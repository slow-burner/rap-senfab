# EXECUTION — 구현 지시서

처음부터 만든다고 보고 쓴 단계별 지시서. **각 단계마다 "왜 하는지" 를 먼저 적었다.**
순서를 바꾸면 안 되는 이유도 적어 둔다. 단계 끝의 **DoD** (완료 기준) 를 만족하지
못하면 다음 단계로 넘어가지 않는다. 넘어가면 어디서 틀렸는지 못 찾는다.

| 단계 | 내용 | 산출물 | 사내 DB 필요 |
|---|---|---|---|
| 0 | 환경 · 뼈대 | `app.py` 빈 화면이 뜬다 | 아니오 |
| 1 | 설정 분리 | `capa_config.py` | 아니오 |
| 2 | 데이터 계층 (샘플) | `data_source.py` | 아니오 |
| 3 | 알람 · 공통 레이아웃 | 배너 · 탭 · 사이드바 | 아니오 |
| 4 | 상단 3탭 | 전체 현황 · 부서별 · LOT 상세 | 아니오 |
| 5 | 기타 분석 8화면 | 부하·CAPA · 조정 요청 등 | 아니오 |
| 6 | 주차별 3화면 | 부서 · PPID·STEP · 요청자 | 아니오 |
| 7 | SQL | `sql/precheck_tkin_view.sql` | 아니오 (모의 실행) |
| 8 | 실연결 · 검증 | `config.ini` · 테스트 | **예** |
| 9 | 배포 | 사내 웹 · exe | 예 |

**0~7 은 사내 DB 없이 전부 만든다.** 접속 정보를 기다리며 멈추지 않기 위한
순서다. 8단계에서 스위치 한 줄만 돌린다.

---

## 0. 환경 · 뼈대

### 왜

Streamlit 은 화면을 **위에서 아래로 매번 다시 실행한다.** 버튼을 누르면 함수가
하나 호출되는 게 아니라 파일이 처음부터 다시 돌아간다. 이 모델을 모르고 짜면
"값이 초기화된다", "그래프가 두 번 그려진다" 로 며칠 날린다. 먼저 빈 화면을
띄워 이 동작을 눈으로 확인하고 시작한다.

### 작업

```bash
python -m venv .venv && source .venv/bin/activate
pip install streamlit pandas plotly openpyxl Jinja2
streamlit run app.py
```

`requirements.txt` 는 **버전을 박아 둔다.** 박지 않으면 몇 달 뒤 다른 PC 에서
`Styler.applymap` 삭제(pandas 3) 같은 걸로 통째로 죽는다.

```python
# app.py 첫 줄
import streamlit as st
st.set_page_config(page_title="계측 사전 지정 부하 모니터", layout="wide")
st.write("hello")
```

`layout="wide"` 는 취향이 아니다. 기본 레이아웃은 가운데 730px 라 **주차 12개
짜리 표가 접힌다.**

### 웹 서버에 대해

Streamlit 1.66 은 내부적으로 **uvicorn + Starlette** 로 돈다 (1.5x 까지는
Tornado 였다). 그래서 `uvicorn` 이 의존성에 들어 있다. 하지만:

```bash
streamlit run app.py              # ← 이것만 쓴다
uvicorn app:app --port 8501       # ← 동작하지 않는다
```

Streamlit 앱은 ASGI 앱이 아니다. `streamlit run` 이 uvicorn 을 띄우고 그 안에
스크립트 실행기를 올리는 구조다. 포트·주소·헤드리스는 `streamlit run` 인자나
`.streamlit/config.toml` 로 준다.

```toml
# .streamlit/config.toml
[server]
port = 8501
address = "0.0.0.0"     # 사내 다른 PC 에서 붙으려면 필요
headless = true         # 서버에서 브라우저 자동 실행 방지
[browser]
gatherUsageStats = false
```

### DoD

- [ ] `streamlit run app.py` 로 화면이 뜬다
- [ ] 코드를 고치면 브라우저가 자동 갱신된다
- [ ] `pip freeze` 결과를 `requirements-lock.txt` 로 떠 둔다

---

## 1. 설정 분리 — `capa_config.py`

### 왜

