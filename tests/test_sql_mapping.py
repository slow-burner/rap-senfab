# -*- coding: utf-8 -*-
"""SQL 출력 -> 화면 컬럼 변환 검증.  실행: pytest -q tests/test_sql_mapping.py

사내 Oracle 없이 돌린다. sql/precheck_tkin_view.sql 을 DuckDB 에서 실행해
실제와 같은 모양의 결과를 만들고, data_source._map_db 를 통과시킨다.
SQL 의 출력 컬럼을 바꿨는데 매핑을 안 고치면 여기서 걸린다.
"""
from __future__ import annotations

import os
import re
import sys
from datetime import datetime

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import capa_config as C          # noqa: E402
import data_source as ds         # noqa: E402

duckdb = pytest.importorskip("duckdb")

DDL = {
    "fab.m_lot_actv_req": """LINE_ID VARCHAR,LOT_ID VARCHAR,ACTV_STEP_SEQ VARCHAR,REQ_STATUS_SEQ VARCHAR,
        ACTV_SLOT_ID VARCHAR,PROCESS_ID VARCHAR,REQ_QTY INT,REQ_STATUS VARCHAR,REQUEST_COMMENT VARCHAR,
        REQUEST_TYPE VARCHAR,ROOM_NAME VARCHAR,UPDATE_DATE TIMESTAMP,REQUESTER_ID VARCHAR""",
    "fab.m_lot_transn_hist": """EQP_TYPE VARCHAR,LAST_UPDATE_DATE TIMESTAMP,LINE_ID VARCHAR,LOT_ID VARCHAR,
        LOT_TRANSN_TYPE VARCHAR,LOT_TYPE VARCHAR,PPID VARCHAR,PROCESS_EQP_ID VARCHAR,PROCESS_ID VARCHAR,
        PROCESS_START_DATE TIMESTAMP,SLOT_ID VARCHAR,STEP_DESC VARCHAR,STEP_ID VARCHAR,STEP_SEQ VARCHAR,
        TKIN_DATE TIMESTAMP,TKOUT_DATA TIMESTAMP,TO_PROCESS_UNIT VARCHAR""",
    "fab.m_wip_current": """LINE_ID VARCHAR,LOT_ID VARCHAR,PROCESS_ID VARCHAR,STEP_SEQ VARCHAR,STEP_DESC VARCHAR,
        EQP_TYPE VARCHAR,BAY_NAME VARCHAR,LOT_TYPE VARCHAR,WORK_STATUS_SEQ VARCHAR,LOT_STATUS_SEQ VARCHAR,
        LAST_UPDATE_DATE TIMESTAMP""",
    "fab.m_step": "LINE_ID VARCHAR,STEP_SEQ VARCHAR,STEP_ID VARCHAR,PROCESS_ID VARCHAR,EQP_TYPE VARCHAR,STEP_DESC VARCHAR",
    "fab.m_lot_spx": "PPID VARCHAR,PROCESS_ID VARCHAR,LOCATION_ID VARCHAR,AST_TIME DOUBLE,OUT_TIME TIMESTAMP,AREA VARCHAR",
    "fab.g_tpss_design_rule_record": "AREA VARCHAR,PROCESS_ID VARCHAR,DESIGN_RULE VARCHAR,REV_TIME TIMESTAMP",
    "dscrm_ds.crmadmin_if_zto_employee": "EMP_NO VARCHAR,EMP_PRF_FLLNM VARCHAR,ORG_DEPT_KOR_NM VARCHAR",
}


