# -*- coding: utf-8 -*-
"""계측 사전 지정 부하 대시보드 - 기준값과 계산식.

화면(app.py)은 계산식을 직접 쓰지 않고 이 파일의 상수·함수만 쓴다.
아래 CAPA 숫자는 예시다. 실제 운영 전에 라인 실측값으로 바꿔야 한다.
"""

from __future__ import annotations

# ---------------------------------------------------------------- 조회 기간
DEFAULT_DAYS = 3          # 사이드바 기본 조회 기간 (사전 지정은 3일치가 관리 단위)
MIN_DAYS = 3              # 이보다 짧게 고르면 3일로 늘린다
CMP_MIN_DAYS = 14         # 비교 구간을 위해 최소 이만큼 더 앞에서부터 가져온다

# ------------------------------------------------------ 총측정시간 알람 기준
# 이 대시보드의 주 목적: 총측정시간이 임계치를 넘는 사전 지정 LOT을 미리 띄운다.
ALARM_THR_MIN = 120      # LOT 총측정시간 알람 임계 (분). 사이드바에서 조정 가능
ALARM_CRIT_MULT = 2.0    # 임계 x 이 배수 이상이면 '위험'

HEAVY_LOT_MIN = 120     # 고부하 LOT (STEP 1건 기준 ST, 분)
STALE_DAYS = 3          # 요청 후 이 일수 넘게 미진행이면 지연
SUGGEST_SLOTS = 2       # 부서 조정 요청 시 제안 매수
SURGE_RATIO = 1.5       # 주차 추이 급증 판정 배수
SURGE_MIN_MIN = 60      # 주차 추이 급증 판정 최소 증가량 (분)

LOAD_WARN = 80          # 부하율 주의 (%)
LOAD_OVER = 100         # 부하율 과부하 (%)

# ------------------------------------------------------------------- CAPA
# 설비대수 / 가동률 / 기본유입_분(시스템 자동 유입 물량, 분/일)
EQP_CAPA = {
    "METRCD":  {"설비대수": 6, "가동률": 0.80, "기본유입_분": 5200},
    "METROVL": {"설비대수": 4, "가동률": 0.82, "기본유입_분": 3400},
    "METRTHK": {"설비대수": 3, "가동률": 0.85, "기본유입_분": 2600},
    "METRDEF": {"설비대수": 2, "가동률": 0.78, "기본유입_분": 1500},
}
EQP_ALL = list(EQP_CAPA.keys())

REASONS = ["Manual", "PM AUTO QUAL", "APC", "DSM"]   # 철자 일치 필수
MANUAL = "Manual"

# ------------------------------------------------------------------- 색
INK = "#26332f"
SUB = "#6b7773"
LINE = "#e3e8e6"
ACCENT = "#12a37a"
DEEP = "#0b7a59"
BG = "#eef0f2"
MINT = "#e9f7f1"
RED = "#c0392b"
AMBER = "#b9770e"

C1 = "#12a37a"   # 주목: Manual, 미진행·예정, 고부하, 강조
C2 = "#c9ecdd"   # 나머지


# --------------------------------------------------------------- 계산식
def st_total(apt_per_wafer: float, slots: float) -> float:
    """총측정시간(분) = 1매 ST x 사전 지정 매수."""
    return float(apt_per_wafer) * float(slots)


def free_capa_min(eqp_type: str) -> float:
    """EQP 여유 CAPA(분/일) = 설비대수 x 1440 x 가동률 - 기본유입_분."""
    c = EQP_CAPA.get(eqp_type)
    if not c:
        return 0.0
    v = c["설비대수"] * 1440 * c["가동률"] - c["기본유입_분"]
    return float(max(v, 0.0))


def free_capa_min_multi(eqp_types) -> float:
    """여러 EQP TYPE의 여유 CAPA 합(분/일)."""
    return float(sum(free_capa_min(e) for e in eqp_types))


def load_pct(st_sum_min: float, eqp_types) -> float:
    """부하율(%) = 미진행 사전 지정 ST 합 / 여유 CAPA x 100."""
    if isinstance(eqp_types, str):
        eqp_types = [eqp_types]
    cap = free_capa_min_multi(eqp_types)
    if cap <= 0:
        return 0.0
    return float(st_sum_min) / cap * 100.0


def load_state(pct: float) -> str:
    if pct >= LOAD_OVER:
        return "과부하"
    if pct >= LOAD_WARN:
        return "주의"
    return "정상"


def alarm_level(total_min: float, thr: float = ALARM_THR_MIN) -> str:
    """총측정시간 알람 등급."""
    if total_min >= thr * ALARM_CRIT_MULT:
        return "위험"
    if total_min >= thr:
        return "주의"
    return "정상"


def is_heavy(total_min: float, thr: float = ALARM_THR_MIN) -> bool:
    return float(total_min) >= float(thr)


def period_unit(n_days: int) -> str:
    """추이 단위: 14일 이하 '주'(일별 점), 45일 이하 '월', 그 이상 '분기'(주별 점)."""
    if n_days <= 14:
        return "주"
    if n_days <= 45:
        return "월"
    return "분기"


def trend_freq(n_days: int) -> str:
    """추이 점 간격: '주'는 일별, 그 외는 주별."""
    return "D" if period_unit(n_days) == "주" else "W"


def need_adjust_mask(df, thr: float, over_eqps) -> "object":
    """조정 대상(need) 마스크.

    미진행(예정) 중 ST >= thr 이거나,
    주의·과부하 EQP의 Manual 중 ST >= thr/4.
    """
    pend = df["상태"].eq("예정")
    big = df["예상APT"].ge(thr)
    man_over = (
        df["사유"].eq(MANUAL)
        & df["EQP_TYPE"].isin(list(over_eqps))
        & df["예상APT"].ge(thr / 4.0)
    )
    return pend & (big | man_over)