**이 단계를 건너뛰면 반드시 망한다.** 임계치 120분, CAPA 계산식, 코드값 매핑이
화면 코드 안에 흩어지면 "이 숫자 어디서 나왔나" 를 아무도 못 찾는다. 계측 현장은
임계치와 CAPA 가 **계속 바뀐다.** 바뀔 값은 처음부터 한 파일에 모은다.

또 하나. 지금은 `AST_TIME` 의 단위(분/초)와 `REQUEST_TYPE` 코드표를 모른다.
값이 오면 **설정 한 줄만** 고쳐야 한다. 코드를 뒤져야 하면 안 된다.

### 작업

```python
# capa_config.py
DEFAULT_DAYS = 3          # 기본 조회 3일
MIN_DAYS     = 3          # 최소 3일 — 하루만 골라도 3일로 늘린다
ALARM_THR_MIN  = 120      # 총측정시간 알람 임계 (분)
ALARM_CRIT_MULT = 2.0     # 임계 × 2 이상 = '위험'
AST_UNIT_MIN = 1.0        # AST_TIME 단위. 초면 1/60 로 바꾼다  ★확인 필수

EQP_CAPA = {"METRCD": {"설비대수": 6, "가동률": 0.80, "기본유입_분": 5200}}
CAPA_IS_SAMPLE = True     # 실측값 들어오면 False. 화면 경고가 사라진다

C1 = "#12a37a"; C2 = "#c9ecdd"; RED = "#c0392b"   # 그래프 2색 + 경고색

REASON_MAP = {"MANUAL": "Manual", "PM": "PM AUTO QUAL"}   # ★코드표 확인 필수
REASON_DEFAULT = "Manual"      # 모르는 코드는 Manual 로 — 과소 집계보다 안전
```

`REASON_DEFAULT` 를 Manual 로 두는 이유: 코드표를 모르는 지금, 모르는 코드를
'기타' 로 빼면 **알람이 조용해진다.** 알람이 안 울리는 게 제일 나쁘다.
Manual 로 몰아 두면 과다 탐지는 되지만 빠지지는 않는다.

`CAPA_IS_SAMPLE` 플래그가 꼭 필요하다. 예시값으로 낸 부하율 85% 가 회의에서
실측값으로 보고되는 사고를 막는다. 화면에 "예시값" 경고를 띄우는 근거다.

### DoD

- [ ] 화면·SQL 코드에 숫자 리터럴이 없다 (`grep -n "120\|0.8" app.py` 가 비어 있다)
- [ ] `ALARM_THR_MIN` 을 60 으로 바꾸면 알람 건수가 늘어난다

---

## 2. 데이터 계층 — `data_source.py`

### 왜

사내 DB 접속 정보, 컬럼 단위, 코드표가 아직 없다. 그걸 기다리면 아무것도 못
만든다. **같은 모양의 샘플 데이터**를 먼저 만들어 화면을 전부 완성하고, 나중에
스위치만 돌린다.

더 중요한 이유: 화면이 DB 컬럼 이름(`ACTY_SLOT_ID` 같은)을 직접 쓰면 컬럼명이
하나 바뀔 때 **화면 14개를 전부 고쳐야 한다.** 이름을 바꾸는 지점을 한 군데로
묶는다.

### 작업

```python
# data_source.py
USE_SAMPLE = True         # 8단계에서 False 로

SQL_TO_APP = {            # DB 컬럼 → 화면 컬럼. 이름 바꾸는 곳은 여기 한 군데
    "RESERVE_DATE": "요청일", "LOT_ID": "LOTID",
    "ACTY_STEP_SEQ": "STEP_SEQ", "ACTY_SLOT_ID": "SLOTID",
    "REQ_SLOT_COUNT": "지정매수", "FORECAST_APT_REQ": "예상APT",
    # ...
}

def load_raw(d_from, d_to) -> pd.DataFrame:
    return _sample(d_from, d_to) if USE_SAMPLE else _map_db(_db(d_from, d_to))
```

샘플 데이터는 **현장에서 실제로 보이는 모양**을 넣는다. 깨끗한 데이터로 만들면
실데이터에서 전부 깨진다. 반드시 넣을 것:

