# 계측 사전 지정 부하 모니터

기술 부서가 Manual 로 걸어 둔 계측 사전 지정 때문에 계측 재공이 밀리는 것을
**측정이 돌기 전에** 잡는 Streamlit 대시보드.

핵심은 하나다. **총측정시간 = 1매 측정시간(PPID ST) × 사전 지정 매수** 를 LOT 단위로
합산해, 임계치를 넘는 LOT 을 알람으로 띄우고 요청 부서에 물량 조정을 요청한다.
측정 3시간짜리 PPID 를 무작위로 걸어 둔 건을 사전에 찾아내는 것이 목적이다.

## 바로 띄워 보기

```bash
pip install -r requirements.txt
streamlit run app.py
```

브라우저가 `http://localhost:8501` 을 연다. `data_source.USE_SAMPLE = True` 라
**DB 없이 샘플 데이터로 바로 돈다.** 화면과 계산을 확인하는 용도다.

## 화면

상단 탭 3개 + 기타 분석 11개. 모든 화면 위에 **총측정시간 임계 초과 알람 배너**가 고정으로 뜬다.

| 탭 | 내용 |
|---|---|
| 전체 현황 | KPI 4장 · 사전 지정 추이 · EQP×사유(또는 STEP·PPID×사유) 매트릭스 · 조정이 필요한 LOT |
| 부서별 Manual 사전 지정 현황 | 부서별/요청자별 총측정시간 · Manual 요청 현황 · 장시간 Manual LOT 히트맵 · 일별 최대 ST STEP·PPID |
| LOT 상세 조회 | STEP 단위 / LOT 단위 전환, 검색·사유·상태·EQP 필터, 엑셀 |

기타 분석: 부하·CAPA / 부서별 조정 요청 / Manual 상세 /
**주차별 부서별 현황** / **주차별 PPID·STEP Worst 10** / **주차별 요청자 Worst 10** /
ST TOP 10 / 사유 분류 / 일자 추이 / STEP 분포 / 전주 대비 PPID

### 알람

- 사이드바 **총측정시간 알람 임계 (분)** 에서 기준을 바꾼다 (기본 120분).
- LOT 의 사전 지정 총측정시간 **합**이 기준이다. 한 LOT 에 계측 STEP 이 여러 개 걸리면 합산한다.
- 주의 = 임계 이상, 위험 = 임계 × 2 이상 (`ALARM_CRIT_MULT`).
- 기본은 **미진행(예정)** 만 본다. 이미 측정이 끝난 LOT 은 조정할 수 없기 때문.
  사이드바 체크를 풀면 Cancel 을 뺀 전체가 대상이 된다.
- `부서별 조정 요청` 화면에서 부서별 대상 목록과 **복사용 요청 문안**을 바로 만든다.
  화면을 보는 것으로는 아무것도 안 바뀐다. 이 문안이 이 프로그램의 산출물이다.

### 주차별 3화면

세 화면 모두 **완료 건까지 포함한 최근 N주**(4/8/12주)를 모수로 쓰고, Manual 만,
Cancel 제외, 요청일의 ISO 주차(월요일 시작) 기준이다. 같은 주 합계가 세 화면에서
일치하는 것을 테스트로 고정해 뒀다.

- **진행 중인 주는 흐리게** 표시하고 증감은 끝난 주끼리만 비교한다. 섞으면 어느 부서든
  감소로 보여 증감이 통째로 거짓말이 된다.
- 순위만으로는 늘 같은 PPID 가 1위라 아무도 안 본다. **전주 순위 변동·신규 배지**가 있어야
  "지난주보다 나빠진 것"이 보인다.
- 요청자 화면 하단의 **읽는 기준**을 지우지 말 것. 평가로 쓰이면 사전 지정을 안 걸고
  구두로 부탁하는 식으로 우회하게 되고, 그러면 데이터가 망가져 화면 자체가 쓸모없어진다.

### 조회 기간

기본 최근 3일, 최소 3일 (`capa_config.MIN_DAYS`). 하루만 골라도 3일로 늘려 조회한다.
비교 문구(`직전 N일 대비`)를 위해 `max(N일, 14일)` 만큼 앞에서부터 한 번에 가져온다.
주차별 화면은 별도로 최근 N주를 가져온다.

## 파일