def _run_sql():
    """실제 SQL 을 DuckDB 로 실행해 결과 DataFrame 을 돌려준다."""
    sql = ds._sql_text()
    # Oracle 전용 표현만 치환한다. 조인·계산 로직은 그대로 둔다.
    sql = sql.replace(":d_from - 8", "TIMESTAMP '2026-10-12 00:00:00'")
    sql = sql.replace(":d_to - 28", "TIMESTAMP '2026-09-22 00:00:00'")
    sql = sql.replace(":d_from", "TIMESTAMP '2026-10-20 00:00:00'")
    sql = sql.replace(":d_to", "TIMESTAMP '2026-10-21 00:00:00'")
    sql = sql.replace("NULLS LAST", "")
    sql = re.sub(r"/\*.*?\*/", "", sql, flags=re.S)
    sql = re.sub(r"--[^\n]*", "", sql)

    con = duckdb.connect()
    con.execute("CREATE SCHEMA fab; CREATE SCHEMA dscrm_ds;")
    for t, cols in DDL.items():
        con.execute(f"CREATE TABLE {t}({cols})")

    con.execute("""INSERT INTO fab.m_lot_actv_req VALUES
     ('PFBP','T1','S1','1','01,05','KGVL',2,'EXECUTE','PM 변경점','MANUAL','DIFF',TIMESTAMP '2026-10-20 08:00','E001'),
     ('PFBP','W1','S1','1','01,05,09','KGVL',3,'EXECUTE','확인','MANUAL','DIFF',TIMESTAMP '2026-10-20 09:00','E002'),
     ('PFBP','X1','S1','1','01','KGVL',1,'CANCEL','취소','APC','DIFF',TIMESTAMP '2026-10-20 10:00','E001')""")
    con.execute("""INSERT INTO fab.m_lot_transn_hist VALUES
     ('METRCD',TIMESTAMP '2026-10-20 12:00','PFBP','T1','Trackout','PP','PX','MCPG76','KGVL',
      TIMESTAMP '2026-10-20 11:50','01,05','CD','ST_H','S1',TIMESTAMP '2026-10-20 11:45',NULL,'PUP')""")
    con.execute("""INSERT INTO fab.m_wip_current VALUES
     ('PFBP','T1','KGVL','S1','CD측정','METRCD','BAY1','PP','RUN','Active',TIMESTAMP '2026-10-20 12:00'),
     ('PFBP','W1','KGVL','S0','식각','ETCH','BAY3','PP','WAIT','Active',TIMESTAMP '2026-10-20 12:00'),
     ('PFBP','X1','KGVL','S1','CD측정','METRCD','BAY1','PP','RUN','Active',TIMESTAMP '2026-10-20 12:00')""")
    con.execute("INSERT INTO fab.m_step VALUES ('PFBP','S1','ST_MASTER','KGVL','METRCD','마스터')")
    con.execute("""INSERT INTO fab.m_lot_spx VALUES
     ('PX','KGVL','S1',10.0,TIMESTAMP '2026-10-01','PFBP'),
     ('PY','KGVL','S1',30.0,TIMESTAMP '2026-10-02','PFBP')""")
    con.execute("INSERT INTO fab.g_tpss_design_rule_record VALUES ('PFBP','KGVL','C10',TIMESTAMP '2026-05-01')")
    con.execute("INSERT INTO dscrm_ds.crmadmin_if_zto_employee VALUES ('E001','홍길동','식각기술팀'),('E002','김철수','포토기술팀')")
    return con.execute(sql).df()


def test_sql_runs_and_has_mapped_columns():
    """SQL 이 돌고, 매핑표가 가리키는 컬럼을 전부 내놓는가."""
    raw = _run_sql()
    assert not raw.empty
    missing = [c for c in ds.SQL_TO_APP if c not in raw.columns]
    assert not missing, f"SQL 이 내보내지 않는 컬럼: {missing}"


def test_map_db_fills_app_contract():
    """_map_db 가 화면 계약(COLUMNS)을 빠짐없이 채우는가."""
    out = ds._map_db(_run_sql())
    for c in ds.COLUMNS:
        assert c in out.columns, f"화면 계약 컬럼 누락: {c}"
    assert out["요청일"].dtype.kind == "M"
    assert out["지정매수"].dtype.kind in "iu"
    assert out["예상APT"].notna().all()


def test_code_values_translated():
    """코드값이 화면 값으로 번역되는가 (사유·승인상태·상태·요청자)."""
    out = ds._map_db(_run_sql()).set_index("LOTID")

    assert set(out["사유"]) <= set(C.REASONS), f"모르는 사유: {set(out['사유'])}"
    assert out.loc["T1", "사유"] == "Manual"          # REQUEST_TYPE = MANUAL
    assert out.loc["X1", "사유"] == "APC"

    assert out.loc["T1", "승인상태"] == "승인 완료"    # REQ_STATUS = EXECUTE
    assert out.loc["X1", "승인상태"] == "요청 대기"    # CANCEL -> 매핑 없음

    assert out.loc["T1", "상태"] == "진행"             # TKIN 했고 TKOUT 전
    assert out.loc["W1", "상태"] == "예정"             # 대기 현황
    assert out.loc["X1", "상태"] == "Cancel"           # REQ_STATUS = CANCEL

    assert out.loc["T1", "요청자"] == "홍길동(E001)"
    assert out.loc["T1", "DEPARTMENT"] == "식각기술팀"


def test_forecast_uses_requested_slots():
    """예상APT 는 '요청 슬롯 수 x 1매 ST' 다. 트랙인 슬롯이 아니다."""
    out = ds._map_db(_run_sql()).set_index("LOTID")
    assert out.loc["T1", "지정매수"] == 2            # 요청 01,05
    assert out.loc["T1", "APT_매"] == pytest.approx(10.0)
    assert out.loc["T1", "예상APT"] == pytest.approx(20.0)
    # 대기 건은 PPID 가 없어 STEP 평균(10+30)/2 = 20 으로 받친다
    assert out.loc["W1", "ST_SOURCE"] == "STEP 평균"
    assert out.loc["W1", "예상APT"] == pytest.approx(60.0)


def test_ast_unit_conversion(monkeypatch):
    """AST_TIME 이 초 단위면 capa_config.AST_UNIT_MIN 만 바꿔 분으로 환산된다."""
    monkeypatch.setattr(C, "AST_UNIT_MIN", 1 / 60)
    out = ds._map_db(_run_sql()).set_index("LOTID")
    assert out.loc["T1", "예상APT"] == pytest.approx(20.0 / 60)
