# -*- coding: utf-8 -*-
"""계측 사전 지정 부하 모니터.

기술 부서가 Manual 로 걸어 둔 사전 지정 때문에 계측 재공이 밀리는 것을
미리 잡는 화면. 핵심은 '총측정시간(= 1매 ST x 지정 매수)'이 임계치를 넘는
LOT 을 측정 전에 띄워 담당 부서에 물량 조정을 요청하는 것이다.
"""

from __future__ import annotations

import html
import io
from datetime import date, timedelta

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
import streamlit.components.v1 as components

import capa_config as C
from data_source import DEPTS, load_raw

st.set_page_config(page_title="계측 사전 지정 부하 모니터", layout="wide", page_icon="📐")

TOPS = ["전체 현황", "부서별 Manual 사전 지정 현황", "LOT 상세 조회"]
EXTRA_HEAD = "기타 분석"
EXTRA = [EXTRA_HEAD, "부하·CAPA", "부서별 조정 요청", "Manual 상세", "Manual 주차 추이",
         "ST TOP 10", "사유 분류", "일자 추이", "STEP 분포", "전주 대비 PPID"]
CARD_PAGES = {TOPS[0], TOPS[1]}
DEPT_ALL = list(DEPTS)        # 요청 부서 목록 (조회 전에 필터를 그려야 해서 기준표에서 받는다)

for k, v in {"nav": TOPS[0], "extra_pick": EXTRA_HEAD}.items():
    st.session_state.setdefault(k, v)


# ============================================================ 공통 유틸
def esc(v) -> str:
    return html.escape("" if v is None else str(v))


def fh(minutes) -> str:
    """분 -> 시간 문자열."""
    try:
        return f"{float(minutes) / 60.0:,.1f}h"
    except (TypeError, ValueError):
        return "-"


def card(parent, name: str):
    """흰 카드 컨테이너. 구버전 streamlit 은 key 없이 떨어진다."""
    try:
        return parent.container(border=True, key=f"card_{name}")
    except TypeError:
        return parent.container(border=True)


def seg(parent, label: str, options: list, key: str, default=None):
    """segmented_control 이 없으면 radio horizontal 로 떨어진다."""
    if default is None:
        default = options[0]
    st.session_state.setdefault(key, default)
    if hasattr(parent, "segmented_control"):
        v = parent.segmented_control(label, options, key=key, label_visibility="collapsed")
        return v if v else st.session_state.get(key) or default
    return parent.radio(label, options, key=key, horizontal=True, label_visibility="collapsed")


def chart(parent, fig, key: str, on_select=None):
    # 그래프 key 는 g_ 를 붙여 사이드바 필터 key(f_dept 등)와 겹치지 않게 한다
    kw = dict(width="stretch", config={"displayModeBar": False}, key=f"g_{key}")
    if on_select:
        kw["on_select"] = on_select
    return parent.plotly_chart(fig, **kw)


def lay(fig, height: int = 250, legend: bool = False, facet: bool = False):
    fig.update_layout(
        height=height,
        margin=dict(l=8, r=8, t=56 if legend else 16, b=8),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Malgun Gothic, Apple SD Gothic Neo, sans-serif",
                  size=11.5, color=C.INK),
        showlegend=legend,
        legend=dict(orientation="h", y=1.13, x=0, title_text="", font=dict(size=11)),
        bargap=0.30,
        hoverlabel=dict(font_size=11.5),
    )
    fig.update_xaxes(showgrid=False, linecolor=C.LINE, title_text="")
    fig.update_yaxes(gridcolor="#f1f4f3", zerolinecolor=C.LINE, title_text="")
    if facet:
        fig.for_each_annotation(lambda a: a.update(text=a.text.split("=")[-1],
                                                   font=dict(size=11, color=C.SUB)))
    return fig


def empty_note(parent, msg: str = "조건에 맞는 사전 지정 내역이 없습니다."):
    parent.markdown(f"<div class='nn'>{esc(msg)}</div>", unsafe_allow_html=True)


def tx_table(rows: list[list[str]], head: list[str], wrap: bool = True) -> str:
    """HTML 표. 셀 문자열은 미리 esc 하거나 배지 HTML 을 그대로 넣는다."""
    th = "".join(f"<th>{h}</th>" for h in head)
    tr = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
    t = f"<table class='tx'><thead><tr>{th}</tr></thead><tbody>{tr}</tbody></table>"
    return f"<div class='txw'>{t}</div>" if wrap else t


def bd(kind: str, text: str) -> str:
    return f"<span class='bd {kind}'>{esc(text)}</span>"


def xls(frames: dict[str, pd.DataFrame]) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        for name, d in frames.items():
            d.to_excel(w, sheet_name=name[:31], index=False)
    return buf.getvalue()


def dstr(d) -> str:
    return pd.Timestamp(d).strftime("%Y-%m-%d")


# ============================================================ CSS
PAGE = st.session_state["nav"]
IS_CARD = PAGE in CARD_PAGES
TOP_IDX = TOPS.index(PAGE) if PAGE in TOPS else -1

st.markdown(f"""<style>
:root {{ --ink:{C.INK}; --sub:{C.SUB}; --line:{C.LINE}; --acc:{C.ACCENT};
         --deep:{C.DEEP}; --mint:{C.MINT}; --red:{C.RED}; --amber:{C.AMBER}; }}
.stApp {{ background:{C.BG}; }}
#MainMenu, footer, header [data-testid="stStatusWidget"] {{ visibility:hidden; }}
[data-testid="stMainBlockContainer"] {{ padding:58px 26px 40px; max-width:1680px; }}
section[data-testid="stSidebar"] {{ background:#fff; border-right:1px solid var(--line); }}
section[data-testid="stSidebar"] [data-testid="stSidebarContent"] {{ padding-top:14px; }}
h1,h2,h3,h4 {{ color:var(--ink); }}

/* ---- 카드 ---- */
[class*="st-key-card_"] {{
  background:#fff; border:1px solid var(--line) !important; border-radius:16px;
  padding:4px 16px 14px; box-shadow:0 1px 3px rgba(20,40,30,.06);
}}
.ct {{ font-size:14px; font-weight:800; color:var(--ink); margin:8px 0 2px; }}
.cs {{ font-size:11.5px; color:var(--sub); margin:0 0 8px; }}
.sec {{ font-size:17px; font-weight:800; color:var(--ink); border-left:4px solid var(--acc);
        padding-left:10px; margin:2px 0 14px; }}
.nn {{ color:var(--sub); font-size:12.5px; padding:16px 2px; }}

/* ---- 머리글 ---- */
.hd {{ font-size:21px; font-weight:800; color:var(--ink); letter-spacing:-.4px; }}
.hdc {{ font-size:12px; color:var(--sub); margin-top:2px; }}

/* ---- 상단 탭 ---- */
[class*="st-key-top_"] button {{
  background:transparent !important; border:none !important; border-radius:0 !important;
  border-bottom:2px solid transparent !important; color:var(--sub) !important;
  font-weight:600 !important; padding:7px 2px !important; font-size:13.5px !important;
}}
[class*="st-key-top_"] button:hover {{ color:var(--ink) !important; }}
[class*="st-key-top_{TOP_IDX}"] button {{
  color:var(--deep) !important; font-weight:800 !important;
  border-bottom:2px solid var(--acc) !important;
}}

/* ---- 알람 배너 ---- */
.alm {{ border-radius:14px; padding:12px 16px; margin:4px 0 16px;
        display:flex; gap:14px; align-items:center; flex-wrap:wrap; }}
.alm.crit {{ background:#fdecea; border:1px solid #f3c4bd; }}
.alm.warn {{ background:#fdf6e9; border:1px solid #efdcb2; }}
.alm.ok   {{ background:var(--mint); border:1px solid #bfe6d6; }}
.alm .ic {{ font-size:19px; line-height:1; }}
.alm .m  {{ font-size:14.5px; font-weight:800; color:var(--ink); }}
.alm .d  {{ font-size:12px; color:var(--sub); margin-top:2px; }}
.alm .sp {{ margin-left:auto; display:flex; gap:18px; }}
.alm .sp div {{ text-align:right; }}
.alm .sp .n {{ font-size:18px; font-weight:800; color:var(--ink); }}
.alm .sp .l {{ font-size:11px; color:var(--sub); }}
.alm.crit .sp .n.r {{ color:var(--red); }}

/* ---- KPI ---- */
.kpis {{ display:grid; grid-template-columns:repeat(4,1fr); gap:12px; margin-bottom:4px; }}
@media (max-width:1180px) {{ .kpis {{ grid-template-columns:repeat(2,1fr); }} }}
.kp {{ background:#fff; border:1px solid var(--line); border-radius:16px;
       padding:14px 16px 13px; box-shadow:0 1px 3px rgba(20,40,30,.06); }}
.kp .t {{ font-size:12.5px; color:var(--sub); font-weight:600; line-height:1.35; min-height:34px; }}
.kp .v {{ font-size:27px; font-weight:800; color:var(--ink); letter-spacing:-.6px; margin-top:6px; }}
.kp .u {{ font-size:13px; font-weight:700; color:var(--sub); margin-left:2px; }}
.kp .s {{ font-size:11.5px; color:var(--sub); margin-top:4px; }}
.kp .up {{ color:var(--red); font-weight:700; }}
.kp .dn {{ color:var(--acc); font-weight:700; }}

/* ---- 표 ---- */
.txw {{ overflow-x:auto; }}
table.tx {{ border-collapse:collapse; width:100%; font-size:12.5px; }}
table.tx th {{ background:#f3f6f5; color:var(--sub); font-weight:700; text-align:left;
               padding:7px 9px; border-bottom:1px solid var(--line); white-space:nowrap; }}
table.tx td {{ padding:7px 9px; border-bottom:1px solid #eef1f0; color:var(--ink);
               white-space:nowrap; }}
table.tx tr:last-child td {{ border-bottom:none; }}
table.tx td.r, table.tx th.r {{ text-align:right; }}
.bd {{ display:inline-block; padding:1px 7px; border-radius:999px; font-size:11px; font-weight:700; }}
.bd.hv {{ background:#fdecea; color:var(--red); }}
.bd.wt {{ background:#fdf3e2; color:var(--amber); }}
.bd.lt {{ background:#eceff1; color:#546e7a; }}
.bd.ok {{ background:var(--mint); color:var(--deep); }}

/* ---- 매트릭스 / 히트맵 / 격자 ---- */
table.mx {{ border-collapse:separate; border-spacing:3px; width:100%; font-size:12px; }}
table.mx th {{ color:var(--sub); font-weight:700; font-size:11.5px; padding:4px 6px;
               text-align:center; white-space:nowrap; }}
table.mx th.lf {{ text-align:left; }}
table.mx td {{ padding:7px 8px; text-align:center; border-radius:8px; background:#f7faf9;
               color:var(--ink); white-space:nowrap; }}
table.mx td.lf {{ text-align:left; background:#fff; font-weight:600; font-size:11.5px; }}
.gd td small {{ display:block; color:var(--sub); font-size:10.5px; font-weight:600; }}
.gd td.on small {{ color:rgba(255,255,255,.85); }}

/* ---- 사이드바 ---- */
.brand {{ display:flex; align-items:center; gap:9px; margin:0 0 12px; }}
.brand .bi {{ width:28px; height:28px; border-radius:9px; display:flex; align-items:center;
              justify-content:center; background:linear-gradient(135deg,var(--acc),var(--deep));
              color:#fff; font-size:14px; }}
.brand .bt {{ font-size:13.5px; font-weight:800; color:var(--ink); line-height:1.2; }}
.brand .bs {{ font-size:10.5px; color:var(--sub); }}
.hero {{ background:linear-gradient(135deg,var(--acc),var(--deep)); color:#fff;
         border-radius:14px; padding:12px 14px; margin:0 0 12px; }}
.hero .hl {{ font-size:10.5px; opacity:.88; font-weight:700; letter-spacing:.2px; }}
.hero .hv {{ font-size:20px; font-weight:800; margin-top:1px; }}
.hero .hs {{ font-size:11px; opacity:.92; margin-top:5px; line-height:1.5; }}
.fn {{ font-size:11px; color:var(--sub); line-height:1.65; border-top:1px solid var(--line);
       padding-top:9px; margin-top:4px; }}
.fn b {{ color:var(--ink); }}
section[data-testid="stSidebar"] label p {{ font-size:11.5px !important; font-weight:700; color:var(--sub); }}

/* ---- segmented / 위젯 ---- */
[data-testid="stSegmentedControl"] button[aria-checked="true"],
div[role="radiogroup"] label[data-checked="true"] {{ background:var(--mint) !important; }}
[data-testid="stSegmentedControl"] button[aria-checked="true"] p {{
  color:var(--deep) !important; font-weight:800 !important; }}
{"" if IS_CARD else '[data-testid="stMainBlockContainer"]{background:#fff;border:1px solid '
 + C.LINE + ';border-radius:18px;box-shadow:0 1px 3px rgba(20,40,30,.06);margin-top:10px;}'}
</style>""", unsafe_allow_html=True)


