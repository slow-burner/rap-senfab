# -*- coding: utf-8 -*-
"""계측 사전 지정 조회 계층.

화면은 load_raw(d_from, d_to)가 돌려주는 컬럼 이름만 쓴다.

데이터 계약 (이 이름 그대로 유지):
    요청일(Timestamp), LINEID, EQP_TYPE, PROCESSID, STEPID, STEP_SEQ, PPID,
    DEPARTMENT, 요청자, LOTID, SLOTID, 지정매수, APT_매(1매 ST, 분),
    예상APT(= APT_매 x 지정매수, 분), 사유, 승인상태, 상태

USE_SAMPLE = True 면 사내 DB 없이 샘플로 돈다. 실제 연결은 _db()를 채운다.
"""

from __future__ import annotations

import configparser
import os
import random
from datetime import date, datetime, timedelta

import pandas as pd

USE_SAMPLE = True   # 사내망에서 DB 붙일 때 False

COLUMNS = [
    "요청일", "LINEID", "EQP_TYPE", "PROCESSID", "STEPID", "STEP_SEQ", "PPID",
    "DEPARTMENT", "요청자", "LOTID", "SLOTID", "지정매수", "APT_매", "예상APT",
    "사유", "승인상태", "상태",
]

# --------------------------------------------------------------- 샘플 기준표
# (PPID, EQP_TYPE, STEPID, STEP_SEQ, APT_매(분/매))
# 이름이 _MN 으로 끝나는 PPID = 장시간 측정 레시피. Manual 사전 지정에만 쓰인다.
PPID_MASTER = [
    ("CDM_GATE_AEI_01",    "METRCD",  "GATE_AEI_CD",    "0420",  6.0),
    ("CDM_ACT_ADI_02",     "METRCD",  "ACT_ADI_CD",     "0260",  5.5),
    ("CDM_CT_AEI_03",      "METRCD",  "CONTACT_AEI_CD", "0710",  7.0),
    ("CDM_M1_ADI_04",      "METRCD",  "M1_ADI_CD",      "0980",  6.5),
    ("CDM_GATE_FULL_MN",   "METRCD",  "GATE_AEI_CD",    "0420", 28.0),
    ("CDM_CT_PROFILE_MN",  "METRCD",  "CONTACT_AEI_CD", "0710", 32.0),
    ("OVL_M1_DBO_01",      "METROVL", "M1_OVL",         "0990",  4.0),
    ("OVL_CT_IBO_02",      "METROVL", "CONTACT_OVL",    "0720",  4.5),
    ("OVL_GATE_DBO_03",    "METROVL", "GATE_OVL",       "0430",  5.0),
    ("OVL_CPE_FULL_MN",    "METROVL", "M1_OVL",         "0990", 26.0),
    ("OVL_HOT_CPE_MN",     "METROVL", "GATE_OVL",       "0430", 24.0),
    ("THK_OX_ELP_01",      "METRTHK", "OXIDE_THK",      "0150",  3.5),
    ("THK_NIT_ELP_02",     "METRTHK", "NITRIDE_THK",    "0320",  3.0),
    ("THK_POLY_ELP_03",    "METRTHK", "POLY_THK",       "0400",  3.8),
    ("THK_STACK_MAP_MN",   "METRTHK", "OXIDE_THK",      "0150", 30.0),
    ("DEF_ADI_INSP_01",    "METRDEF", "ADI_DEFECT",     "0270",  9.0),
    ("DEF_AEI_INSP_02",    "METRDEF", "AEI_DEFECT",     "0440", 10.0),
    ("DEF_FULLWF_SCAN_MN", "METRDEF", "AEI_DEFECT",     "0440", 36.0),
]

LINEIDS = ["M1A", "M1B", "M2A"]
PROCESSIDS = ["LG28-A1", "LG28-B2", "DR18-C1"]

# 부서 -> 요청자 ID 앞단어
DEPTS = {
    "포토기술팀": "PHOTO",
    "식각기술팀": "ETCH",
    "박막기술팀": "THIN",
    "확산기술팀": "DIFF",
    "계측기술팀": "METRO",
}
# 부서가 주로 보는 EQP TYPE (가중치)
DEPT_EQP_W = {
    "포토기술팀": {"METROVL": 5, "METRCD": 3, "METRTHK": 1, "METRDEF": 1},
    "식각기술팀": {"METRCD": 5, "METRDEF": 3, "METROVL": 1, "METRTHK": 1},
    "박막기술팀": {"METRTHK": 5, "METRCD": 2, "METRDEF": 2, "METROVL": 1},
    "확산기술팀": {"METRTHK": 4, "METRDEF": 2, "METRCD": 2, "METROVL": 1},
    "계측기술팀": {"METRCD": 3, "METROVL": 3, "METRTHK": 2, "METRDEF": 2},
}