| 넣을 것 | 왜 |
|---|---|
| 한 LOT 에 계측 STEP 여러 개 | FR-1.1 의 LOT 합산이 맞는지 확인할 유일한 방법 |
| 1매 30분짜리 고ST PPID | 알람이 실제로 울리는지 |
| Manual 이 아닌 고부하 (PM 풀랏 QUAL) | 이게 없으면 KPI 2번과 4번이 항상 같은 값으로 나온다 |
| 상태 `예정` / `진행` / `완료` / `Cancel` | 모수 기본값이 '예정' 인지 확인 |
| 요청 후 3일 넘게 안 움직인 건 | 지연 표시 |
| 주차별 12주 분량 | 6단계 전제 |

네 번째 줄이 실제로 겪은 것이다. Manual 에만 고부하를 넣어 두면 "Manual 고부하
PPID" 와 "전체 고부하 PPID" 가 늘 같은 숫자로 나와서, 값이 맞는지 틀린지
구분할 수 없다.

### DoD

- [ ] `load_raw()` 가 데이터 계약(AGENTS.md)의 컬럼을 전부 돌려준다
- [ ] 한 LOT 에 STEP 2개 이상인 케이스가 샘플에 있다
- [ ] Manual 아닌 고부하 건이 샘플에 있다

---

## 3. 알람 · 공통 레이아웃

### 왜

알람이 이 프로그램의 **1순위 요구사항**이다. 화면을 다 만든 뒤 알람을 붙이면,
알람이 특정 탭에만 달린다. 사용자는 "부서별 현황" 을 보다가 알람을 놓친다.
그래서 **화면보다 알람을 먼저** 만들고, 모든 화면 위에 고정한다.

### 작업

순서가 중요하다.

1. **사이드바 필터** (기간 · LINEID · EQP TYPE · 부서 · 사유 · 임계치)
   기간은 `date_input` 으로 받되 **3일 미만이면 3일로 늘린다.** 요구사항이다.
   하루만 보면 "오늘 좀 많네" 밖에 안 나온다. 3일은 추세가 보이는 최소 기간이다.

2. **데이터 가공** — 필터 적용 → `cur`(조회 구간) · `prv`(직전 동일 구간)
   `prv` 를 같이 만드는 이유: 숫자만 보여주면 많은지 적은지 모른다. 증감이 있어야
   판단이 된다.

3. **알람 계산** — LOT 단위 합산
   ```python
   lot_sum = man_pending.groupby("LOTID")["예상APT"].sum()
   crit = lot_sum[lot_sum >= THR * C.ALARM_CRIT_MULT]   # 위험
   warn = lot_sum[(lot_sum >= THR) & (lot_sum < THR * C.ALARM_CRIT_MULT)]
   ```
   **STEP 단위로 세면 안 된다.** 60분짜리 2개를 걸면 STEP 단위로는 둘 다
   임계 미만이지만 LOT 은 120분이다. 그게 실제 문제 사례다.

4. **배너 고정** — 탭보다 위, 모든 화면 공통
5. **상단 탭 3개 + 기타 분석 selectbox**

기타 분석을 selectbox 로 둔 이유: 탭이 14개면 가로로 안 들어가고 줄바꿈되면서
어느 게 선택됐는지 안 보인다. 자주 보는 3개만 탭, 나머지는 목록으로 접는다.

### 함정

위젯 `key` 는 전역이다. 사이드바 필터에 `f_dept` 를 쓰고 그래프에 `f_dept` 를
쓰면 `DuplicateWidgetID` 로 **화면이 통째로 백지가 된다.** 실제로 겪었다.
그래프는 래퍼를 하나 두고 `g_` 접두어를 강제한다.

```python
def chart(parent, fig, key):
    parent.plotly_chart(fig, width="stretch", key=f"g_{key}")   # g_ 강제
```

### DoD

- [ ] 어느 화면에서도 배너가 보인다
- [ ] 임계치를 60 으로 내리면 배너 건수가 늘어난다
- [ ] 하루만 골라도 3일로 조회된다
- [ ] 한 LOT 에 STEP 2개인 건이 **합산되어** 알람에 잡힌다

---

## 4. 상단 3탭

### 왜

사용자 셋의 동선이 서로 다르다. 한 화면에 다 넣으면 아무도 못 쓴다.