# ============================================================ 조회
@st.cache_data(ttl=300, show_spinner=False)
def get_data(a: date, b: date) -> pd.DataFrame:
    return load_raw(a, b)


TODAY = date.today()

# ============================================================ 사이드바
sb = st.sidebar
sb.markdown(
    "<div class='brand'><div class='bi'>📐</div><div>"
    "<div class='bt'>계측 사전 지정 부하 모니터</div>"
    "<div class='bs'>Manual 과부하 사전 감지</div></div></div>",
    unsafe_allow_html=True)
hero_slot = sb.empty()

f_line = sb.multiselect("LINEID", ["M1A", "M1B", "M2A"], key="f_line",
                        placeholder="전체")
f_eqp = sb.multiselect("EQP TYPE", C.EQP_ALL, key="f_eqp", placeholder="전체")

_dr = sb.date_input("데이터 조회 기간",
                    value=(TODAY - timedelta(days=C.DEFAULT_DAYS - 1), TODAY),
                    max_value=TODAY, key="drange", format="YYYY-MM-DD")
if isinstance(_dr, (tuple, list)) and len(_dr) == 2:
    d_from, d_to = _dr[0], _dr[1]
elif isinstance(_dr, (tuple, list)) and len(_dr) == 1:
    d_from = d_to = _dr[0]
else:
    d_from = d_to = _dr
if d_from > d_to:
    d_from, d_to = d_to, d_from
short = (d_to - d_from).days + 1 < C.MIN_DAYS
if short:                                  # 사전 지정 관리 단위는 최소 3일
    d_from = d_to - timedelta(days=C.MIN_DAYS - 1)
N_DAYS = (d_to - d_from).days + 1
if short:
    sb.caption(f"최소 {C.MIN_DAYS}일로 늘려 조회합니다.")

with sb.expander("추가 필터", expanded=False):
    f_dept = st.multiselect("요청 부서", DEPT_ALL, key="f_dept", placeholder="전체")
    f_rsn = st.multiselect("사전 지정 사유", C.REASONS, key="f_rsn", placeholder="전체")

sb.markdown("<div style='height:4px'></div>", unsafe_allow_html=True)
THR = sb.number_input("총측정시간 알람 임계 (분)", min_value=10, max_value=1200,
                      value=int(C.ALARM_THR_MIN), step=10, key="thr",
                      help="LOT 의 사전 지정 총측정시간 합이 이 값 이상이면 알람을 띄웁니다.")
ALM_PEND_ONLY = sb.checkbox("알람은 미진행(예정)만", value=True, key="alm_pend",
                            help="이미 측정이 끝난 LOT 은 조정할 수 없으므로 기본은 미진행만 봅니다.")

funnel_slot = sb.empty()
if sb.button("새로고침", key="refresh", width="stretch"):
    get_data.clear()
    st.rerun()

with sb.expander("내보내기", expanded=False):
    if st.button("PDF로 저장", key="pdfbtn", width="stretch"):
        components.html("<script>window.parent.print()</script>", height=0)
    xls_slot = st.empty()

# ============================================================ 데이터 가공
_back = max(N_DAYS, C.CMP_MIN_DAYS)
raw = get_data(d_from - timedelta(days=_back), d_to)

LINE_ALL = sorted(raw["LINEID"].dropna().unique().tolist()) if not raw.empty else []
EQP_SEL = f_eqp or C.EQP_ALL


