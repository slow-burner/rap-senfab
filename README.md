# 계측 사전 지정 부하 모니터

기술 부서가 Manual 로 걸어 둔 계측 사전 지정 때문에 계측 재공이 밀리는 것을
**측정이 돌기 전에** 잡는 Streamlit 대시보드.

핵심은 하나다. **총측정시간 = 1매 측정시간(PPID ST) × 사전 지정 매수** 를 LOT 단위로
합산해, 임계치를 넘는 LOT 을 알람으로 띄우고 요청 부서에 물량 조정을 요청한다.
측정 3시간짜리 PPID 를 무작위로 걸어 둔 건을 사전에 찾아내는 것이 목적이다.

## 화면

상단 탭 3개 + 기타 분석 9개, 모든 화면 위에 **총측정시간 임계 초과 알람 배너**가 고정으로 뜬다.

| 탭 | 내용 |
|---|---|
| 전체 현황 | KPI 4장 · 사전 지정 추이 · EQP×사유(또는 STEP·PPID×사유) 매트릭스 · 조정이 필요한 LOT |
| 부서별 Manual 사전 지정 현황 | 부서별/요청자별 총측정시간 · Manual 요청 현황 · 장시간 Manual LOT 히트맵 · 일별 최대 ST STEP·PPID |
| LOT 상세 조회 | STEP 단위 / LOT 단위 전환, 검색·사유·상태·EQP 필터, 엑셀 |

기타 분석: 부하·CAPA / 부서별 조정 요청 / Manual 상세 / Manual 주차 추이 /
ST TOP 10 / 사유 분류 / 일자 추이 / STEP 분포 / 전주 대비 PPID

### 알람

- 사이드바 **총측정시간 알람 임계 (분)** 에서 기준을 바꾼다 (기본 120분).
- LOT 의 사전 지정 총측정시간 **합**이 기준이다. 한 LOT 에 계측 STEP 이 여러 개 걸리면 합산한다.
- 주의 = 임계 이상, 위험 = 임계 × 2 이상 (`ALARM_CRIT_MULT`).
- 기본은 **미진행(예정)** 만 본다. 이미 측정이 끝난 LOT 은 조정할 수 없기 때문.
  사이드바 체크를 풀면 Cancel 을 뺀 전체가 대상이 된다.
- `부서별 조정 요청` 화면에서 부서별 대상 목록과 **복사용 요청 문안**을 바로 만든다.

### 조회 기간

기본 최근 3일, 최소 3일 (`capa_config.MIN_DAYS`). 하루만 골라도 3일로 늘려 조회한다.
비교 문구(`직전 N일 대비`)를 위해 `max(N일, 14일)` 만큼 앞에서부터 한 번에 가져온다.

## 파일

```
app.py             화면 전체
data_source.py     조회 (USE_SAMPLE 스위치 + _sample() + load_raw())
capa_config.py     CAPA · 임계값 · 계산식  ← 숫자는 전부 여기만 고친다
tests/test_app.py  화면 전수 검증 (pytest)
run_app.py         exe 진입점
build.bat          PyInstaller --onedir 빌드
config.ini.sample  DB 접속 정보 서식 (config.ini 로 복사해서 쓴다)
```

## 실행

```bash
pip install -r requirements.txt
streamlit run app.py          # 샘플 데이터로 바로 뜬다
pytest -q tests/test_app.py   # 화면 전수 검증 (142건)
```

exe: `build.bat` → `dist/precheck_monitor/precheck_monitor.exe`
(`config.ini` 를 exe 옆에 두고 DB 정보를 채운다)

## 실제 DB 로 바꾸기

1. `data_source.USE_SAMPLE = False`
2. `data_source._db()` 의 SQL 에서 테이블·컬럼명을 사내 실제 이름으로 바꾼다.
   - MySQL = 사전 지정 요청/승인 테이블 (`metro_precheck_request`)
   - PPID ST 기준표 (`metro_ppid_st`) → PPID 로 join
   - bdq = 계측 진행 여부 → `LOTID` + `STEPID` 로 merge
3. `config.ini` 에 접속 정보를 채운다. **port 는 int 변환 필수.**

### 데이터 계약 (이 컬럼 이름 그대로)

`요청일(Timestamp), LINEID, EQP_TYPE, PROCESSID, STEPID, STEP_SEQ, PPID,
DEPARTMENT, 요청자, LOTID, SLOTID, 지정매수, APT_매, 예상APT, 사유, 승인상태, 상태`

- `APT_매` = 1매당 측정시간(분), `예상APT` = `APT_매 × 지정매수` = 총측정시간(분)
- `사유` 는 철자가 정확히 일치해야 한다: `Manual` / `PM AUTO QUAL` / `APC` / `DSM`
- `승인상태` = `승인 완료` / `요청 대기`, `상태` = `완료` / `예정` / `Cancel`

> 데이터 컬럼을 바꾼 뒤에는 **서버를 재시작**한다 (`@st.cache_data` 에 옛 컬럼이 남는다).

## 실제 연결 전에 반드시 확인할 것

1. **CAPA 값** — `capa_config.EQP_CAPA` 의 설비대수·가동률·기본유입_분은 전부 예시다.
   라인 실측값으로 바꿔야 부하율이 의미를 갖는다.
2. **알람 임계치** — 기본 120분은 예시다. 라인의 계측 재공 여유에 맞춰 정한다.
3. **부하율 산정 가정** — 지금은 *조회 구간 전체의 미진행 ST* 를 *1일 여유 CAPA* 와 비교한다.
   요청 테이블에 **측정 예정일**이 있으면 날짜별 비교로 바꾸는 편이 정확하다.
4. **요청자 / ST / LINEID 컬럼** — 사내 테이블의 실제 컬럼명 확인.
5. **사유 코드** — 사내 코드값이 위 4가지 철자와 다르면 매핑을 넣는다.

## 수정할 때

- 계산식·기준값은 **`capa_config.py` 에만** 둔다. 화면에 숫자를 박지 않는다.
- 그래프 색은 2가지만. `C1 #12a37a`(Manual·미진행·고부하·강조) / `C2 #c9ecdd`(나머지).
  빨강은 그래프가 아니라 경고(KPI 증가, 배지, 지연 행)에만 쓴다.
- 위젯 key 는 고정한다. 동적 key 금지. 그래프 key 는 `chart()` 가 `g_` 를 붙여
  사이드바 필터 key 와 분리한다.
- 고치고 나면 `pytest -q tests/test_app.py` 가 전부 통과해야 한다.
