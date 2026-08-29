import csv
import os

import numpy as np
import pytest

from rap_senfab import image_pipeline
from rap_senfab.image_pipeline import (
    ResultTest,
    SetGlobalVariables,
    makeCSV,
)


@pytest.fixture(autouse=True)
def clear_globals():
    image_pipeline._gv.clear()
    yield
    image_pipeline._gv.clear()


@pytest.fixture
def image():
    return np.zeros((240, 320, 3), dtype=np.uint8)


@pytest.fixture
def gv(tmp_path):
    return {
        "gs_semimage": str(tmp_path / "input" / "DEF123_sem.jpg"),
        "gs_resultdata.url": "  " + str(tmp_path / "result") + "  ",
        "gs_defectid": "DEF123",
        "dcoll_list": [["^CD_A$", "^CD_B$"]],
    }


def read_dcoll(path):
    with open(path, newline="") as handle:
        return list(csv.reader(handle))


def test_set_global_variables_passes_the_image_through(image, gv):
    output1, output2, output3 = SetGlobalVariables(image, None, gv)

    assert output1 is image
    assert output3 is gv


def test_set_global_variables_derives_paths(image, gv, tmp_path):
    SetGlobalVariables(image, None, gv)

    assert image_pipeline._gv["id"] == "DEF123"
    assert image_pipeline._gv["mp_no"] == 1
    assert image_pipeline._gv["image_height"] == 240
    assert image_pipeline._gv["image_width"] == 320
    assert image_pipeline._gv["result_data_dir"] == str(tmp_path / "result")
    assert image_pipeline._gv["result_image_path"] == str(
        tmp_path / "result" / "DEF123_sem_result.jpg"
    )
    assert image_pipeline._gv["dcollFilePath"] == str(
        tmp_path / "result" / "DEF123_Dcoll.csv"
    )


def test_extensionless_input_gets_a_default_extension(image, gv, tmp_path):
    gv["gs_semimage"] = str(tmp_path / "input" / "DEF123_sem")

    SetGlobalVariables(image, None, gv)

    assert image_pipeline._gv["result_file_name"] == "DEF123_sem_result.jpg"


def test_separate_image_directory_is_honoured(image, gv, tmp_path):
    gv["gs_resultimage.url"] = str(tmp_path / "images")

    SetGlobalVariables(image, None, gv)
    makeCSV(image, None, None)

    assert os.path.isdir(tmp_path / "images")
    assert image_pipeline._gv["result_image_path"].startswith(
        str(tmp_path / "images")
    )


def test_make_csv_writes_header_and_rows(image, gv):
    SetGlobalVariables(image, None, gv)
    output1, output2, output3 = makeCSV(image, None, None)

    assert output1 is image
    assert output2 is None and output3 is None

    rows = read_dcoll(image_pipeline._gv["dcollFilePath"])

    assert rows[0] == ["ID", "TYPE", "NAME", "VALUE", "DESCRIPTION"]
    assert rows[1] == [
        "DEF123",
        "IMG",
        "PATH",
        image_pipeline._gv["result_image_path"],
        "Results Image",
    ]
    assert rows[2] == ["DEF123", "IDBS", "^CD1$", "", "^CD1$"]
    assert rows[3] == ["DEF123", "IDBS", "^CD_A$", "", "^CD_A$"]
    assert rows[4] == ["DEF123", "IDBS", "^CD_B$", "", "^CD_B$"]
    assert len(rows) == 5


def test_make_csv_uses_mp_no_from_the_recipe(image, gv):
    gv["mp_no"] = 3

    SetGlobalVariables(image, None, gv)
    makeCSV(image, None, None)

    rows = read_dcoll(image_pipeline._gv["dcollFilePath"])

    assert rows[2][2] == "^CD3$"


def test_make_csv_without_dcoll_list(image, gv):
    del gv["dcoll_list"]

    SetGlobalVariables(image, None, gv)
    makeCSV(image, None, None)

    rows = read_dcoll(image_pipeline._gv["dcollFilePath"])

    assert len(rows) == 3


def test_malformed_dcoll_entry_is_rejected(image, gv):
    gv["dcoll_list"] = [["^CD_A$"]]

    with pytest.raises(ValueError):
        SetGlobalVariables(image, None, gv)


def test_result_test_draws_on_the_image(gv):
    # The annotations are drawn in black, so start from a white canvas.
    canvas = np.full((240, 320, 3), 255, dtype=np.uint8)

    SetGlobalVariables(canvas, None, gv)
    res, resultData, passthrough = ResultTest(canvas, "data", "third")

    assert res is canvas
    assert resultData == "data"
    assert passthrough == "third"
    assert (canvas != 255).any(), "expected the annotation text to be drawn"


def test_nodes_refuse_to_run_before_set_global_variables(image):
    with pytest.raises(RuntimeError):
        makeCSV(image, None, None)

    with pytest.raises(RuntimeError):
        ResultTest(image, None, None)