REASONS = ["Manual", "PM AUTO QUAL", "APC", "DSM"]
_RAMP_DAYS = 120      # 최근 120일에 걸쳐 Manual 비중이 늘어나는 샘플


def _manual_weight(d: date, today: date) -> float:
    """Manual 사유 가중치. 0.6 -> 3.0 으로 서서히 증가."""
    frac = (d - (today - timedelta(days=_RAMP_DAYS))).days / float(_RAMP_DAYS)
    frac = min(max(frac, 0.0), 1.0)
    return 0.6 + 2.4 * frac


def _pick(rng: random.Random, weights: dict):
    keys = list(weights.keys())
    return rng.choices(keys, weights=[weights[k] for k in keys], k=1)[0]


def _sample(d_from: date, d_to: date) -> pd.DataFrame:
    """날짜별로 고정 시드를 쓰므로 같은 날짜는 조회 구간이 달라도 같은 값이 나온다."""
    today = date.today()
    normal = [p for p in PPID_MASTER if not p[0].endswith("_MN")]
    longs = [p for p in PPID_MASTER if p[0].endswith("_MN")]
    by_eqp_n, by_eqp_l = {}, {}
    for p in normal:
        by_eqp_n.setdefault(p[1], []).append(p)
    for p in longs:
        by_eqp_l.setdefault(p[1], []).append(p)

    rows = []
    d = d_from
    while d <= d_to:
        rng = random.Random(d.toordinal() * 7919)
        mw = _manual_weight(d, today)
        reason_w = {"Manual": mw, "PM AUTO QUAL": 1.0, "APC": 1.2, "DSM": 0.6}
        days_ago = (today - d).days
        n = rng.randint(26, 44)
        lot_pool: list[tuple[str, str]] = []

        for i in range(n):
            dept = _pick(rng, {k: 1 for k in DEPTS})
            reason = _pick(rng, reason_w)
            eqp = _pick(rng, DEPT_EQP_W[dept])

            long_shot = reason == "Manual" and rng.random() < 0.45
            # PM 후 full wafer qual 은 일반 레시피로 여러 매를 돌려 ST 가 커진다
            pm_full = reason == "PM AUTO QUAL" and rng.random() < 0.22
            pool = by_eqp_l.get(eqp) if long_shot else by_eqp_n.get(eqp)
            if not pool:
                pool = by_eqp_n.get(eqp) or normal
            ppid, eqp_type, stepid, step_seq, apt = rng.choice(pool)

            if long_shot:
                slots = rng.randint(3, 6)
            elif pm_full:
                slots = rng.randint(9, 25)     # PM 후 full lot qual
            elif reason == "Manual":
                slots = rng.randint(1, 3)
            else:
                slots = rng.randint(1, 2)

            # 같은 LOT에 계측 STEP이 여러 개 걸리는 경우를 섞는다
            if lot_pool and rng.random() < 0.25:
                lotid, lineid = rng.choice(lot_pool)
            else:
                lotid = f"N{d:%y%m%d}{i:02d}"
                lineid = rng.choice(LINEIDS)
                lot_pool.append((lotid, lineid))

            slot_ids = sorted(rng.sample(range(1, 26), slots))
            if days_ago >= 5:
                state = _pick(rng, {"완료": 0.82, "예정": 0.10, "Cancel": 0.08})
            elif days_ago >= 2:
                state = _pick(rng, {"완료": 0.50, "예정": 0.42, "Cancel": 0.08})
            else:
                state = _pick(rng, {"완료": 0.18, "예정": 0.75, "Cancel": 0.07})
            wait_w = 0.45 if long_shot else 0.18
            appr = _pick(rng, {"요청 대기": wait_w, "승인 완료": 1 - wait_w})

            rows.append({
                "요청일": datetime(d.year, d.month, d.day,
                                rng.randint(6, 21), rng.choice([0, 10, 20, 30, 40, 50])),
                "LINEID": lineid,
                "EQP_TYPE": eqp_type,
                "PROCESSID": rng.choice(PROCESSIDS),
                "STEPID": stepid,
                "STEP_SEQ": step_seq,
                "PPID": ppid,
                "DEPARTMENT": dept,
                "요청자": f"{DEPTS[dept]}_USER{rng.randint(1, 3):02d}",
                "LOTID": lotid,
                "SLOTID": ",".join(f"{s:02d}" for s in slot_ids),
                "지정매수": slots,
                "APT_매": apt,
                "사유": reason,
                "승인상태": appr,
                "상태": state,
            })
        d += timedelta(days=1)

    df = pd.DataFrame(rows)
    if df.empty:
        return pd.DataFrame(columns=COLUMNS)
    df["예상APT"] = df["APT_매"] * df["지정매수"]
    return df[COLUMNS]