def apply_filters(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    m = df["EQP_TYPE"].isin(EQP_SEL)
    if f_line:
        m &= df["LINEID"].isin(f_line)
    if f_dept:
        m &= df["DEPARTMENT"].isin(f_dept)
    if f_rsn:
        m &= df["사유"].isin(f_rsn)
    return df.loc[m].copy()


raw = raw.copy()
raw["일자"] = raw["요청일"].dt.normalize()
flt = apply_filters(raw)

p_from = d_from - timedelta(days=N_DAYS)
p_to = d_from - timedelta(days=1)
_d = flt["일자"].dt.date if not flt.empty else pd.Series(dtype="object")
cur = flt.loc[(_d >= d_from) & (_d <= d_to)].copy() if not flt.empty else flt.copy()
prv = flt.loc[(_d >= p_from) & (_d <= p_to)].copy() if not flt.empty else flt.copy()

MAN = C.MANUAL
live = cur[cur["상태"].ne("Cancel")].copy()        # Cancel 제외
pend = cur[cur["상태"].eq("예정")].copy()          # 미진행
man = live[live["사유"].eq(MAN)].copy()
man_pend = pend[pend["사유"].eq(MAN)].copy()


def lot_agg(df: pd.DataFrame) -> pd.DataFrame:
    """LOT 단위 총측정시간 집계. 한 LOT 에 계측 STEP 이 여러 개 걸릴 수 있다."""
    if df.empty:
        return pd.DataFrame(columns=["LOTID", "총측정시간", "건수", "매수", "요청일",
                                     "EQP_TYPE", "DEPARTMENT", "요청자", "STEP",
                                     "PPID", "사유", "승인상태", "상태", "알람"])
    g = df.groupby("LOTID", sort=False)
    out = pd.DataFrame({
        "총측정시간": g["예상APT"].sum(),
        "건수": g.size(),
        "매수": g["지정매수"].sum(),
        "요청일": g["요청일"].min(),
        "EQP_TYPE": g["EQP_TYPE"].agg(lambda s: ", ".join(sorted(set(s)))),
        "DEPARTMENT": g["DEPARTMENT"].agg(lambda s: ", ".join(sorted(set(s)))),
        "요청자": g["요청자"].agg(lambda s: ", ".join(sorted(set(s)))),
        "STEP": g.apply(lambda x: ", ".join(
            sorted({f"{a}({b})" for a, b in zip(x["STEPID"], x["STEP_SEQ"])})),
            include_groups=False),
        "PPID": g["PPID"].agg(lambda s: ", ".join(sorted(set(s)))),
        "사유": g["사유"].agg(lambda s: ", ".join(sorted(set(s)))),
        "승인상태": g["승인상태"].agg(lambda s: "요청 대기" if "요청 대기" in set(s) else "승인 완료"),
        "상태": g["상태"].agg(lambda s: "예정" if "예정" in set(s) else sorted(set(s))[0]),
    }).reset_index()
    out["알람"] = out["총측정시간"].map(lambda v: C.alarm_level(v, THR))
    return out.sort_values("총측정시간", ascending=False).reset_index(drop=True)


alm_base = pend if ALM_PEND_ONLY else live
lots = lot_agg(alm_base)
alm = lots[lots["알람"].ne("정상")].copy()
n_crit = int((lots["알람"] == "위험").sum())
n_warn = int((lots["알람"] == "주의").sum())
alm_st = float(alm["총측정시간"].sum()) if not alm.empty else 0.0

# EQP 부하율 (미진행 ST / 1일 여유 CAPA)
load_rows = []
for e in EQP_SEL:
    s = float(pend.loc[pend["EQP_TYPE"].eq(e), "예상APT"].sum())
    p = C.load_pct(s, e)
    load_rows.append({"EQP_TYPE": e, "미진행ST": s, "여유CAPA": C.free_capa_min(e),
                      "부하율": p, "판정": C.load_state(p)})
load_df = pd.DataFrame(load_rows)
OVER_EQP = load_df.loc[load_df["부하율"].ge(C.LOAD_WARN), "EQP_TYPE"].tolist() if not load_df.empty else []
need = live.loc[C.need_adjust_mask(live, THR, OVER_EQP)].copy() if not live.empty else live.copy()

# 사이드바 hero / funnel / 엑셀
hero_slot.markdown(
    f"<div class='hero'><div class='hl'>{esc(dstr(d_from))} – {esc(dstr(d_to))} · {N_DAYS}일</div>"
    f"<div class='hv'>{fh(man_pend['예상APT'].sum() if not man_pend.empty else 0)}</div>"
    f"<div class='hs'>미진행 Manual 총측정시간<br>조정 대상 <b>{len(need)}</b>건 · "
    f"임계 초과 LOT <b>{len(alm)}</b>건</div></div>", unsafe_allow_html=True)
funnel_slot.markdown(
    "<div class='fn'>"
    f"LINEID <b>{esc(', '.join(f_line) if f_line else '전체')}</b><br>"
    f"EQP TYPE <b>{esc(', '.join(f_eqp) if f_eqp else '전체')}</b><br>"
    f"요청 부서 <b>{esc(', '.join(f_dept) if f_dept else '전체')}</b><br>"
    f"사유 <b>{esc(', '.join(f_rsn) if f_rsn else '전체')}</b><br>"
    f"조회 <b>{len(cur):,}</b>건 / 미진행 <b>{len(pend):,}</b>건</div>",
    unsafe_allow_html=True)

VIEW_COLS = ["요청일", "LOTID", "SLOTID", "EQP_TYPE", "STEP_SEQ", "STEPID", "PPID",
             "DEPARTMENT", "요청자", "APT_매", "지정매수", "예상APT", "사유", "승인상태", "상태"]
VIEW_NAMES = {"EQP_TYPE": "EQP", "STEP_SEQ": "STEP SEQ", "STEPID": "STEP",
              "DEPARTMENT": "부서", "APT_매": "1매당 측정시간(분)", "지정매수": "매수",
              "예상APT": "총 측정시간(분)"}


def view(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=[VIEW_NAMES.get(c, c) for c in VIEW_COLS])
    d = df[VIEW_COLS].rename(columns=VIEW_NAMES).copy()
    d["요청일"] = pd.to_datetime(d["요청일"]).dt.strftime("%Y-%m-%d %H:%M")
    return d


xls_slot.download_button(
    "엑셀 내려받기", key="xlsdl", width="stretch",
    data=xls({"사전지정_전체": view(cur), "임계초과_LOT": alm, "조정대상": view(need),
              "EQP부하": load_df}),
    file_name=f"precheck_{d_from:%Y%m%d}_{d_to:%Y%m%d}.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

# ============================================================ 머리글 + 상단 탭
st.markdown(
    f"<div class='hd'>계측 사전 지정 부하 모니터</div>"
    f"<div class='hdc'>조회 {esc(dstr(d_from))} – {esc(dstr(d_to))} ({N_DAYS}일) · "
    f"총측정시간 알람 임계 {THR:,}분 ({fh(THR)}) · "
    f"마지막 갱신 {pd.Timestamp.now():%Y-%m-%d %H:%M}</div>",
    unsafe_allow_html=True)


def _go_extra():
    v = st.session_state.get("extra_pick")
    if v and v != EXTRA_HEAD:
        st.session_state["nav"] = v


tcols = st.columns([1.1, 2.2, 1.2, 1.5], gap="small", vertical_alignment="center")
for i, name in enumerate(TOPS):
    if tcols[i].button(name, key=f"top_{i}", width="stretch"):
        st.session_state["nav"] = name
        st.session_state["extra_pick"] = EXTRA_HEAD
        st.rerun()
tcols[3].selectbox("기타 분석", EXTRA, key="extra_pick", on_change=_go_extra,
                   label_visibility="collapsed")
st.markdown(f"<div style='border-top:1px solid {C.LINE};margin:0 0 14px'></div>",
            unsafe_allow_html=True)

# ============================================================ 알람 배너
if len(alm) == 0:
    kls, ic, msg = "ok", "✅", f"총측정시간 {THR:,}분 이상 사전 지정 LOT 없음"
    desc = "현재 조회 구간에서 임계를 넘는 LOT 이 없습니다."
elif n_crit > 0:
    kls, ic = "crit", "🚨"
    msg = f"총측정시간 임계 초과 사전 지정 LOT {len(alm):,}건 — 위험 {n_crit:,}건"
    desc = (f"위험 = {THR * C.ALARM_CRIT_MULT:,.0f}분 이상. "
            f"{'미진행(예정)' if ALM_PEND_ONLY else 'Cancel 제외 전체'} 기준")
else:
    kls, ic = "warn", "⚠️"
    msg = f"총측정시간 임계 초과 사전 지정 LOT {len(alm):,}건 — 주의"
    desc = f"{'미진행(예정)' if ALM_PEND_ONLY else 'Cancel 제외 전체'} 기준 · 임계 {THR:,}분"

_top_dept = _top_user = "-"
if not alm.empty:
    _dd = alm["DEPARTMENT"].str.split(", ").explode().value_counts()
    _uu = alm["요청자"].str.split(", ").explode().value_counts()
    if len(_dd):
        _top_dept = f"{_dd.index[0]} ({int(_dd.iloc[0])}건)"
    if len(_uu):
        _top_user = f"{_uu.index[0]} ({int(_uu.iloc[0])}건)"

st.markdown(
    f"<div class='alm {kls}'><div class='ic'>{ic}</div>"
    f"<div><div class='m'>{esc(msg)}</div><div class='d'>{esc(desc)}</div></div>"
    f"<div class='sp'>"
    f"<div><div class='n r'>{n_crit:,}</div><div class='l'>위험</div></div>"
    f"<div><div class='n'>{n_warn:,}</div><div class='l'>주의</div></div>"
    f"<div><div class='n'>{fh(alm_st)}</div><div class='l'>초과 LOT ST 합</div></div>"
    f"<div><div class='n' style='font-size:13px'>{esc(_top_dept)}</div>"
    f"<div class='l'>최다 요청 부서</div></div>"
    f"<div><div class='n' style='font-size:13px'>{esc(_top_user)}</div>"
    f"<div class='l'>최다 요청자</div></div>"
    f"</div></div>", unsafe_allow_html=True)


# ============================================================ 색 보간
def mix(v: float, vmax: float, lo=(243, 248, 246), hi=(18, 163, 122)) -> tuple[str, str]:
    t = 0.0 if vmax <= 0 else min(max(float(v) / float(vmax), 0.0), 1.0)
    rgb = tuple(int(lo[i] + (hi[i] - lo[i]) * t) for i in range(3))
    return f"rgb({rgb[0]},{rgb[1]},{rgb[2]})", ("#ffffff" if t > 0.55 else C.INK)


WD = ["월", "화", "수", "목", "금", "토", "일"]


def daylabel(ts) -> str:
    t = pd.Timestamp(ts)
    return f"{t:%m/%d} ({WD[t.weekday()]})"


def row_badges(r) -> str:
    out = []
    if float(r["예상APT"]) >= THR:
        out.append(bd("hv", "고부하"))
    if str(r["승인상태"]) == "요청 대기":
        out.append(bd("wt", "승인 대기"))
    if str(r["상태"]) == "예정" and (TODAY - r["요청일"].date()).days >= C.STALE_DAYS:
        out.append(bd("lt", "지연"))
    return " ".join(out) if out else bd("ok", "정상")


# ============================================================ 탭 1. 전체 현황
if PAGE == TOPS[0]:

    def kpi_vals(df: pd.DataFrame):
        if df.empty:
            return 0, 0, 0.0, 0
        lv = df[df["상태"].ne("Cancel")]
        m = lv[lv["사유"].eq(MAN)]
        k1 = int(m["LOTID"].nunique())
        k2 = int(m.loc[m["예상APT"].ge(THR), "PPID"].nunique())
        mp = m[m["상태"].eq("예정") & m["예상APT"].ge(THR)]
        k3 = float(mp["예상APT"].sum())
        k4 = int(lv.loc[lv["예상APT"].ge(THR), "PPID"].nunique())
        return k1, k2, k3, k4

    c1, c2, c3, c4 = kpi_vals(cur)
    p1, p2, p3, p4 = kpi_vals(prv)

    def dlt(c: float, p: float, unit: str = "") -> str:
        d = float(c) - float(p)
        if abs(d) < 0.05:
            return f"<span style='color:{C.SUB}'>직전 {N_DAYS}일 대비 변동 없음</span>"
        k, a = ("up", "▲") if d > 0 else ("dn", "▼")
        n = f"{abs(d):,.1f}" if unit == "h" else f"{abs(d):,.0f}"
        return f"<span class='{k}'>{a} {n}{unit}</span> 직전 {N_DAYS}일 대비"

    cap_all = C.free_capa_min_multi(EQP_SEL)
    pct3 = (c3 / cap_all * 100.0) if cap_all > 0 else 0.0
    st.markdown(
        "<div class='kpis'>"
        f"<div class='kp'><div class='t'>Manual 사전 지정 LOT</div>"
        f"<div class='v'>{c1:,}<span class='u'>LOT</span></div>"
        f"<div class='s'>{dlt(c1, p1)}</div></div>"
        f"<div class='kp'><div class='t'>Manual 사전 지정 고부하 PPID<br>"
        f"<span style='font-weight:500'>(총측정시간 {THR:,}분 이상)</span></div>"
        f"<div class='v'>{c2:,}<span class='u'>종</span></div>"
        f"<div class='s'>{dlt(c2, p2)}</div></div>"
        f"<div class='kp'><div class='t'>Manual 계측 예정 고부하 LOT 예상 ST</div>"
        f"<div class='v'>{c3 / 60:,.1f}<span class='u'>h</span></div>"
        f"<div class='s'>여유 CAPA 대비 <b>{pct3:,.1f}%</b> · {dlt(c3 / 60, p3 / 60, 'h')}</div></div>"
        f"<div class='kp'><div class='t'>고부하 PPID (전체 사유)</div>"
        f"<div class='v'>{c4:,}<span class='u'>종</span></div>"
        f"<div class='s'>{dlt(c4, p4)}</div></div>"
        "</div>", unsafe_allow_html=True)

    # ---- 추이 ----
    tc = card(st, "trend")
    tc.markdown("<div class='ct'>사전 지정 추이</div>"
                f"<div class='cs'>{C.period_unit(N_DAYS)} 단위 · "
                f"{'일별' if C.trend_freq(N_DAYS) == 'D' else '주별'} 집계</div>",
                unsafe_allow_html=True)
    sc1, sc2, _ = tc.columns([1.1, 1.5, 3])
    t_scope = seg(sc1, "범위", ["전체", "Manual"], "t_scope")
    t_metric = seg(sc2, "지표", ["ST(h)", "LOT 수", "매수"], "t_metric")

    if live.empty:
        empty_note(tc)
    else:
        d = live.copy()
        d["구분"] = d["사유"].where(d["사유"].eq(MAN), "기타")
        if t_scope == "Manual":
            d = d[d["구분"].eq(MAN)]
        freq = C.trend_freq(N_DAYS)
        d["버킷"] = d["일자"].dt.to_period("D" if freq == "D" else "W").dt.start_time
        if t_metric == "ST(h)":
            g = d.groupby(["버킷", "구분"], sort=True)["예상APT"].sum().div(60).reset_index(name="값")
            ytit = "총측정시간 (h)"
        elif t_metric == "LOT 수":
            g = d.groupby(["버킷", "구분"], sort=True)["LOTID"].nunique().reset_index(name="값")
            ytit = "LOT 수"
        else:
            g = d.groupby(["버킷", "구분"], sort=True)["지정매수"].sum().reset_index(name="값")
            ytit = "지정 매수"
        if g.empty:
            empty_note(tc)
        else:
            fig = px.bar(g, x="버킷", y="값", color="구분",
                         color_discrete_map={MAN: C.C1, "기타": C.C2},
                         category_orders={"구분": [MAN, "기타"]})
            fig.update_xaxes(tickformat="%m/%d")
            fig.update_yaxes(title_text=ytit)
            chart(tc, lay(fig, 268, legend=True), "f_trend")

    # ---- 매트릭스 ----
    mc = card(st, "matrix")
    if not f_eqp:
        mc.markdown("<div class='ct'>EQP TYPE × 사전 지정 사유 총측정시간</div>"
                    "<div class='cs'>상위 25% 칸을 진하게 표시합니다. "
                    "EQP TYPE 을 고르면 STEP·PPID 단위로 바뀝니다.</div>",
                    unsafe_allow_html=True)
        if live.empty:
            empty_note(mc)
        else:
            pv = (live.pivot_table(index="EQP_TYPE", columns="사유", values="예상APT",
                                   aggfunc="sum", fill_value=0.0)
                  .reindex(index=EQP_SEL).reindex(columns=C.REASONS).fillna(0.0))
            vals = pv.to_numpy().ravel()
            nz = vals[vals > 0]
            q = float(pd.Series(nz).quantile(0.75)) if nz.size else 0.0
            vmax = float(vals.max()) if vals.size else 0.0
            head = "<th class='lf'>EQP TYPE</th>" + "".join(f"<th>{esc(c)}</th>" for c in pv.columns) + "<th>합계</th>"
            body = ""
            for idx, r in pv.iterrows():
                tds = ""
                for v in r:
                    if v >= q and v > 0:
                        b, fg = mix(v, vmax)
                        tds += f"<td style='background:{b};color:{fg};font-weight:700'>{fh(v)}</td>"
                    else:
                        tds += f"<td>{fh(v) if v > 0 else '-'}</td>"
                tds += f"<td style='background:#fff;font-weight:800'>{fh(r.sum())}</td>"
                body += f"<tr><td class='lf'>{esc(idx)}</td>{tds}</tr>"
            mc.markdown(f"<div class='txw'><table class='mx'><thead><tr>{head}</tr></thead>"
                        f"<tbody>{body}</tbody></table></div>", unsafe_allow_html=True)
    else:
        mc.markdown("<div class='ct'>STEP · PPID × 사전 지정 사유 총측정시간</div>"
                    f"<div class='cs'>{esc(', '.join(f_eqp))} · Manual 총측정시간 상위 8개</div>",
                    unsafe_allow_html=True)
        if live.empty:
            empty_note(mc)
        else:
            d = live.copy()
            d["행"] = d["STEPID"] + " (" + d["STEP_SEQ"] + ") · " + d["PPID"]
            pv = d.pivot_table(index="행", columns="사유", values="예상APT",
                               aggfunc="sum", fill_value=0.0).reindex(columns=C.REASONS).fillna(0.0)
            pv = pv.sort_values(MAN, ascending=False).head(8)
            if pv.empty:
                empty_note(mc)
            else:
                mmax = float(pv[MAN].max())
                head = "<th class='lf'>STEP (SEQ) · PPID</th>" + "".join(
                    f"<th>{esc(c)}</th>" for c in pv.columns) + "<th>합계</th>"
                body = ""
                for idx, r in pv.iterrows():
                    tds = ""
                    for cname, v in r.items():
                        if cname == MAN and v > 0:
                            b, fg = mix(v, mmax)
                            tds += f"<td style='background:{b};color:{fg};font-weight:700'>{fh(v)}</td>"
                        else:
                            tds += f"<td>{fh(v) if v > 0 else '-'}</td>"
                    tds += f"<td style='background:#fff;font-weight:800'>{fh(r.sum())}</td>"
                    body += f"<tr><td class='lf'>{esc(idx)}</td>{tds}</tr>"
                mc.markdown(f"<div class='txw'><table class='mx'><thead><tr>{head}</tr></thead>"
                            f"<tbody>{body}</tbody></table></div>", unsafe_allow_html=True)

    # ---- 조정이 필요한 LOT ----
    nc = card(st, "need")
    nc.markdown("<div class='ct'>조정이 필요한 LOT</div>"
                f"<div class='cs'>미진행 중 총측정시간 {THR:,}분 이상, 또는 부하 주의·과부하 "
                f"EQP 의 Manual 중 {THR / 4:,.0f}분 이상 · 총측정시간 내림차순 상위 20건</div>",
                unsafe_allow_html=True)
    if need.empty:
        empty_note(nc, "조정이 필요한 LOT 이 없습니다.")
    else:
        nd = need.sort_values("예상APT", ascending=False).head(20)
        rows = [[
            f"{r['요청일']:%m/%d %H:%M}", esc(r["LOTID"]), esc(r["SLOTID"]),
            esc(r["EQP_TYPE"]), esc(r["STEP_SEQ"]), esc(r["STEPID"]), esc(r["PPID"]),
            esc(r["DEPARTMENT"]), esc(r["요청자"]),
            f"<span class='r'>{r['APT_매']:,.1f}</span>", f"{int(r['지정매수'])}",
            f"<b>{r['예상APT']:,.0f}</b>", esc(r["사유"]), row_badges(r),
        ] for _, r in nd.iterrows()]
        nc.markdown(tx_table(rows, ["요청일", "LOTID", "SLOTID", "EQP", "STEP SEQ", "STEP",
                                    "PPID", "부서", "요청자", "1매 ST(분)", "매수",
                                    "총 ST(분)", "사유", "상태"]),
                    unsafe_allow_html=True)


# ============================================ 탭 2. 부서별 Manual 사전 지정 현황
elif PAGE == TOPS[1]:
    a, b = st.columns(2, gap="small")

    # ---- 부서별 집계 ----
    dc = card(a, "dept")
    dc.markdown("<div class='ct'>부서별 사전 지정 총측정시간</div>", unsafe_allow_html=True)
    d_scope = seg(dc, "범위", [MAN, "전체"], "d_scope")
    if live.empty:
        empty_note(dc)
    else:
        d = live.copy()
        d["구분"] = d["사유"].where(d["사유"].eq(MAN), "기타")
        if d_scope == MAN:
            d = d[d["구분"].eq(MAN)]
        g = d.groupby(["DEPARTMENT", "구분"])["예상APT"].sum().div(60).reset_index(name="ST")
        if g.empty:
            empty_note(dc)
        else:
            order = (g.groupby("DEPARTMENT")["ST"].sum()
                     .sort_values(ascending=False).index.tolist())
            fig = px.bar(g, x="DEPARTMENT", y="ST", color="구분",
                         color_discrete_map={MAN: C.C1, "기타": C.C2},
                         category_orders={"DEPARTMENT": order, "구분": [MAN, "기타"]})
            fig.update_yaxes(title_text="총측정시간 (h)")
            chart(dc, lay(fig, 272, legend=True), "f_dept")

    # ---- 요청자별 ----
    uc = card(b, "user")
    uc.markdown("<div class='ct'>요청자별 사전 지정 총측정시간</div>"
                "<div class='cs'>상위 10명 · Manual 과 기타를 나눠 쌓았습니다.</div>",
                unsafe_allow_html=True)
    if live.empty:
        empty_note(uc)
    else:
        d = live.copy()
        d["구분"] = d["사유"].where(d["사유"].eq(MAN), "기타")
        g = d.groupby(["요청자", "구분"])["예상APT"].sum().div(60).reset_index(name="ST")
        tot = g.groupby("요청자")["ST"].sum()
        g = g[g["요청자"].isin(tot.sort_values(ascending=False).head(10).index)].copy()
        if g.empty:
            empty_note(uc)
        else:
            g["_t"] = g["요청자"].map(tot)
            g = g.sort_values(["_t", "구분"], ascending=[False, True])
            fig = px.bar(g, x="ST", y="요청자", orientation="h", color="구분",
                         color_discrete_map={MAN: C.C1, "기타": C.C2},
                         category_orders={"구분": [MAN, "기타"]})
            fig.update_yaxes(autorange="reversed")
            fig.update_xaxes(title_text="총측정시간 (h)")
            chart(uc, lay(fig, 300, legend=True), "f_user")

    # ---- Manual 요청 현황 ----
    rc = card(st, "mreq")
    rc.markdown("<div class='ct'>Manual 요청 현황</div>"
                "<div class='cs'>STEP · PPID · 부서 · 요청자로 묶은 총측정시간 상위 12건</div>",
                unsafe_allow_html=True)
    rq1, rq2, _ = rc.columns([2.2, 1.1, 1.6])
    mreq_dept = rq1.multiselect("부서", DEPT_ALL, key="mreq_dept", placeholder="전체")
    mreq_long = rq2.checkbox(f"장시간만 ({THR:,}분↑)", key="mreq_long")
    if man.empty:
        empty_note(rc, "Manual 사전 지정 내역이 없습니다.")
    else:
        d = man.copy()
        if mreq_dept:
            d = d[d["DEPARTMENT"].isin(mreq_dept)]
        if mreq_long:
            d = d[d["예상APT"].ge(THR)]
        g = (d.groupby(["STEPID", "STEP_SEQ", "PPID", "DEPARTMENT", "요청자"])
             .agg(ST=("예상APT", "sum"), 건수=("LOTID", "nunique"), 매수=("지정매수", "sum"))
             .reset_index().sort_values("ST", ascending=False).head(12))
        if g.empty:
            empty_note(rc, "선택한 조건의 Manual 요청이 없습니다.")
        else:
            g = g.reset_index(drop=True)
            # 같은 라벨이 겹치면 plotly 가 하나로 합치므로 보이지 않는 공백을 덧붙인다
            g["라벨"] = [f"{r.STEPID} ({r.STEP_SEQ}) · {r.PPID} · {r.DEPARTMENT} · {r['요청자']}"
                       + " " * i for i, r in g.iterrows()]
            g["ST_h"] = g["ST"] / 60.0
            fig = px.bar(g, x="ST_h", y="라벨", orientation="h",
                         custom_data=["건수", "매수", "ST"])
            fig.update_traces(marker_color=C.C1,
                              hovertemplate="%{y}<br>총측정시간 %{customdata[2]:,.0f}분"
                                            "<br>LOT %{customdata[0]}건 · %{customdata[1]}매<extra></extra>")
            fig.update_yaxes(autorange="reversed", tickfont=dict(size=10.5))
            fig.update_xaxes(title_text="총측정시간 (h)")
            fig.update_layout(margin=dict(l=8, r=8, t=12, b=8))
            chart(rc, lay(fig, 30 * len(g) + 70), "f_mreq")

    # ---- 장시간 Manual LOT 히트맵 ----
    hc = card(st, "heat")
    hc.markdown("<div class='ct'>장시간 Manual LOT 분포</div>"
                "<div class='cs'>기준 이상 LOT 만 · 행은 총측정시간 상위 10개 PPID</div>",
                unsafe_allow_html=True)
    hq1, _ = hc.columns([1.2, 4])
    long_thr = hq1.number_input("기준 (분)", min_value=10, max_value=1200,
                                value=int(THR), step=10, key="long_thr")
    d = man[man["예상APT"].ge(long_thr)].copy() if not man.empty else man.copy()
    if d.empty:
        empty_note(hc, f"{long_thr:,}분 이상 Manual 사전 지정이 없습니다.")
    else:
        if N_DAYS <= 14:
            d["열"] = d["일자"].map(daylabel)
            cols = [daylabel(x) for x in pd.date_range(d_from, d_to, freq="D")]
        else:
            d["열"] = d["일자"].dt.to_period("W").dt.start_time.map(lambda t: f"{t:%m/%d}주")
            cols = sorted(d["열"].unique().tolist(),
                          key=lambda s: pd.Timestamp(f"{d_to.year}/{s[:5]}"))
        rows_i = (d.groupby("PPID")["예상APT"].sum().sort_values(ascending=False).head(10).index.tolist())
        pv = (d.pivot_table(index="PPID", columns="열", values="예상APT", aggfunc="sum",
                            fill_value=0.0).reindex(index=rows_i).reindex(columns=cols).fillna(0.0))
        vmax = float(pv.to_numpy().max()) if pv.size else 0.0
        head = "<th class='lf'>PPID</th>" + "".join(f"<th>{esc(c)}</th>" for c in pv.columns)
        body = ""
        for idx, r in pv.iterrows():
            tds = ""
            for v in r:
                if v <= 0:
                    tds += "<td style='background:#fafbfb;color:#c3cbc8'>-</td>"
                elif v >= long_thr * 2:
                    bgc, fg = mix(v, vmax)
                    tds += f"<td style='background:{bgc};color:{fg};font-weight:800'>{v:,.0f}</td>"
                else:
                    tds += f"<td>{v:,.0f}</td>"
            body += f"<tr><td class='lf'>{esc(idx)}</td>{tds}</tr>"
        hc.markdown(f"<div class='txw'><table class='mx'><thead><tr>{head}</tr></thead>"
                    f"<tbody>{body}</tbody></table></div>"
                    f"<div class='cs' style='margin-top:6px'>칸 숫자는 총측정시간(분) 합. "
                    f"{long_thr * 2:,}분 이상을 진하게 표시합니다.</div>",
                    unsafe_allow_html=True)

    # ---- 일별 최대 ST STEP · PPID ----
    gc = card(st, "grid")
    gc.markdown("<div class='ct'>일별 최대 총측정시간 STEP · PPID</div>"
                "<div class='cs'>그날 그 EQP TYPE 에서 STEP+PPID 별 총측정시간 합이 가장 큰 항목</div>",
                unsafe_allow_html=True)
    if live.empty:
        empty_note(gc)
    else:
        d = live.copy()
        g = (d.groupby(["일자", "EQP_TYPE", "STEPID", "STEP_SEQ", "PPID"])
             .agg(ST=("예상APT", "sum"), 매수=("지정매수", "sum"),
                  LOT=("LOTID", "nunique"),
                  사유=("사유", lambda s: "/".join(sorted(set(s)))))
             .reset_index())
        g = g.set_index(["일자", "EQP_TYPE", "STEPID", "STEP_SEQ", "PPID"], drop=False)
        g = g.sort_values("ST", ascending=False)
        days = sorted(d["일자"].unique())[-14:]
        single = len(EQP_SEL) == 1
        headers = ["1위", "2위", "3위"] if single else EQP_SEL
        body = ""
        for day in days:
            tds = ""
            if single:
                sub = g[(g["일자"] == day) & (g["EQP_TYPE"] == EQP_SEL[0])].head(3)
                picks = [sub.iloc[i] if i < len(sub) else None for i in range(3)]
            else:
                picks = []
                for e in EQP_SEL:
                    sub = g[(g["일자"] == day) & (g["EQP_TYPE"] == e)]
                    picks.append(sub.iloc[0] if len(sub) else None)
            for p in picks:
                if p is None:
                    tds += "<td style='background:#fafbfb;color:#c3cbc8'>-</td>"
                    continue
                on = float(p["ST"]) >= C.HEAVY_LOT_MIN
                stl = (f"background:{C.C1};color:#fff;font-weight:700" if on
                       else "background:#f7faf9")
                tip = esc(f"{p['사유']} · LOT {int(p['LOT'])}건 · {int(p['매수'])}매")
                tds += (f"<td class='{'on' if on else ''}' style='{stl}' title='{tip}'>"
                        f"{esc(p['STEPID'])} ({esc(p['STEP_SEQ'])})"
                        f"<small>{esc(p['PPID'])} · {float(p['ST']):,.0f}분</small></td>")
            body += f"<tr><td class='lf'>{esc(daylabel(day))}</td>{tds}</tr>"
        head = "<th class='lf'>날짜</th>" + "".join(f"<th>{esc(h)}</th>" for h in headers)
        gc.markdown(f"<div class='txw'><table class='mx gd'><thead><tr>{head}</tr></thead>"
                    f"<tbody>{body}</tbody></table></div>"
                    f"<div class='cs' style='margin-top:6px'>진한 칸 = 총측정시간 "
                    f"{C.HEAVY_LOT_MIN:,}분 이상. 칸에 마우스를 올리면 사유·LOT·매수가 보입니다.</div>",
                    unsafe_allow_html=True)


# ============================================================ 탭 3. LOT 상세 조회
elif PAGE == TOPS[2]:
    st.markdown("<div class='sec'>LOT 상세 조회</div>", unsafe_allow_html=True)
    q1, q2, q3 = st.columns([2.2, 1.6, 1.2])
    lot_q = q1.text_input("LOTID · PPID · STEP 검색", key="lot_q",
                          placeholder="예: N2610 / CDM_GATE / GATE_AEI_CD / 0420")
    lot_rsn = q2.multiselect("사유", C.REASONS, key="lot_rsn", placeholder="전체")
    lot_long = q3.checkbox(f"장시간만 ({THR:,}분↑)", key="lot_long")
    v1, v2, v3 = st.columns([2.6, 2.0, 1.2])
    lot_view = v1.radio("보기", ["전체", "미진행", "지연", "승인 대기", "완료", "Cancel"],
                        key="lot_view", horizontal=True)
    lot_eqp = v2.radio("EQP TYPE", ["전체"] + EQP_SEL, key="lot_eqp", horizontal=True)
    lot_unit = seg(v3, "단위", ["STEP 단위", "LOT 단위"], "lot_unit")

    d = cur.copy()
    if lot_q.strip():
        k = lot_q.strip().upper()
        d = d[d["LOTID"].str.upper().str.contains(k, na=False)
              | d["PPID"].str.upper().str.contains(k, na=False)
              | d["STEPID"].str.upper().str.contains(k, na=False)
              | d["STEP_SEQ"].astype(str).str.contains(k, na=False)]
    if lot_rsn:
        d = d[d["사유"].isin(lot_rsn)]
    if lot_long:
        d = d[d["예상APT"].ge(THR)]
    if lot_eqp != "전체":
        d = d[d["EQP_TYPE"].eq(lot_eqp)]
    if not d.empty:
        _late = d["상태"].eq("예정") & d["요청일"].dt.date.map(
            lambda x: (TODAY - x).days >= C.STALE_DAYS)
        if lot_view == "미진행":
            d = d[d["상태"].eq("예정")]
        elif lot_view == "지연":
            d = d[_late]
        elif lot_view == "승인 대기":
            d = d[d["승인상태"].eq("요청 대기")]
        elif lot_view == "완료":
            d = d[d["상태"].eq("완료")]
        elif lot_view == "Cancel":
            d = d[d["상태"].eq("Cancel")]
    d = d.sort_values("예상APT", ascending=False)

    st.caption(f"조회 결과 {len(d):,}건 · LOT {d['LOTID'].nunique() if not d.empty else 0:,}개 · "
               f"총측정시간 합 {fh(d['예상APT'].sum() if not d.empty else 0)}")

    if d.empty:
        empty_note(st)
    elif lot_unit == "LOT 단위":
        la = lot_agg(d[d["상태"].ne("Cancel")])
        if la.empty:
            empty_note(st)
        else:
            show = la[["LOTID", "알람", "총측정시간", "건수", "매수", "EQP_TYPE", "STEP",
                       "PPID", "DEPARTMENT", "요청자", "승인상태", "상태", "요청일"]].copy()
            show["요청일"] = show["요청일"].dt.strftime("%Y-%m-%d %H:%M")
            show = show.rename(columns={"EQP_TYPE": "EQP", "DEPARTMENT": "부서",
                                        "총측정시간": "총 측정시간(분)"})

            def _alm_row(r):
                if r["알람"] == "위험":
                    return [f"background-color:#fdecea;color:{C.RED}"] * len(r)
                if r["알람"] == "주의":
                    return [f"background-color:#fdf6e9;color:{C.AMBER}"] * len(r)
                return [""] * len(r)

            st.dataframe(show.style.apply(_alm_row, axis=1)
                         .format({"총 측정시간(분)": "{:,.0f}"}),
                         width="stretch", hide_index=True, height=520)
            st.caption(f"알람 = LOT 의 사전 지정 총측정시간 합 기준 "
                       f"(주의 {THR:,}분↑ / 위험 {THR * C.ALARM_CRIT_MULT:,.0f}분↑)")
    else:
        show = view(d)
        late = (d["상태"].eq("예정") & d["요청일"].dt.date.map(
            lambda x: (TODAY - x).days >= C.STALE_DAYS)).to_numpy()
        wait = d["승인상태"].eq("요청 대기").to_numpy()

        def _row(r):
            i = show.index.get_loc(r.name)
            if late[i]:
                return [f"background-color:#fdecea;color:{C.RED}"] * len(r)
            if wait[i]:
                return [f"background-color:#fdf6e9;color:{C.AMBER}"] * len(r)
            return [""] * len(r)

        st.dataframe(show.style.apply(_row, axis=1).format(
            {"1매당 측정시간(분)": "{:,.1f}", "총 측정시간(분)": "{:,.0f}"}),
            width="stretch", hide_index=True, height=520)
        st.caption("빨강 = 지연(요청 후 "
                   f"{C.STALE_DAYS}일 이상 미진행) · 주황 = 승인 대기")

    st.download_button("조회 결과 엑셀 내려받기", key="lotxls",
                       data=xls({"LOT상세": view(d), "LOT단위": lot_agg(d[d['상태'].ne('Cancel')])}),
                       file_name=f"precheck_lot_{d_from:%Y%m%d}_{d_to:%Y%m%d}.xlsx",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


# ============================================================ 기타 분석 · 부하·CAPA
elif PAGE == "부하·CAPA":
    st.markdown("<div class='sec'>부하 · CAPA</div>", unsafe_allow_html=True)
    if load_df.empty:
        empty_note(st)
    else:
        rows = [[esc(r["EQP_TYPE"]), f"{r['미진행ST']:,.0f}", f"{r['여유CAPA']:,.0f}",
                 f"<b>{r['부하율']:,.1f}%</b>",
                 bd({"과부하": "hv", "주의": "wt", "정상": "ok"}[r["판정"]], r["판정"])]
                for _, r in load_df.iterrows()]
        st.markdown(tx_table(rows, ["EQP TYPE", "미진행 ST(분)", "1일 여유 CAPA(분)",
                                    "부하율", "판정"]), unsafe_allow_html=True)
        st.caption("여유 CAPA = 설비대수 × 1440 × 가동률 − 기본유입. "
                   "부하율 = 미진행 사전 지정 ST 합 ÷ 1일 여유 CAPA. "
                   f"조회 구간 {N_DAYS}일치 미진행 물량을 1일 CAPA 와 비교하므로 "
                   "100% 초과는 '하루 안에 못 턴다'는 뜻입니다. "
                   "측정 예정일 컬럼이 생기면 날짜별 비교로 바꿔야 합니다. "
                   "CAPA 값은 예시이므로 실제 라인 값으로 바꿔야 합니다.")

    st.markdown("<div class='ct'>EQP TYPE 별 일자 부하율</div>"
                "<div class='cs'>미진행 사전 지정 기준 · 실선 100% / 점선 80%</div>",
                unsafe_allow_html=True)
    if pend.empty:
        empty_note(st, "미진행 사전 지정이 없습니다.")
    else:
        d = pend.copy()
        d["구분"] = d["사유"].where(d["사유"].eq(MAN), "기타")
        g = d.groupby(["EQP_TYPE", "일자", "구분"])["예상APT"].sum().reset_index(name="ST")
        g["부하율"] = [C.load_pct(v, e) for v, e in zip(g["ST"], g["EQP_TYPE"])]
        fig = px.bar(g, x="일자", y="부하율", color="구분", facet_col="EQP_TYPE",
                     facet_col_wrap=2, color_discrete_map={MAN: C.C1, "기타": C.C2},
                     category_orders={"구분": [MAN, "기타"]})
        fig.add_hline(y=C.LOAD_OVER, line_color=C.C1, line_width=1.4)
        fig.add_hline(y=C.LOAD_WARN, line_color=C.C1, line_width=1.2, line_dash="dot")
        fig.update_xaxes(tickformat="%m/%d", matches="x")
        _stack = g.groupby(["EQP_TYPE", "일자"])["부하율"].sum()
        _ymax = max(float(_stack.max()) if len(_stack) else 0.0, float(C.LOAD_OVER)) * 1.18
        # matches 를 쓰면 명시 range 가 먹지 않는다. 같은 range 를 직접 준다.
        fig.update_yaxes(title_text="", range=[0, _ymax])
        chart(st, lay(fig, 190 * max(1, (len(EQP_SEL) + 1) // 2) + 70, legend=True, facet=True),
              "f_capa")

    st.markdown("<div class='ct'>PPID 별 부하 순위</div>"
                "<div class='cs'>미진행 사전 지정 총측정시간 상위 15 · 해당 EQP 여유 CAPA 대비</div>",
                unsafe_allow_html=True)
    if pend.empty:
        empty_note(st)
    else:
        g = (pend.groupby(["PPID", "EQP_TYPE"])
             .agg(ST=("예상APT", "sum"), LOT=("LOTID", "nunique"),
                  매수=("지정매수", "sum"), APT=("APT_매", "max"))
             .reset_index().sort_values("ST", ascending=False).head(15))
        g["비중"] = [C.load_pct(v, e) for v, e in zip(g["ST"], g["EQP_TYPE"])]
        rows = [[f"{i + 1}", esc(r["PPID"]), esc(r["EQP_TYPE"]), f"{r['APT']:,.1f}",
                 f"{int(r['LOT'])}", f"{int(r['매수'])}", f"<b>{r['ST']:,.0f}</b>",
                 f"{r['비중']:,.1f}%"]
                for i, (_, r) in enumerate(g.iterrows())]
        st.markdown(tx_table(rows, ["#", "PPID", "EQP", "1매 ST(분)", "LOT", "매수",
                                    "미진행 ST(분)", "여유 CAPA 대비"]),
                    unsafe_allow_html=True)


# ============================================== 기타 분석 · 부서별 조정 요청
elif PAGE == "부서별 조정 요청":
    st.markdown("<div class='sec'>부서별 조정 요청</div>", unsafe_allow_html=True)
    if need.empty:
        empty_note(st, "조정이 필요한 사전 지정이 없습니다.")
    else:
        nd = need.copy()
        nd["제안매수"] = nd["지정매수"].clip(upper=C.SUGGEST_SLOTS)
        nd["절감"] = (nd["지정매수"] - nd["제안매수"]) * nd["APT_매"]
        summ = (nd.groupby("DEPARTMENT")
                .agg(대상=("LOTID", "nunique"), 건수=("LOTID", "size"),
                     ST=("예상APT", "sum"), 절감=("절감", "sum"))
                .reset_index().sort_values("ST", ascending=False))
        rows = [[esc(r["DEPARTMENT"]), f"{int(r['대상'])}", f"{int(r['건수'])}",
                 f"<b>{fh(r['ST'])}</b>", f"{fh(r['절감'])}"]
                for _, r in summ.iterrows()]
        st.markdown(tx_table(rows, ["요청 부서", "대상 LOT", "대상 건수",
                                    "총측정시간", "조정 시 절감"]), unsafe_allow_html=True)

        dept = st.selectbox("요청 문안을 만들 부서", summ["DEPARTMENT"].tolist(), key="adj_dept")
        sub = nd[nd["DEPARTMENT"].eq(dept)].sort_values("예상APT", ascending=False)
        rows = [[f"{r['요청일']:%m/%d}", esc(r["LOTID"]), esc(r["SLOTID"]), esc(r["EQP_TYPE"]),
                 esc(r["STEP_SEQ"]), esc(r["STEPID"]), esc(r["PPID"]), esc(r["요청자"]),
                 f"{r['APT_매']:,.1f}", f"{int(r['지정매수'])}", f"{int(r['제안매수'])}",
                 f"<b>{r['예상APT']:,.0f}</b>", f"{r['절감']:,.0f}"]
                for _, r in sub.iterrows()]
        st.markdown(tx_table(rows, ["요청일", "LOTID", "SLOTID", "EQP", "STEP SEQ", "STEP",
                                    "PPID", "요청자", "1매 ST(분)", "지정매수", "제안매수",
                                    "총 ST(분)", "절감(분)"]), unsafe_allow_html=True)

        over = load_df[load_df["부하율"].ge(C.LOAD_WARN)] if not load_df.empty else pd.DataFrame()
        if not over.empty:
            head = ("계측 CAPA 초과가 예상됩니다 ("
                    + ", ".join(f"{r['EQP_TYPE']} 부하율 {r['부하율']:,.0f}%"
                                for _, r in over.iterrows()) + ").")
        else:
            head = "계측 CAPA 는 아직 여유가 있으나 고부하 사전 지정 확인이 필요합니다."
        msg = (
            f"[계측 사전 지정 물량 조정 요청] {dept}\n"
            f"- 대상 기간: {dstr(d_from)} ~ {dstr(d_to)}\n"
            f"- {head}\n"
            f"- 귀 부서 사전 지정 중 총측정시간 {THR:,}분({fh(THR)}) 이상 건: "
            f"{sub['LOTID'].nunique():,} LOT / {len(sub):,}건, 합계 {fh(sub['예상APT'].sum())}\n"
            f"- 매수를 {C.SUGGEST_SLOTS}매로 조정하면 {fh(sub['절감'].sum())} 절감됩니다.\n"
            f"- 상위 대상:\n"
            + "\n".join(
                f"    {r['LOTID']} / {r['STEPID']}({r['STEP_SEQ']}) / {r['PPID']} / "
                f"{int(r['지정매수'])}매 / {r['예상APT']:,.0f}분 / 요청자 {r['요청자']}"
                for _, r in sub.head(10).iterrows())
            + "\n- 조정 또는 유지 사유를 회신 부탁드립니다."
        )
        st.markdown("<div class='ct'>복사용 요청 문안</div>", unsafe_allow_html=True)
        st.code(msg, language=None)
        st.download_button("조정 요청 엑셀 내려받기", key="adjxls",
                           data=xls({"부서요약": summ, f"{dept}_대상": view(sub)}),
                           file_name=f"adjust_{dept}_{d_from:%Y%m%d}_{d_to:%Y%m%d}.xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


# ================================================== 기타 분석 · Manual 상세
elif PAGE == "Manual 상세":
    st.markdown("<div class='sec'>Manual 사전 지정 상세</div>", unsafe_allow_html=True)
    m1, m2, m3 = st.columns([1.6, 1.6, 1.4])
    md = m1.multiselect("부서", DEPT_ALL, key="md_dept", placeholder="전체")
    users = sorted(man["요청자"].unique().tolist()) if not man.empty else []
    if st.session_state.get("md_user") and \
            not set(st.session_state["md_user"]).issubset(set(users)):
        st.session_state["md_user"] = []
    mu = m2.multiselect("요청자", users, key="md_user", placeholder="전체")
    me = m3.multiselect("EQP TYPE", EQP_SEL, key="md_eqp", placeholder="전체")

    d = man.copy()
    if md:
        d = d[d["DEPARTMENT"].isin(md)]
    if mu:
        d = d[d["요청자"].isin(mu)]
    if me:
        d = d[d["EQP_TYPE"].isin(me)]

    if d.empty:
        empty_note(st, "조건에 맞는 Manual 사전 지정이 없습니다.")
    else:
        a, b = st.columns([1.3, 1.7], gap="small")
        g = (d.groupby("DEPARTMENT").agg(LOT=("LOTID", "nunique"), ST=("예상APT", "sum"))
             .reset_index().sort_values("LOT", ascending=False))
        fig = px.bar(g, x="DEPARTMENT", y="LOT")
        fig.update_traces(marker_color=C.C1,
                          hovertemplate="%{x}<br>LOT %{y}건<extra></extra>")
        fig.update_yaxes(title_text="Manual LOT 수")
        a.markdown("<div class='ct'>부서별 Manual LOT 수</div>", unsafe_allow_html=True)
        chart(a, lay(fig, 250), "f_md")

        gu = (d.groupby(["요청자", "DEPARTMENT"])
              .agg(LOT=("LOTID", "nunique"), 건수=("LOTID", "size"),
                   매수=("지정매수", "sum"), ST=("예상APT", "sum"),
                   고부하=("예상APT", lambda s: int((s >= THR).sum())))
              .reset_index().sort_values("ST", ascending=False))
        b.markdown("<div class='ct'>요청자별 Manual 집계</div>", unsafe_allow_html=True)
        rows = [[esc(r["요청자"]), esc(r["DEPARTMENT"]), f"{int(r['LOT'])}", f"{int(r['건수'])}",
                 f"{int(r['매수'])}", f"<b>{fh(r['ST'])}</b>",
                 bd("hv", f"{int(r['고부하'])}건") if r["고부하"] else bd("ok", "0건")]
                for _, r in gu.iterrows()]
        b.markdown(tx_table(rows, ["요청자", "부서", "LOT", "건수", "매수", "총측정시간",
                                   f"고부하({THR:,}분↑)"]), unsafe_allow_html=True)

        st.markdown("<div class='ct'>Manual LOT 상세</div>", unsafe_allow_html=True)
        show = view(d.sort_values("예상APT", ascending=False))
        heavy = d.sort_values("예상APT", ascending=False)["예상APT"].ge(THR).to_numpy()

        def _hv(r):
            i = show.index.get_loc(r.name)
            return [f"background-color:#fdecea;color:{C.RED}"] * len(r) if heavy[i] else [""] * len(r)

        st.dataframe(show.style.apply(_hv, axis=1).format(
            {"1매당 측정시간(분)": "{:,.1f}", "총 측정시간(분)": "{:,.0f}"}),
            width="stretch", hide_index=True, height=440)
        st.download_button("Manual 상세 엑셀 내려받기", key="mdxls",
                           data=xls({"Manual상세": show, "요청자별": gu}),
                           file_name=f"manual_{d_from:%Y%m%d}_{d_to:%Y%m%d}.xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


# ============================================= 기타 분석 · Manual 주차 추이
elif PAGE == "Manual 주차 추이":
    st.markdown("<div class='sec'>Manual 주차 추이</div>", unsafe_allow_html=True)
    w1, w2, w3 = st.columns([1.1, 1.2, 1.8])
    weeks = int(seg(w1, "기간", ["4주", "8주", "12주"], "w_weeks")[:-1])
    w_by = seg(w2, "구분", ["PPID", "부서"], "w_by")
    w_metric = seg(w3, "지표", ["측정시간", "LOT 수", "매수"], "w_metric")

    wdf = apply_filters(get_data(d_to - timedelta(days=7 * weeks - 1), d_to))
    wdf = wdf[wdf["상태"].ne("Cancel") & wdf["사유"].eq(MAN)].copy()
    if wdf.empty:
        empty_note(st, "Manual 사전 지정 내역이 없습니다.")
    else:
        wdf["주차"] = wdf["요청일"].dt.to_period("W").dt.start_time
        key = "PPID" if w_by == "PPID" else "DEPARTMENT"
        if w_metric == "측정시간":
            g = wdf.groupby(["주차", key])["예상APT"].sum().div(60).reset_index(name="값")
            unit = "h"
        elif w_metric == "LOT 수":
            g = wdf.groupby(["주차", key])["LOTID"].nunique().reset_index(name="값")
            unit = "건"
        else:
            g = wdf.groupby(["주차", key])["지정매수"].sum().reset_index(name="값")
            unit = "매"

        g["값"] = g["값"].astype(float)      # LOT 수·매수는 정수라 pivot fill_value 와 dtype 이 어긋난다
        opts = (g.groupby(key)["값"].sum().sort_values(ascending=False).head(12).index.tolist())
        if st.session_state.get("w_pick") not in opts:
            st.session_state["w_pick"] = opts[0] if opts else None
        pick = st.selectbox(f"강조할 {w_by}", opts, key="w_pick")

        g["강조"] = g[key].eq(pick).map({True: "선택", False: "기타"})
        fig = px.bar(g, x="주차", y="값", color="강조",
                     color_discrete_map={"선택": C.C1, "기타": C.C2},
                     category_orders={"강조": ["선택", "기타"]},
                     custom_data=[key])
        fig.update_traces(hovertemplate="%{customdata[0]}<br>%{x|%m/%d}주<br>"
                                        "%{y:,.1f}" + unit + "<extra></extra>")
        fig.update_xaxes(tickformat="%m/%d")
        fig.update_yaxes(title_text=f"{w_metric} ({unit})")
        chart(st, lay(fig, 300, legend=True), "f_wk")

        pv = g.pivot_table(index=key, columns="주차", values="값", aggfunc="sum",
                           fill_value=0.0).sort_index(axis=1)
        if pv.shape[1] >= 2:
            last, prev = pv.columns[-1], pv.columns[-2]
            t = pd.DataFrame({w_by: pv.index, "직전주": pv[prev].to_numpy(),
                              "최근주": pv[last].to_numpy()})
            t["전주 대비"] = t["최근주"] - t["직전주"]
            thr_min = C.SURGE_MIN_MIN / (60.0 if w_metric == "측정시간" else 1.0)

            def _judge(r):
                if r["직전주"] <= 0 and r["최근주"] > 0:
                    return "신규"
                if (r["직전주"] > 0 and r["최근주"] >= r["직전주"] * C.SURGE_RATIO
                        and r["전주 대비"] >= thr_min):
                    return "급증"
                if r["전주 대비"] > 0:
                    return "증가"
                return "-"

            t["판정"] = t.apply(_judge, axis=1)
            t = t[t["판정"].ne("-")].sort_values("전주 대비", ascending=False).round(1)
            st.markdown(f"<div class='ct'>최근 주차 증가 항목</div>"
                        f"<div class='cs'>{dstr(prev)}주 → {dstr(last)}주 · 단위 {unit} · "
                        f"급증 = 직전주의 {C.SURGE_RATIO}배 이상이고 "
                        f"{C.SURGE_MIN_MIN}분 이상 증가</div>", unsafe_allow_html=True)
            if t.empty:
                empty_note(st, "증가한 항목이 없습니다.")
            else:
                st.dataframe(t.style.format({"직전주": "{:,.1f}", "최근주": "{:,.1f}",
                                             "전주 대비": "{:+,.1f}"}),
                             width="stretch", hide_index=True, height=min(420, 40 + 35 * len(t)))


# ==================================================== 기타 분석 · ST TOP 10
elif PAGE == "ST TOP 10":
    st.markdown("<div class='sec'>총측정시간 TOP 10</div>", unsafe_allow_html=True)
    t_by = seg(st, "기준", ["LOT", "PPID", "STEP", "요청자", "부서"], "top_by")
    keymap = {"LOT": "LOTID", "PPID": "PPID", "STEP": "STEPID",
              "요청자": "요청자", "부서": "DEPARTMENT"}
    if live.empty:
        empty_note(st)
    else:
        k = keymap[t_by]
        g = (live.groupby(k).agg(ST=("예상APT", "sum"), 건수=("LOTID", "size"),
                                 매수=("지정매수", "sum"),
                                 Manual=("사유", lambda s: int(s.eq(MAN).sum())))
             .reset_index().sort_values("ST", ascending=False).head(10))
        g["ST_h"] = g["ST"] / 60.0
        fig = px.bar(g, x="ST_h", y=k, orientation="h", custom_data=["건수", "매수", "ST"])
        fig.update_traces(marker_color=C.C1,
                          hovertemplate="%{y}<br>%{customdata[2]:,.0f}분 · "
                                        "%{customdata[0]}건 · %{customdata[1]}매<extra></extra>")
        fig.update_yaxes(autorange="reversed")
        fig.update_xaxes(title_text="총측정시간 (h)")
        chart(st, lay(fig, 34 * len(g) + 70), "f_top")
        rows = [[f"{i + 1}", esc(r[k]), f"{int(r['건수'])}", f"{int(r['매수'])}",
                 f"<b>{fh(r['ST'])}</b>",
                 bd("hv", f"{int(r['Manual'])}건") if r["Manual"] else bd("ok", "0건")]
                for i, (_, r) in enumerate(g.iterrows())]
        st.markdown(tx_table(rows, ["#", t_by, "건수", "매수", "총측정시간", "Manual"]),
                    unsafe_allow_html=True)


# ==================================================== 기타 분석 · 사유 분류
elif PAGE == "사유 분류":
    st.markdown("<div class='sec'>사전 지정 사유 분류</div>", unsafe_allow_html=True)
    if live.empty:
        empty_note(st)
    else:
        g = (live.groupby("사유").agg(LOT=("LOTID", "nunique"), 건수=("LOTID", "size"),
                                    매수=("지정매수", "sum"), ST=("예상APT", "sum"))
             .reindex(C.REASONS).dropna(how="all").reset_index())
        tot = float(g["ST"].sum()) or 1.0
        rows = [[esc(r["사유"]), f"{int(r['LOT'])}", f"{int(r['건수'])}", f"{int(r['매수'])}",
                 f"<b>{fh(r['ST'])}</b>", f"{r['ST'] / tot * 100:,.1f}%"]
                for _, r in g.iterrows()]
        st.markdown(tx_table(rows, ["사유", "LOT", "건수", "매수", "총측정시간", "비중"]),
                    unsafe_allow_html=True)

        st.markdown("<div class='ct'>사유별 일자 추이</div>"
                    "<div class='cs'>미진행(예정) 과 완료를 나눠 표시</div>",
                    unsafe_allow_html=True)
        d = live.copy()
        d["진행"] = d["상태"].map(lambda s: "예정" if s == "예정" else "완료")
        gg = d.groupby(["사유", "일자", "진행"])["예상APT"].sum().div(60).reset_index(name="ST")
        fig = px.bar(gg, x="일자", y="ST", color="진행", facet_col="사유", facet_col_wrap=2,
                     facet_row_spacing=0.13,
                     color_discrete_map={"예정": C.C1, "완료": C.C2},
                     category_orders={"진행": ["예정", "완료"], "사유": C.REASONS})
        fig.update_xaxes(tickformat="%m/%d", matches="x")
        fig.update_yaxes(matches="y")
        chart(st, lay(fig, 190 * max(1, (len(gg["사유"].unique()) + 1) // 2) + 70,
                      legend=True, facet=True), "f_rsn")


# ==================================================== 기타 분석 · 일자 추이
elif PAGE == "일자 추이":
    st.markdown("<div class='sec'>일자 추이</div>", unsafe_allow_html=True)
    st.caption("막대를 클릭하면 그 날짜·부서의 사전 지정 LOT 이 아래에 나옵니다.")
    if live.empty:
        empty_note(st)
    else:
        d = live.copy()
        d["구분"] = d["사유"].where(d["사유"].eq(MAN), "기타")
        g = (d.groupby(["DEPARTMENT", "일자", "구분"])["예상APT"].sum()
             .div(60).reset_index(name="ST"))
        fig = px.bar(g, x="일자", y="ST", color="구분", facet_col="DEPARTMENT",
                     facet_col_wrap=3, facet_row_spacing=0.15,
                     color_discrete_map={MAN: C.C1, "기타": C.C2},
                     category_orders={"구분": [MAN, "기타"]},
                     custom_data=["DEPARTMENT", "일자"])
        fig.update_xaxes(tickformat="%m/%d", matches="x")
        fig.update_yaxes(matches="y")
        ev = chart(st, lay(fig, 180 * max(1, (len(g["DEPARTMENT"].unique()) + 2) // 3) + 70,
                           legend=True, facet=True), "f_daily", on_select="rerun")

        pts = []
        try:
            pts = (ev.get("selection", {}) or {}).get("points", []) or []
        except AttributeError:
            pts = []
        if pts:
            p = pts[0]
            cd = p.get("customdata") or []
            sel_dept = cd[0] if cd else None
            sel_day = pd.Timestamp(p.get("x")).normalize() if p.get("x") else None
            sub = live.copy()
            if sel_day is not None:
                sub = sub[sub["일자"].eq(sel_day)]
            if sel_dept:
                sub = sub[sub["DEPARTMENT"].eq(sel_dept)]
            st.markdown(f"<div class='ct'>{esc(sel_dept or '전체 부서')} · "
                        f"{esc(dstr(sel_day) if sel_day is not None else '전체')}</div>",
                        unsafe_allow_html=True)
            if sub.empty:
                empty_note(st)
            else:
                st.dataframe(view(sub.sort_values("예상APT", ascending=False)),
                             width="stretch", hide_index=True, height=360)
        else:
            st.caption("선택된 막대가 없습니다.")


# ==================================================== 기타 분석 · STEP 분포
elif PAGE == "STEP 분포":
    st.markdown("<div class='sec'>STEP 분포</div>", unsafe_allow_html=True)
    if live.empty:
        empty_note(st)
    else:
        g = (live.groupby(["STEPID", "STEP_SEQ"])
             .agg(ST=("예상APT", "sum"), LOT=("LOTID", "nunique"), 건수=("LOTID", "size"),
                  Manual=("사유", lambda s: float(live.loc[s.index, "예상APT"][s.eq(MAN)].sum())))
             .reset_index().sort_values("ST", ascending=False))
        g["라벨"] = g["STEPID"] + " (" + g["STEP_SEQ"] + ")"
        g["ST_h"] = g["ST"] / 60.0
        vmax = float(g["ST"].max())
        colors = [mix(v, vmax)[0] for v in g["ST"]]
        fig = go.Figure(go.Bar(x=g["ST_h"], y=g["라벨"], orientation="h",
                               marker=dict(color=colors),
                               customdata=g[["LOT", "건수", "ST"]].to_numpy(),
                               hovertemplate="%{y}<br>%{customdata[2]:,.0f}분 · "
                                             "LOT %{customdata[0]}건<extra></extra>"))
        fig.update_yaxes(autorange="reversed")
        fig.update_xaxes(title_text="총측정시간 (h)")
        chart(st, lay(fig, 32 * len(g) + 70), "f_step")
        rows = [[esc(r["STEP_SEQ"]), esc(r["STEPID"]), f"{int(r['LOT'])}", f"{int(r['건수'])}",
                 f"<b>{fh(r['ST'])}</b>", f"{fh(r['Manual'])}",
                 f"{r['Manual'] / r['ST'] * 100 if r['ST'] else 0:,.0f}%"]
                for _, r in g.iterrows()]
        st.markdown(tx_table(rows, ["STEP SEQ", "STEP", "LOT", "건수", "총측정시간",
                                    "Manual ST", "Manual 비중"]), unsafe_allow_html=True)


# ================================================ 기타 분석 · 전주 대비 PPID
elif PAGE == "전주 대비 PPID":
    st.markdown("<div class='sec'>전주 대비 PPID</div>", unsafe_allow_html=True)
    w_to = d_to
    w_from = d_to - timedelta(days=6)
    p_f, p_t = w_from - timedelta(days=7), w_from - timedelta(days=1)
    st.caption(f"최근 7일 {dstr(w_from)} – {dstr(w_to)} vs 직전 7일 {dstr(p_f)} – {dstr(p_t)}")
    base = flt[flt["상태"].ne("Cancel")].copy()
    if base.empty:
        empty_note(st)
    else:
        bd_ = base["일자"].dt.date
        a = base[(bd_ >= w_from) & (bd_ <= w_to)]
        b = base[(bd_ >= p_f) & (bd_ <= p_t)]
        ca = a.groupby("PPID")["예상APT"].sum()
        cb = b.groupby("PPID")["예상APT"].sum()
        t = pd.DataFrame({"최근": ca, "직전": cb}).fillna(0.0)
        t["증감"] = t["최근"] - t["직전"]

        def _j(r):
            if r["직전"] <= 0 and r["최근"] > 0:
                return "신규"
            if r["최근"] <= 0 and r["직전"] > 0:
                return "중단"
            if r["증감"] > 0:
                return "증가"
            if r["증감"] < 0:
                return "감소"
            return "유지"

        t["판정"] = t.apply(_j, axis=1)
        t = t.reset_index().sort_values("증감", ascending=False)
        cnt = t["판정"].value_counts()
        chips = "".join(
            f"<span class='bd {'hv' if k in ('신규', '증가') else 'ok'}' "
            f"style='margin-right:6px'>{esc(k)} {int(cnt.get(k, 0))}종</span>"
            for k in ["신규", "증가", "유지", "감소", "중단"])
        st.markdown(f"<div style='margin:0 0 10px'>{chips}</div>", unsafe_allow_html=True)
        rows = [[esc(r["PPID"]), f"{r['직전']:,.0f}", f"{r['최근']:,.0f}",
                 f"<b>{r['증감']:+,.0f}</b>",
                 bd({"신규": "hv", "증가": "hv", "감소": "ok", "중단": "lt", "유지": "ok"}[r["판정"]],
                    r["판정"])]
                for _, r in t.iterrows()]
        st.markdown(tx_table(rows, ["PPID", "직전 7일 ST(분)", "최근 7일 ST(분)",
                                    "증감", "판정"]), unsafe_allow_html=True)


else:
    st.markdown("<div class='sec'>준비 중</div>", unsafe_allow_html=True)
    empty_note(st, f"'{PAGE}' 화면이 없습니다. 상단 탭에서 다시 선택해 주세요.")