| 탭 | 누가 | 질문 |
|---|---|---|
| 전체 현황 | 계측 재공 담당 | "지금 괜찮은가" |
| 부서별 Manual 사전 지정 현황 | 계측 팀장 | "어디에 얘기해야 하나" |
| LOT 상세 조회 | 기술 부서 담당 | "내 LOT 이 왜 지목됐나" |

### 작업

**4-1 전체 현황** — KPI 4개 → 추이 → 부서×EQP 행렬 → 조치 필요 목록

KPI 를 4개로 끊은 이유: 2개면 상황 판단이 안 되고 6개면 아무도 안 본다.
각 KPI 에 **직전 동일 기간 대비 증감**을 붙인다.

**4-2 부서별 현황** — 부서 막대 · 요청자 막대 · 요청 사유 · 히트맵 · 그리드

요청자 막대는 **가로 막대**로 한다. 세로로 하면 이름이 길어 x축 라벨이 비스듬히
눕고 카드를 넘친다. 실제로 겪었다.

**4-3 LOT 상세 조회** — 검색 · 모수 선택 · **STEP/LOT 단위 전환** · 엑셀

단위 전환이 꼭 필요하다. 알람은 LOT 합산인데 표는 STEP 단위다. 합산 근거를 못
보면 사용자는 알람을 믿지 않는다.

### 그래프 규칙

**색은 2가지만.** `C1` = Manual·미진행·고부하·강조, `C2` = 나머지.
범주가 4개 이상이면 `Manual vs 기타` 로 묶는다. 빨강은 그래프가 아니라
경고(증가 KPI, 배지, 지연 행)에만. 색이 5개 있는 그래프는 아무 정보도 안 준다.

### DoD

- [ ] 3탭 모두 예외 없이 뜬다
- [ ] 필터를 걸면 세 탭 숫자가 **같이** 변한다
- [ ] 엑셀 다운로드가 열린다
- [ ] STEP/LOT 전환 시 LOT 합계가 알람 값과 일치한다

---

## 5. 기타 분석 8화면

### 왜

3탭으로 "문제가 있다" 까지는 간다. 그 다음 질문에 답하는 화면들이다.
그중 **부서별 조정 요청**이 이 프로그램의 실질적 산출물이다.

### 작업

| 화면 | 답하는 질문 |
|---|---|
| 부하·CAPA | 설비가 실제로 소화 가능한가 |
| **부서별 조정 요청** | **어떤 문장으로 보낼까** ← 핵심 |
| Manual 상세 | 왜 걸었나 (요청 사유 원문) |
| ST TOP 10 | 어떤 레시피가 비싼가 |
| 사유 분류 · 일자 추이 · STEP 분포 · 전주 대비 PPID | 보조 |

조정 요청 화면은 **복사해서 메일·메신저에 그대로 붙일 수 있는 문안**을 만든다.
대상 LOT, 총측정시간, 제안 매수, 절감 예상 시간을 넣는다. 화면을 캡처해 보내면
받는 쪽이 뭘 해야 하는지 모른다.

부하·CAPA 화면은 `CAPA_IS_SAMPLE` 이 True 면 **반드시 경고를 띄운다.**

### DoD

- [ ] 조정 요청 문안이 복사 가능한 형태로 나온다
- [ ] 문안의 절감 시간이 `capa_config.py` 식과 일치한다
- [ ] 예시값 경고가 보인다

---

## 6. 주차별 3화면

### 왜

한 번 넘긴 건 사정이 있었을 수 있다. 6주 연속이면 관행이다. 그 차이를 보여주는
화면이다. 부서 협의 자리에서 "이번 주 많았다" 는 반박되지만 "8주 중 7주 평균
상회" 는 반박이 안 된다.

### 작업

세 화면이 **같은 모수·같은 집계 함수**를 쓴다. 공통 함수로 뺀다.

```python
def week_base(weeks): ...          # 주차 구간 생성
def week_agg(df, keys, metric): ...  # keys 별 주차 집계
```

따로 짜면 같은 주의 합계가 화면마다 다르게 나온다. 그 순간 세 화면 전부 신뢰를
잃는다. 테스트로 **세 화면의 같은 주 합계가 일치**하는지 본다.

### 가장 중요한 함정 — 진행 중인 주