# ------------------------------------------------------------- 실제 DB 연결
SQL_FILE = "sql/precheck_tkin_view.sql"

# SQL 출력 컬럼 -> 화면이 쓰는 컬럼 (COLUMNS)
# 왼쪽을 바꾸려면 sql/precheck_tkin_view.sql 의 마지막 SELECT 도 같이 본다.
SQL_TO_APP = {
    "RESERVE_DATE":     "요청일",     # 사전 지정 요청 시각 (UPDATE_DATE)
    "LINEP":            "LINEID",     # 라인 분류 (P1F / P2D ...)
    "EQP_TYPE":         "EQP_TYPE",
    "PROC_ID":          "PROCESSID",
    "STEP_ID":          "STEPID",
    "ACTY_STEP_SEQ":    "STEP_SEQ",   # 사전 지정을 건 계측 STEP
    "PPID":             "PPID",
    "DEPT_NAME":        "DEPARTMENT",
    "LOT_ID":           "LOTID",
    "ACTY_SLOT_ID":     "SLOTID",
    "REQ_SLOT_COUNT":   "지정매수",   # 요청 슬롯 수. 트랙인 슬롯이 아니다
    "AVG_APT_USED":     "APT_매",     # PPID 평균, 없으면 STEP 평균
    "FORECAST_APT_REQ": "예상APT",    # 요청 슬롯 기준 총측정시간
}
# 화면이 안 쓰지만 같이 들고 다니는 컬럼 (주차 화면·상세 표에서 쓴다)
SQL_EXTRA = [
    "계측유무", "측정상태", "STEP_도달", "CUR_STEP_SEQ", "CUR_STEP_DESC",
    "BAY_NAME", "WORK_STATUS_SEQ", "PROCESS_EQP_ID", "ST_SOURCE", "APT_N",
    "FORECAST_APT", "SLOT_COUNT", "DESIGN_RULE", "REQ_USER_ID", "EMP_NAME",
    "TKIN_DATE", "TKOUT_DATA",
]


def _cfg() -> configparser.ConfigParser:
    """exe 폴더 옆의 config.ini 를 읽는다."""
    cp = configparser.ConfigParser()
    here = os.path.dirname(os.path.abspath(__file__))
    for p in (os.path.join(os.getcwd(), "config.ini"), os.path.join(here, "config.ini")):
        if os.path.exists(p):
            cp.read(p, encoding="utf-8")
            break
    return cp


def _sql_text() -> str:
    """조회 SQL 본문. 파일 하나만 고치면 프로그램과 수작업 조회가 같이 바뀐다."""
    here = os.path.dirname(os.path.abspath(__file__))
    for base in (here, os.getcwd()):
        p = os.path.join(base, SQL_FILE)
        if os.path.exists(p):
            txt = open(p, encoding="utf-8").read()
            # 파일 끝의 설명 주석을 떼고 본문만 쓴다
            return txt.split(";")[0]
    raise FileNotFoundError(f"{SQL_FILE} 을 찾을 수 없습니다")


def _connect():
    """config.ini 의 [oracle] 로 접속한다. 드라이버는 oracledb 를 먼저 본다."""
    sec = _cfg()["oracle"]
    try:
        import oracledb as drv            # thin 모드. 클라이언트 설치 불필요
    except ImportError:                    # 구버전 환경
        import cx_Oracle as drv            # type: ignore
    dsn = sec.get("dsn") or drv.makedsn(
        sec["host"], int(sec["port"]), service_name=sec["service_name"])
    return drv.connect(user=sec["user"], password=sec["password"], dsn=dsn)


