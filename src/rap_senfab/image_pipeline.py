"""SEM image post-processing nodes for the MPP recipe pipeline.

Every public node keeps the framework's three-in / three-out signature, so the
recipe graph can call them unchanged:

    SetGlobalVariables -> ... -> ResultTest -> makeCSV

``SetGlobalVariables`` fills the module level ``_gv`` cache that the later
nodes read from, so it has to run first for each defect image.
"""

import os

import cv2
import numpy as np
import pandas as pd

# region setup dependent constants -------------------------------------------

NM_PER_PIXEL = 0.53  # [nm/pixel]
ROTATION_DEG = 0

BLACK = (0, 0, 0)
WHITE = (255, 255, 255)

# Fallback extension for input paths that carry no suffix.
DEFAULT_IMAGE_EXTENSION = ".jpg"

DCOLL_HEADER = ["ID", "TYPE", "NAME", "VALUE", "DESCRIPTION"]

# endregion

_gv = {}


def _require_globals(*keys):
    """Return the cached globals, failing loudly when a node runs too early."""
    missing = [key for key in ("id", *keys) if key not in _gv]
    if missing:
        raise RuntimeError(
            "SetGlobalVariables must run before this node; missing: "
            + ", ".join(missing)
        )
    return _gv


def _normalize_dcoll_list(raw):
    """Coerce the recipe's DColl variable list into ``[[name_a, name_b], ...]``."""
    dcoll_list = []

    for entry in raw or []:
        pair = list(entry)
        if len(pair) != 2:
            raise ValueError(
                "each dcoll_list entry needs exactly 2 variable names, got: "
                + repr(entry)
            )
        dcoll_list.append(pair)

    return dcoll_list


def SetGlobalVariables(input1, input2, input3):
    inputImg = input1
    gv = input3

    _gv.clear()

    ## 셋업 조건에 따라 수정 ##
    _gv["nm_pixel"] = NM_PER_PIXEL
    _gv["rotation"] = ROTATION_DEG

    _gv["black"] = BLACK
    _gv["white"] = WHITE

    ## pno 구별 필요시 ##
    _gv["mp_no"] = int(gv.get("mp_no", 1))

    _gv["image_height"], _gv["image_width"] = inputImg.shape[:2]

    _gv["id"] = gv["gs_defectid"]

    input_image_path = gv["gs_semimage"]
    input_file_name = os.path.basename(input_image_path)

    base_file_name, image_extension = os.path.splitext(input_file_name)
    if not image_extension:
        image_extension = DEFAULT_IMAGE_EXTENSION

    result_data_dir = str(gv["gs_resultdata.url"]).strip()
    result_image_dir = str(
        gv.get("gs_resultimage.url", result_data_dir)
    ).strip()

    _gv["result_data_dir"] = result_data_dir
    _gv["result_image_dir"] = result_image_dir

    _gv["result_file_name"] = base_file_name + "_result" + image_extension
    _gv["result_image_path"] = os.path.join(
        result_image_dir,
        _gv["result_file_name"]
    )

    _gv["dcollFilePath"] = os.path.join(
        result_data_dir,
        str(gv["gs_defectid"]) + "_Dcoll.csv"
    )

    _gv["dcoll_list"] = _normalize_dcoll_list(gv.get("dcoll_list"))

    # Pass the image through so the downstream nodes still receive it.
    return inputImg, input2, gv


def makeCSV(inputImg, input2, input3):
    gv = _require_globals(
        "result_image_dir",
        "result_data_dir",
        "result_image_path",
        "dcollFilePath",
        "dcoll_list",
        "mp_no",
    )

    ## 결과물 저장 폴더 생성 ##
    os.makedirs(gv["result_image_dir"], exist_ok=True)
    os.makedirs(gv["result_data_dir"], exist_ok=True)

    ### 파일 Header
    dcollData = [list(DCOLL_HEADER)]

    dcollData.append([
        gv["id"],
        "IMG",
        "PATH",
        gv["result_image_path"],
        "Results Image"
    ])

    ### DColl Variable 데이터 저장
    # 사진에서 삭제 표시된 부분
    cd_name = "^CD{}$".format(gv["mp_no"])

    dcollData.append([
        gv["id"],
        "IDBS",
        cd_name,
        np.nan,
        cd_name
    ])

    for name_a, name_b in gv["dcoll_list"]:
        dcollData.append([gv["id"], "IDBS", name_a, np.nan, name_a])
        dcollData.append([gv["id"], "IDBS", name_b, np.nan, name_b])

    df = pd.DataFrame(dcollData)

    df.to_csv(
        gv["dcollFilePath"],
        header=False,
        index=False
    )

    output1 = inputImg
    output2 = None
    output3 = None

    return output1, output2, output3


def drawText(
    res,
    x,
    y,
    text,
    color=WHITE,
    fontScale=1.5,
    thickness=2
):
    cv2.putText(
        res,
        str(text),
        (int(x), int(y)),
        cv2.FONT_HERSHEY_PLAIN,
        fontScale,
        color,
        thickness,
        cv2.LINE_AA
    )

    return res


def ResultTest(input1, input2, input3):
    res = input1
    resultData = input2

    gv = _require_globals(
        "image_width",
        "image_height",
        "nm_pixel",
        "rotation",
        "black",
    )

    drawText(
        res,
        gv["image_width"] * 0.65,
        gv["image_height"] * 0.05,
        "nm/pixel : " + str(gv["nm_pixel"]) + "nm",
        color=gv["black"],
        fontScale=1,
        thickness=1
    )

    drawText(
        res,
        gv["image_width"] * 0.65,
        gv["image_height"] * 0.1,
        "deg : " + str(gv["rotation"]),
        color=gv["black"],
        fontScale=1,
        thickness=1
    )

    output1 = res
    output2 = resultData
    output3 = input3

    return output1, output2, output3