조회 끝일이 수요일이면 이번 주는 3일치다. 지난주(7일치)와 비교하면 **모든 부서가
'감소' 로 나온다.** 증감 전체가 거짓말이 된다. 실제로 겪었다.

```python
def done_weeks(ws):
    return [w for w in ws if (pd.Timestamp(d_to) - pd.Timestamp(w)).days >= 6]
```

증감은 **끝난 주끼리만** 비교하고, 진행 중인 주는 흐리게 표시하고 라벨에
"진행 중" 을 붙인다.

### 엑셀 함정

주차 라벨이 `10/13주` 다. 이걸 시트 이름으로 쓰면
`Invalid character / found in sheet title` 로 다운로드가 죽는다. Excel 시트
이름은 31자 제한에 `/ \ ? * [ ] :` 금지다. 전용 함수를 거친다.

```python
_BAD = set("/\\?*[]:")
def sheet_name(name, used): ...     # 금지문자 제거 + 31자 + 중복 번호
```

### DoD

- [ ] 4 / 8 / 12주 전환이 된다
- [ ] 세 화면의 같은 주 합계가 일치한다 (테스트로 고정)
- [ ] 조회 끝일을 주 중간으로 잡아도 증감이 전부 '감소' 로 안 나온다
- [ ] 주차 라벨이 든 엑셀이 열린다

---

## 7. SQL

### 왜

화면이 다 돌아간 뒤에 SQL 을 쓴다. 순서가 반대면 "화면에 뭐가 필요한지" 를
모르는 상태로 쿼리를 짜게 되고, 결국 두 번 짠다.

기존 Spotfire 화면을 SQL 한 벌로 옮기는 작업이다. Spotfire 의 조인·계산 컬럼을
그대로 재현해야 기존 사용자가 같은 숫자를 본다.

### 작업

`.sql` 파일로 **따로 둔다.** 파이썬 문자열에 넣지 않는다. DBeaver 로 바로 돌려
확인할 수 있어야 한다. 프로그램은 이 파일을 런타임에 읽는다.

```python
SQL_FILE = "sql/precheck_tkin_view.sql"   # 단일 진실 원천
```

따라서 exe 빌드에 `--add-data "sql;sql"` 가 필요하다. 빠뜨리면 샘플 모드에서는
잘 돌다가 DB 모드에서만 파일을 못 찾고 죽는다.

### 7-1 Spotfire 조인 재현

Spotfire 의 **Left single match join** 은 오른쪽에 여러 건이 맞아도 1건만 붙인다.
SQL 에는 같은 조인이 없다. 오른쪽을 **키당 1행으로 줄인 뒤** LEFT JOIN 한다.

```sql
WITH HIST_RANKED AS (
  SELECT ..., ROW_NUMBER() OVER (
           PARTITION BY H.LINE_ID, H.LOT_ID, H.STEP_SEQ
           ORDER BY H.TKIN_DATE DESC, H.LAST_UPDATE_DATE DESC) AS RN
  FROM fab.m_lot_transn_hist H
  WHERE ( H.TKOUT_DATA >= DATE_SUB(:d_from, INTERVAL 8 DAY)
          OR H.TKOUT_DATA IS NULL )
    AND H.LINE_ID IN (SELECT DISTINCT LINE_ID FROM REQ_BASE)
)
```

안 줄이면 재측정 LOT 에서 행이 불어나 **총측정시간이 조용히 부풀려진다.**
에러가 안 난다. 그래서 DB 붙인 직후 조인 전후 행 수를 반드시 비교한다.

### 7-2 키 — ERD 의 표를 그대로 따른다

| 지킬 것 | 안 지키면 |
|---|---|
| `m_lot_transn_hist` 는 `LINE_ID` · `TKOUT_DATA` 로 거른다 | 팹 전체 스캔. 수십 초 |
| `TKOUT_DATA IS NULL` 을 OR 로 같이 둔다 | 지금 측정중인 LOT 이 통째로 빠진다 |
| `m_lot_spx` 는 `AREA` · `OUT_TIME` | 〃 |
| 조인·GROUP BY 에 `AREA` 를 넣는다 | 다른 라인 값이 붙어 라인 분류와 예상시간이 동시에 틀린다 |

### 7-3 MySQL 8 방언

CTE·`ROW_NUMBER()` 를 쓰므로 5.7 로는 안 된다.