def _db(d_from: date, d_to: date) -> pd.DataFrame:
    """sql/precheck_tkin_view.sql 을 :d_from / :d_to 바인드로 실행한다."""
    conn = _connect()
    try:
        return pd.read_sql(
            _sql_text(), conn,
            params={"d_from": datetime.combine(d_from, datetime.min.time()),
                    "d_to":   datetime.combine(d_to + timedelta(days=1),
                                               datetime.min.time())},
        )
    finally:
        conn.close()


def _map_db(df: pd.DataFrame) -> pd.DataFrame:
    """SQL 출력을 화면이 쓰는 컬럼 이름·값으로 바꾼다.

    여기서만 코드값을 번역한다. 사내 코드가 다르면 capa_config 의
    REASON_MAP / APPROVE_MAP / CANCEL_CODES 만 고치면 된다.
    """
    import capa_config as C

    if df.empty:
        return pd.DataFrame(columns=COLUMNS)
    df = df.rename(columns=SQL_TO_APP).copy()

    # 사유 · 승인상태 : 코드값 -> 화면 값
    df["사유"] = df.get("REQUEST_TYPE", "").map(C.classify_reason)
    df["승인상태"] = df.get("REQ_STATUS", "").map(C.classify_approve)

    # 상태 : 대기 현황 -> 예정 / 측정중 -> 진행 / 완료 -> 완료
    #        요청 자체가 취소된 건은 Cancel
    def _state(r):
        if C.is_cancel(r.get("REQ_STATUS")):
            return "Cancel"
        if r.get("계측유무") == "대기 현황":
            return "예정"
        return "진행" if r.get("측정상태") == "측정중" else "완료"

    df["상태"] = df.apply(_state, axis=1)

    # 요청자 : 이름(사번). 이름이 없으면 사번만
    nm = df.get("EMP_NAME")
    no = df.get("REQ_USER_ID")
    df["요청자"] = [
        f"{a}({b})" if a else str(b or "-")
        for a, b in zip(nm.fillna("") if nm is not None else [""] * len(df),
                        no if no is not None else [""] * len(df))
    ]

    # AST_TIME 단위 보정 (초로 들어오면 capa_config.AST_UNIT_MIN = 1/60)
    for c in ("APT_매", "예상APT", "FORECAST_APT"):
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce") * C.AST_UNIT_MIN

    df["요청일"] = pd.to_datetime(df["요청일"])
    df["지정매수"] = pd.to_numeric(df["지정매수"], errors="coerce").fillna(0).astype(int)
    df["APT_매"] = df["APT_매"].fillna(0.0)
    df["예상APT"] = df["예상APT"].fillna(0.0)

    keep = COLUMNS + [c for c in SQL_EXTRA if c in df.columns]
    for c in COLUMNS:
        if c not in df.columns:
            df[c] = ""
    return df[keep]


def _normalize(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["요청일"] = pd.to_datetime(df["요청일"])
    return df.reset_index(drop=True)


def load_raw(d_from: date, d_to: date) -> pd.DataFrame:
    """조회 구간의 사전 지정 내역. 화면은 이 함수만 호출한다."""
    if USE_SAMPLE:
        return _normalize(_sample(d_from, d_to))
    return _normalize(_map_db(_db(d_from, d_to)))


def load_weeks(d_to: date, weeks: int) -> pd.DataFrame:
    """주차별 화면용. 완료 건까지 포함해 최근 N주를 가져온다."""
    return load_raw(d_to - timedelta(days=7 * weeks - 1), d_to)


def options() -> dict:
    """사이드바 필터 목록. 조회 전에 그려야 해서 따로 받는다."""
    if USE_SAMPLE:
        return {"lines": list(LINEIDS), "depts": list(DEPTS)}
    conn = _connect()
    try:
        ln = pd.read_sql("SELECT DISTINCT LINE_ID FROM fab.m_lot_actv_req", conn)
        dp = pd.read_sql(
            "SELECT DISTINCT ORG_DEPT_KOR_NM AS D FROM dscrm_ds.crmadmin_if_zto_employee "
            "WHERE ORG_DEPT_KOR_NM IS NOT NULL", conn)
        return {"lines": sorted(ln.iloc[:, 0].dropna().tolist()),
                "depts": sorted(dp.iloc[:, 0].dropna().tolist())}
    finally:
        conn.close()
