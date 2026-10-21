# AGENTS.md — 이 저장소에서 작업하는 규칙

> 파일 이름을 `AGENTS.md` 로 둔 이유: 코딩 에이전트가 관례로 찾는 이름이다.
> Claude Code 는 `CLAUDE.md` 도 읽으므로, 둘 다 쓸 거면 한쪽을 심볼릭 링크로 둔다.

## 이 저장소가 만드는 것

기술 부서가 Manual 로 걸어 둔 **계측 사전 지정** 때문에 계측 재공이 밀리는 것을
**측정이 돌기 전에** 잡는 Streamlit 웹 화면.

핵심 수식 하나로 전부 설명된다.

```
총측정시간 = 1매 측정시간(PPID ST) × 사전 지정 매수      ← LOT 단위로 합산
```

이 값이 임계치를 넘는 LOT 을 알람으로 띄우고, 요청 부서에 물량 조정을 요청한다.
**화면을 보는 것이 목적이 아니라, 부서에 보낼 조정 요청 문안을 만드는 것이 목적이다.**

## 기술 스택

| 항목 | 선택 | 비고 |
|---|---|---|
| 언어 | Python 3.11+ | 3.13.16 에서 검증 |
| 화면 | Streamlit 1.66 | 1.40+ 의 `segmented_control` 사용 |
| 웹 서버 | **uvicorn** (Streamlit 내장) | 1.66 부터 Tornado → Starlette + uvicorn |
| 그래프 | Plotly | matplotlib 금지 (exe 가 수백 MB 늘어난다) |
| DB | MySQL 8 + 사내 bigdataquery | CTE·윈도우 함수를 쓰므로 5.7 불가 |

**uvicorn 을 직접 띄우지 않는다.** `streamlit run app.py` 가 내부에서 uvicorn 을
구동한다. `uvicorn app:...` 같은 호출은 동작하지 않는다 (Streamlit 앱은 ASGI 앱이
아니다). 포트·주소·헤드리스는 전부 `streamlit run` 인자나 `.streamlit/config.toml`
로 준다.

## 디렉터리

```
app.py                     화면 전체 (단일 파일, 1700줄)
data_source.py             조회 계층 — USE_SAMPLE 스위치 · SQL 실행 · 컬럼 매핑
capa_config.py             임계값 · CAPA · 계산식 · 코드값 매핑
sql/precheck_tkin_view.sql 조회 SQL (프로그램이 이 파일을 그대로 읽는다)
tests/test_app.py          화면 전수 검증
tests/test_sql_mapping.py  SQL 출력 → 화면 컬럼 매핑 검증 (사내 DB 불필요)
docs/                      prd.md · erd.md · execution.md · wireframe.md
run_app.py · build.bat     exe 진입점 · 빌드
```

## 개발 명령

```bash
pip install -r requirements.txt
streamlit run app.py          # 샘플 데이터로 바로 뜬다 (USE_SAMPLE = True)
pytest -q tests/              # 174건. 고치고 나면 전부 통과해야 한다
```

## 어기면 안 되는 것

1. **계산식과 기준값은 `capa_config.py` 에만 둔다.**
   화면이나 SQL 에 숫자를 박지 않는다. 박는 순간 "이 값이 어디서 왔나" 를 아무도
   추적하지 못한다.

2. **그래프 색은 2가지만.**
   `C1 #12a37a` = Manual · 미진행 · 고부하 · 강조 / `C2 #c9ecdd` = 나머지.
   범주가 4개 이상이면 `Manual vs 기타`, `예정 vs 완료`, `선택 강조` 중 하나로 바꾼다.
   빨강 `#c0392b` 은 그래프가 아니라 경고(KPI 증가, 배지, 지연 행)에만 쓴다.

3. **위젯 key 는 고정한다.** 동적 key(`w_pick_{x}`) 금지.
   **그래프 key 에는 `g_` 접두어를 붙인다** (`chart()` 가 자동으로 붙인다).
   안 붙이면 사이드바 필터 key 와 겹쳐 화면이 통째로 죽는다. 실제로 겪었다.

4. **고치고 나면 `pytest -q tests/` 가 전부 통과해야 한다.**
   Streamlit 은 화면을 위에서 아래로 매번 다시 실행한다. 한 화면을 고치면 전혀
   다른 화면이 깨진다. 손으로 들어가 확인하는 걸로는 못 잡는다.

5. **화면 글자는 한글.** 데이터 값(EQP, PPID, LINEID)은 영문 그대로.

## 데이터 계약

`data_source.load_raw(d_from, d_to)` 가 돌려주는 컬럼. **화면은 이 이름만 쓴다.**

```
요청일(datetime) · LINEID · EQP_TYPE · PROCESSID · STEPID · STEP_SEQ · PPID
DEPARTMENT · 요청자 · LOTID · SLOTID · 지정매수(int) · APT_매 · 예상APT
사유 · 승인상태 · 상태
```

- `사유` 는 철자가 정확히 일치해야 한다: `Manual` / `PM AUTO QUAL` / `APC` / `DSM`
- `상태` : `예정`(대기) / `진행`(측정중) / `완료` / `Cancel`
- SQL 컬럼 → 이 이름으로 바꾸는 곳은 `data_source.SQL_TO_APP` 한 군데다.

## 자주 깨지는 자리

실제로 겪은 것만 적는다.

| 증상 | 원인 | 대응 |
|---|---|---|
| `DuplicateWidgetID` 로 화면 전체 백지 | 위젯 key 충돌 | 그래프 key 에 `g_` 접두어 |
| 없는 컬럼 에러가 계속 남 | `@st.cache_data` 에 옛 컬럼이 남음 | **서버 재시작** |
| 엑셀 다운로드가 죽음 | 시트 이름에 `/` (주차 라벨 `10/13주`) | `sheet_name()` 을 거친다 |
| 조회가 수십 초 | 파티션 키를 WHERE 에 안 걸었다 | ERD 의 키 표 참고 |
| 라인 분류·예상시간이 동시에 틀림 | 조인에서 `AREA`(=LINE_ID) 누락 | 라인을 키에 넣는다 |
| 대기 건이 전부 비어 보임 | `TKOUT_DATA IS NULL` 조건 누락 | 측정중 LOT 이 통째로 빠진다 |
| 총측정시간이 부풀려짐 | `NULLIF(SLOT_ID,'')` 누락 | MySQL 은 빈 문자열 ≠ NULL |

## 하지 말 것

- `matplotlib` 추가 (Styler.background_gradient 포함). exe 가 비대해진다.
- 실제 DB 접속 정보를 저장소에 커밋. `config.ini` 는 `.gitignore` 에 있다.
- 검증 없이 "동작합니다" 라고 보고. 돌려 보고 결과를 붙인다.
- 컬럼 정리표(엑셀)만 보고 "이 컬럼은 없다" 고 단정.
  그 표는 사진·메모 재구성본이다. `SELECT * FROM <테이블> WHERE ROWNUM <= 5` 로
  실제 DB 를 본다. 실제로 멀쩡한 컬럼을 없다고 보고 우회 조인을 넣은 적이 있다.

## 작업 순서 제안

1. `docs/prd.md` 로 무엇을 왜 만드는지 확인
2. `docs/erd.md` 로 데이터 구조와 키 확인
3. `docs/wireframe.md` 로 화면 구조 확인
4. `docs/execution.md` 의 단계 순서대로 구현
5. 각 단계의 완료 기준(DoD)을 만족하면 다음 단계로