```
app.py                     화면 전체
data_source.py             조회 계층 (USE_SAMPLE 스위치 · SQL 실행 · 컬럼 매핑)
capa_config.py             임계값 · CAPA · 계산식 · 코드값 매핑  ← 숫자는 전부 여기만 고친다
sql/precheck_tkin_view.sql 실제 조회 SQL (프로그램이 이 파일을 그대로 읽어 쓴다)
tests/test_app.py          화면 전수 검증 (pytest)
tests/test_sql_mapping.py  SQL 출력 → 화면 컬럼 매핑 검증 (DuckDB, 사내 DB 불필요)
run_app.py                 exe 진입점
build.bat                  PyInstaller --onedir 빌드
config.ini.sample          DB 접속 정보 서식 (config.ini 로 복사해서 쓴다)
.streamlit/config.toml     테마 · 서버 옵션
```

`config.ini` 는 `.gitignore` 에 있고 `config.ini.sample` 만 올라간다.
계정 정보가 저장소에 남지 않게 하기 위해서다.

## 검증

```bash
pip install pytest duckdb
pytest -q tests/
```

174건. 고치고 나면 전부 통과해야 한다.

- `tests/test_app.py` — 기간 4종 × EQP 2종 × 14개 화면, 임계치 변경, 필터로 결과가
  0건이 되는 경우, 상단 탭 실제 클릭, 주차 3화면 × 기간 3 × 지표 3, 세 화면 합계 일치.
- `tests/test_sql_mapping.py` — `sql/precheck_tkin_view.sql` 을 DuckDB 로 실행해
  `data_source._map_db` 에 통과시킨다. **사내 DB 없이 배선을 검증한다.**
  SQL 의 출력 컬럼을 바꿨는데 매핑을 안 고치면 여기서 걸린다.

AppTest 는 레이아웃을 못 본다. 글자가 잘리거나 그래프가 겹치는 것은 headless 로 띄워
브라우저로 확인해야 한다.

## 실제 DB 로 바꾸기

```python
# data_source.py
USE_SAMPLE = False
```

`config.ini` 에 `[mysql]` 섹션(host / port / user / password / database)을 채운다.
**port 는 반드시 int 로 변환한다** (`data_source._connect`).

SQL 은 `sql/precheck_tkin_view.sql` 하나뿐이다. 프로그램이 그 파일을 그대로 읽어
`:d_from` / `:d_to` 바인드로 실행하므로, 수작업 조회와 프로그램이 갈라지지 않는다.
pymysql 은 `%(name)s` 형태를 쓰므로 `data_source._to_pymysql` 이 변환한다.
SQL 툴에서 직접 돌릴 때는 `:d_from` / `:d_to` 를 날짜 리터럴로 바꾸면 된다.

**MySQL 8 이상이 필요하다.** CTE 와 `ROW_NUMBER()` 를 쓰므로 5.7 에서는 안 돈다.

`fab.*` 테이블을 MySQL 이 아니라 사내 **bigdataquery(bdq)** 로 읽어야 하면
`data_source._db()` 만 바꾼다. 그 위 주석에 교체용 코드를 적어 뒀고,
`_map_db` 이후는 그대로 쓴다.

### 쓰는 테이블

| 역할 | 테이블 | 비고 |
|---|---|---|
| 사전 지정 요청 | `fab.m_lot_actv_req` | 기준 테이블 |
| 계측 이력 | `fab.m_lot_transn_hist` | 파티션 키 `LINE_ID` + `TKOUT_DATA` |
| 1매 ST | `fab.m_lot_spx` | 파티션 키 `AREA` + `OUT_TIME` |
| DESIGN_RULE | `fab.g_tpss_design_rule_record` | PK 에 `AREA` 포함 |
| 사원 | `dscrm_ds.crmadmin_if_zto_employee` | 사번으로 연결 |
| 현재 재공 | `fab.m_wip_current` | LOT 의 현재 STEP |
| STEP 마스터 | `fab.m_step` | 대기 건의 EQP_TYPE |

파티션 키를 WHERE 에 안 걸면 팹 전체를 읽는다. `AREA`(= 다른 테이블의 `LINE_ID`)를
빼면 라인이 섞인 값이 붙어 라인 분류와 예상 시간이 같이 틀린다. 둘 다 반영돼 있으니
성능이나 숫자가 이상하면 그 조건부터 본다.

## 붙이자마자 확인할 것