```sql
DATE_SUB(:d_from, INTERVAL 8 DAY)              -- 날짜 연산
ORDER BY (FORECAST_APT IS NULL), FORECAST_APT DESC   -- NULLS LAST 가 없다
LENGTH(NULLIF(J.SLOT_ID,'')) - LENGTH(REPLACE(NULLIF(J.SLOT_ID,''),',','')) + 1
```

`NULLIF(SLOT_ID,'')` 가 핵심이다. MySQL 은 **빈 문자열이 NULL 이 아니다.**
빼면 빈 슬롯이 0매가 아니라 **1매로 세진다.** 총측정시간이 부풀려지고 알람이
오탐한다.

### 7-4 모의 실행으로 검증 — 사내 DB 없이

DuckDB 에 같은 이름의 가짜 테이블을 만들고 **실제 `.sql` 파일을 그대로** 돌린다.

```python
con.execute("CREATE TABLE fab.m_lot_actv_req (...)")   # 같은 컬럼명
df = con.execute(open(SQL_FILE).read().replace(":d_from", "'2026-10-18'")).df()
```

이걸로 확인되는 것: 단일 매치 중복 제거, 슬롯 매수 세기, 대상 판정,
LINEP 분기 전부, 측정중 LOT 생존, 라인 분리, `m_step` 받침, STEP 평균 받침.

확인 **안 되는** 것: 실제 성능, 실제 컬럼 존재 여부, 단위. 8단계에서 본다.

### 7-5 컬럼 정리표를 믿지 않는다

받은 엑셀 컬럼 정리표는 **사진·메모 재구성본**이다. 표에 없는 컬럼을 "없다" 고
단정해 우회 조인을 넣었다가, 실제로는 멀쩡히 있는 컬럼이었던 일이 있다.
의심되면 `SELECT * FROM <테이블> LIMIT 5` 로 실제 DB 를 본다.

### DoD

- [ ] `.sql` 을 DBeaver 에서 그대로 실행할 수 있다
- [ ] ERD 의 키 표를 전부 반영했다
- [ ] DuckDB 모의 실행이 통과한다
- [ ] 조인 전후 행 수가 같다 (행 증식 없음)

---

## 8. 실연결 · 검증

### 왜

여기서 처음 실데이터를 본다. 0~7 이 다 끝났으므로 **틀린 게 나오면 원인이
데이터·접속·단위 중 하나**로 좁혀진다. 화면과 섞이지 않는다.

### 작업

```ini
; config.ini  ← .gitignore. 절대 커밋하지 않는다
[db]
host = ...
port = 3306
user = ...
password = ...
```

```python
USE_SAMPLE = False      # data_source.py — 이 한 줄
```

파이썬 바인드 변수 변환이 필요하다. `.sql` 은 읽기 좋게 `:d_from` 으로 쓰고,
pymysql 은 `%(d_from)s` 를 받는다. 순서가 중요하다.

```python
def _to_pymysql(sql):
    sql = _strip_comments(sql)        # 1. 주석 제거 — 주석 안의 % 가 터진다
    sql = sql.replace("%", "%%")      # 2. % 이스케이프
    return _BIND.sub(r"%(\1)s", sql)  # 3. :name → %(name)s
```

### 실연결 직후 확인 순서

**이 순서로 본다.** 뒤에서부터 보면 원인을 못 찾는다.

| # | 확인 | 틀렸을 때 |
|---|---|---|
| 1 | 행 수가 Spotfire 와 같은가 | 조인·필터 문제 |
| 2 | `AST_TIME` 단위 (분/초) | `AST_UNIT_MIN` 한 줄 |
| 3 | `AST_TIME` 이 1매 평균인가 | 시간 계산 전체 재설계 |
| 4 | `REQUEST_TYPE` 코드값 | `REASON_MAP` 수정 |
| 5 | 슬롯 표기법 — `REQ_QTY` 와 대조 | 매수 세는 식 수정 |
| 6 | 3일 조회가 5초 안에 끝나는가 | 파티션 키 미적용 |

2번은 **120분 임계가 2분이 되거나 7200분이 된다.** 알람이 전부 울리거나 전혀
안 울린다. 가장 먼저 본다.

### 캐시 함정

