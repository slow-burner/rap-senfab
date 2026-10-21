# -*- coding: utf-8 -*-
"""화면 전수 검증.  실행:  pytest -q tests/test_app.py

데이터 컬럼이나 기준값을 바꾼 뒤에는 반드시 돌린다.
예외 0건이어야 하고, 실패하면 어떤 기간·EQP·페이지 조합인지 바로 나온다.
"""
from __future__ import annotations

import os
from datetime import date, timedelta

import pytest
from streamlit.testing.v1 import AppTest

APP = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app.py")
TODAY = date.today()

TOPS = ["전체 현황", "부서별 Manual 사전 지정 현황", "LOT 상세 조회"]
EXTRA = ["부하·CAPA", "부서별 조정 요청", "Manual 상세",
         "주차별 부서별 현황", "주차별 PPID·STEP Worst 10", "주차별 요청자 Worst 10",
         "ST TOP 10", "사유 분류", "일자 추이", "STEP 분포", "전주 대비 PPID"]
PAGES = TOPS + EXTRA


def run(**ss) -> AppTest:
    at = AppTest.from_file(APP, default_timeout=180)
    for k, v in ss.items():
        at.session_state[k] = v
    at.run()
    assert not at.exception, [str(getattr(e, "value", e))[:400] for e in at.exception]
    return at


def rng(days: int):
    return (TODAY - timedelta(days=days - 1), TODAY)


@pytest.mark.parametrize("days", [3, 7, 30, 91])
@pytest.mark.parametrize("eqp", [[], ["METRCD"]], ids=["eqp_all", "eqp_metrcd"])
@pytest.mark.parametrize("page", PAGES)
def test_pages(days, eqp, page):
    run(nav=page, drange=rng(days), f_eqp=eqp)


@pytest.mark.parametrize("v", ["전체", "미진행", "지연", "승인 대기", "완료", "Cancel"])
def test_lot_view(v):
    run(nav=TOPS[2], lot_view=v)


@pytest.mark.parametrize("unit", ["STEP 단위", "LOT 단위"])
def test_lot_unit(unit):
    run(nav=TOPS[2], lot_unit=unit)


@pytest.mark.parametrize("scope", ["전체", "Manual"])
@pytest.mark.parametrize("metric", ["ST(h)", "LOT 수", "매수"])
def test_trend(scope, metric):
    run(nav=TOPS[0], t_scope=scope, t_metric=metric)


WEEK_PAGES = [("주차별 부서별 현황", "wd"),
              ("주차별 PPID·STEP Worst 10", "wp"),
              ("주차별 요청자 Worst 10", "wu")]


@pytest.mark.parametrize("page,kp", WEEK_PAGES)
@pytest.mark.parametrize("weeks", ["4주", "8주", "12주"])
@pytest.mark.parametrize("metric", ["측정시간", "LOT 수", "매수"])
def test_weekly(page, kp, weeks, metric):
    """주차별 3화면 x 기간 3종 x 지표 3종."""
    run(**{"nav": page, f"{kp}_weeks": weeks, f"{kp}_metric": metric})


def test_weekly_same_total():
    """세 화면이 같은 모수를 쓰는지 — 같은 주 합계가 일치해야 한다."""
    import pandas as pd
    from datetime import date as _d
    sys_path_df = __import__("data_source").load_weeks(_d.today(), 12)
    m = sys_path_df[sys_path_df["상태"].ne("Cancel") & sys_path_df["사유"].eq("Manual")]
    wk = m["요청일"].dt.to_period("W").dt.start_time
    by_dept = m.groupby([wk, m["DEPARTMENT"]])["예상APT"].sum().groupby(level=0).sum()
    by_ppid = m.groupby([wk, m["PPID"]])["예상APT"].sum().groupby(level=0).sum()
    by_user = m.groupby([wk, m["요청자"]])["예상APT"].sum().groupby(level=0).sum()
    assert by_dept.round(3).equals(by_ppid.round(3))
    assert by_dept.round(3).equals(by_user.round(3))


@pytest.mark.parametrize("by", ["LOT", "PPID", "STEP", "요청자", "부서"])
def test_top(by):
    run(nav="ST TOP 10", top_by=by)


@pytest.mark.parametrize("thr", [10, 120, 600])
def test_threshold(thr):
    """알람 임계치를 바꿔도 모든 카드가 돌아야 한다 (0건 / 다수 / 중간)."""
    run(nav=TOPS[0], thr=thr)
    run(nav=TOPS[2], thr=thr, lot_unit="LOT 단위")


def test_weekly_empty_filter():
    """필터로 Manual 이 0건이 되어도 주차 화면이 안내만 띄워야 한다."""
    for page, _ in WEEK_PAGES:
        run(nav=page, f_rsn=["DSM"])


def test_alarm_all_states():
    run(nav=TOPS[0], alm_pend=False)


def test_search_and_filters():
    run(nav=TOPS[2], lot_q="CDM_GATE")
    run(nav=TOPS[2], lot_q="ZZZZNOPE")            # 결과 0건
    run(nav=TOPS[2], lot_long=True, lot_rsn=["Manual"])
    run(nav=TOPS[0], f_line=["M1A"])
    run(nav=TOPS[1], f_dept=["식각기술팀"], f_rsn=["Manual"])
    run(nav=TOPS[1], mreq_long=True, mreq_dept=["포토기술팀"], long_thr=300)
    run(nav=TOPS[1], f_eqp=["METRCD"])            # 단일 EQP -> 격자 1·2·3위
    run(nav="부서별 조정 요청", f_dept=["식각기술팀"])
    run(nav="Manual 상세", md_dept=["포토기술팀"], md_eqp=["METROVL"])


def test_empty_result():
    """필터를 다 걸어 데이터가 비어도 예외 없이 안내만 떠야 한다."""
    run(nav=TOPS[0], f_line=["M1A"], f_dept=["확산기술팀"], f_rsn=["DSM"],
        f_eqp=["METRDEF"], drange=(TODAY, TODAY))


def test_min_days():
    """하루만 골라도 최소 3일로 늘려 조회한다."""
    at = run(drange=(TODAY, TODAY))
    assert any("최소 3일" in c.value for c in at.caption)


def test_top_tab_click():
    at = AppTest.from_file(APP, default_timeout=180)
    at.run()
    assert not at.exception
    for i, name in enumerate(TOPS):
        btn = [b for b in at.button if b.key == f"top_{i}"]
        assert btn, f"상단 탭 버튼 없음: top_{i}"
        btn[0].click().run()
        assert not at.exception, str(at.exception[0])[:400]
        assert at.session_state["nav"] == name


def test_extra_select():
    at = AppTest.from_file(APP, default_timeout=180)
    at.run()
    at.selectbox(key="extra_pick").select("ST TOP 10").run()
    assert not at.exception
    assert at.session_state["nav"] == "ST TOP 10"