전부 `capa_config.py` 한 파일 안에 있다. 값이 오면 그 파일만 고친다.

1. **`AST_UNIT_MIN`** — `AST_TIME` 이 분이면 `1.0`, 초면 `1/60`.
   **이게 틀리면 모든 시간이 60배 어긋난다.** 임의 LOT 하나를 손으로 계산해 맞춰 본다.
2. **`REASON_MAP`** — 사내 `REQUEST_TYPE` 코드표. 지금은 모르는 코드를 전부 Manual 로 본다.
   관제는 놓치는 것보다 과다 감지가 낫기 때문인데, 코드표가 오면 정확해진다.
   ```sql
   SELECT REQUEST_TYPE, REQ_STATUS, COUNT(*) FROM fab.m_lot_actv_req
   WHERE UPDATE_DATE >= SYSDATE - 30 GROUP BY REQUEST_TYPE, REQ_STATUS ORDER BY 3 DESC;
   ```
3. **`EQP_CAPA`** — EQP TYPE 별 설비대수 · 가동률 · 기본유입_분. 지금은 예시값이라
   부하율이 의미가 없다. 실측값을 넣고 `CAPA_IS_SAMPLE = False` 로 바꾸면 화면의
   '예시값' 경고가 사라진다.
4. **`ALARM_THR_MIN`** — 총측정시간 알람 임계. 기본 120분은 예시다.
   계측 재공 여유에 맞춰 정한다. 화면에서도 바로 조정된다.

> 데이터 컬럼을 바꾼 뒤에는 **서버를 재시작**한다. `@st.cache_data` 에 옛 컬럼이 남는다.

## 개인 PC 배포

파이썬이 없는 PC 에서도 돌게 PyInstaller `--onedir` 로 묶는다.
`build.bat` 을 실행하거나, 같은 명령을 직접 친다.

```
pyinstaller run_app.py --name precheck_monitor --onedir --noconfirm ^
  --collect-all streamlit --copy-metadata streamlit --collect-all plotly ^
  --hidden-import openpyxl --hidden-import pymysql ^
  --collect-all bigdataquery ^
  --add-data "app.py;." --add-data "data_source.py;." ^
  --add-data "capa_config.py;." --add-data "sql;sql" ^
  --add-data ".streamlit;.streamlit"
```

`--add-data "sql;sql"` 을 빼면 안 된다. `data_source` 가 실행 중에
`sql/precheck_tkin_view.sql` 을 읽기 때문에, 빠지면 DB 모드에서 바로 죽는다.
`--copy-metadata streamlit` 도 필수다. 없으면 실행 시 `importlib.metadata` 에서 죽는다.
`bigdataquery` 는 사내 패키지라 공개 저장소에 없다. 사내 인덱스로 설치한다.

결과는 `dist/precheck_monitor/precheck_monitor.exe`.

`config.ini` 는 exe 옆에 둔다(묶지 않는다). 그래야 접속 정보를 재빌드 없이 바꾼다.
`dist/precheck_monitor/` 폴더를 통째로 압축해 전달하면 된다.

## 사내 웹 배포

리눅스 서버에 venv 로 올리고 systemd 로 상시 기동한다.
`--server.address 127.0.0.1` 로 묶고 앞에 nginx 를 세워 인증을 건다.
Streamlit 에는 자체 인증이 없다. nginx 에 **WebSocket 업그레이드 설정이 빠지면
화면이 계속 로딩만 돈다.**

## 수정할 때

- 계산식·기준값은 **`capa_config.py` 에만** 둔다. 화면에 숫자를 박지 않는다.
- 그래프 색은 2가지만. `C1 #12a37a`(Manual·미진행·고부하·강조) / `C2 #c9ecdd`(나머지).
  빨강은 그래프가 아니라 경고(KPI 증가, 배지, 지연 행)에만 쓴다.
- 위젯 key 는 고정한다. 동적 key 금지. 그래프 key 는 `chart()` 가 `g_` 를 붙여
  사이드바 필터 key 와 분리한다. 이걸 안 하면 key 가 겹쳐 화면이 통째로 죽는다.
- 엑셀 시트 이름은 `sheet_name()` 을 거친다. 주차 라벨(`10/13주`)의 `/` 때문에
  openpyxl 이 죽은 적이 있다.
- 고치고 나면 `pytest -q tests/` 가 전부 통과해야 한다.