컬럼을 고쳤는데 "없는 컬럼" 에러가 계속 난다면 `@st.cache_data` 에 옛 데이터가
남은 것이다. **서버를 재시작한다.** 코드만 고치면 안 풀린다.

### 테스트

```bash
pytest -q tests/
```

두 겹으로 둔다.

1. **AppTest** (`streamlit.testing.v1`) — 14화면 × 기간 × 필터 조합을 헤드리스로
   돌려 예외를 잡는다. Streamlit 은 매번 전체를 다시 실행하므로 **한 화면을
   고치면 전혀 다른 화면이 깨진다.** 손으로 확인하는 걸로는 못 잡는다.
2. **Playwright** — 실제 브라우저에서 레이아웃·JS 에러를 본다. AppTest 는
   레이아웃을 못 본다.

Streamlit 1.66 은 react-aria 를 쓴다. 셀렉터를 `div[data-baseweb='select']` 로
잡으면 0개가 나온다. `get_by_role("combobox", name="기타 분석")` 로 잡는다.

### DoD

- [ ] 실데이터로 14화면이 전부 뜬다
- [ ] 행 수가 Spotfire 와 일치한다
- [ ] 위 6개 확인 항목이 전부 끝났다
- [ ] 3일 조회가 5초 이내
- [ ] `pytest -q tests/` 전부 통과

---

## 9. 배포

### 왜

사용 상황이 둘이다. 계측 재공 담당은 매일 아침 브라우저로 본다(사내 웹).
기술 부서 담당은 자기 PC 에서 가끔 확인한다(파이썬 없음). **같은 코드로 둘 다**
내야 한다. 따로 만들면 한쪽이 반드시 뒤처진다.

### A. 사내 웹

```bash
streamlit run app.py --server.port 8501 --server.address 0.0.0.0 --server.headless true
```

내부적으로 uvicorn 이 뜬다. 앞에 nginx 를 세워 인증을 건다. Streamlit 자체에는
사용자 인증이 없다.

```nginx
location / {
    proxy_pass http://127.0.0.1:8501;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;      # ★ WebSocket
    proxy_set_header Connection "upgrade";       # ★ 빠뜨리면 화면이 영원히 "Connecting..."
}
```

Streamlit 은 WebSocket 으로 화면을 갱신한다. 위 두 줄이 없으면 접속은 되고
화면만 안 뜬다. 원인 찾기 어렵다.

### B. 개인 PC exe

```
pyinstaller --onedir --collect-all bigdataquery --hidden-import pymysql \
            --add-data "sql;sql" run_app.py
```

- `--onedir` : `--onefile` 은 실행할 때마다 임시폴더에 풀어 느리다
- `--collect-all bigdataquery` : 사내 패키지. 자동 탐지가 안 된다
- `--hidden-import pymysql` : 동적 import 라 자동 탐지가 안 된다
- `--add-data "sql;sql"` : **런타임에 읽는 파일.** 빠뜨리면 DB 모드에서만 죽는다
- `matplotlib` 금지. 수백 MB 늘어난다

접속 정보는 exe 에 넣지 않는다. `config.ini` 를 폴더에 같이 두고 각자 채운다.

### DoD

- [ ] 웹에서 다른 PC 가 접속해 화면이 뜬다 (WebSocket 포함)
- [ ] 파이썬 없는 PC 에서 exe 가 돈다
- [ ] exe 에서 **DB 모드**로도 뜬다 (`.sql` 포함 확인)
- [ ] `config.ini` 가 저장소에 없다

---

## 전체 완료 기준

- [ ] 임계 초과 LOT 이 **측정 전에** 배너에 뜬다 ← 1순위 요구사항
- [ ] 한 LOT 의 여러 STEP 이 합산되어 판정된다
- [ ] 부서에 보낼 조정 요청 문안이 복사 가능하다 ← 실질 산출물
- [ ] 주차별 3화면 합계가 일치하고, 진행 중인 주가 증감을 오염시키지 않는다
- [ ] 샘플 모드로 사내 DB 없이 전 화면이 돈다
- [ ] 기준값이 전부 `capa_config.py` 에 있다
- [ ] `pytest -q tests/` 전부 통과
- [ ] 웹 · exe 둘 다 같은 코드로 나온다
