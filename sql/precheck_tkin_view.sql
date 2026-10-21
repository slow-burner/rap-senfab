/* ============================================================================
   계측 사전 지정 현황 (TKIN 현황 · Real time)
   Spotfire 데이터 테이블 "MIBKM_MANUAL_RESER_24H" 의 조인·계산 컬럼을 SQL 로 옮긴 것.

   Spotfire 단계           →  이 쿼리
   ---------------------------------------------------------------------------
   기준 테이블             →  REQ_BASE   fab.m_lot_actv_req
   1. MIBKM_LOT_TRANSN_TKOUT → HIST     fab.m_lot_transn_hist
   2. MIBKM_TPSS_DELAY_...28DAY → APT   fab.m_lot_spx
   3. MIBKM_DESIGNRULE     →  DR        fab.g_tpss_design_rule_record
   4. AREA.USER (ILP 406164) → EMP      dscrm_ds.crmadmin_if_zto_employee
   (Spotfire 에 없는 보강)  → STEP_M   fab.m_step  (대기 건의 EQP_TYPE·STEP)
   (Spotfire 에 없는 보강)  → APT_STEP fab.m_lot_spx (PPID 없는 대기 건의 1매 ST)
   (처음 주신 SQL 에 있던) → WIP      fab.m_wip_current (LOT 의 현재 STEP)
   5. 계산 컬럼 대상 / FORECAST_APT / LINEP → CALC

   ※ "Left single match join" 은 여러 건이 맞아도 1건만 붙인다는 뜻이다.
      SQL 에 같은 조인이 없으므로 오른쪽 테이블을 ROW_NUMBER / GROUP BY 로
      키당 1행으로 줄인 뒤 LEFT JOIN 한다. 이걸 빼면 재측정 LOT 에서 행이
      불어나 FORECAST_APT 합계가 과대 집계된다.

   ※ "Treat empty values as equal: No" 는 키가 비어 있으면 매칭하지 않는다는
      뜻이다. SQL 은 NULL 끼리 자동으로 안 맞지만 빈 문자열은 맞으므로,
      오른쪽 키에 NULL/공백 제외 조건을 넣어 동작을 맞춘다.

   DB: Oracle 기준. MySQL 은 파일 맨 아래 주석 참고.
   ============================================================================ */

WITH
/* ---------------------------------------------------------------------------
   [기준] 사전 지정 요청 — 최근 24시간
   Spotfire 테이블 이름의 24H 가 이 조건이다.
   --------------------------------------------------------------------------- */
REQ_BASE AS (
    SELECT
        AR.LINE_ID,
        AR.LOT_ID,
        AR.PROCESS_ID,
        AR.ACTV_STEP_SEQ,
        AR.ACTV_SLOT_ID,
        AR.REQ_QTY,
        AR.REQ_STATUS,
        AR.REQ_STATUS_SEQ,
        AR.REQUEST_TYPE,                 -- 매뉴얼/자동 구분 후보. 코드값 확인 필요
        AR.REQUEST_COMMENT,
        AR.ROOM_NAME,
        AR.UPDATE_DATE,
        AR.REQUESTER_ID                  -- 요청자 사번. 조인 4의 EMP_NO 와 맞춘다
    FROM   fab.m_lot_actv_req AR
    /* 조회 기간. 프로그램이 :d_from / :d_to 를 넘긴다.
       SQL 툴에서 직접 돌릴 때는 아래처럼 날짜 리터럴로 바꿔 쓴다.
         AR.UPDATE_DATE >= TO_DATE('2026-10-18','YYYY-MM-DD')
         AR.UPDATE_DATE <  TO_DATE('2026-10-22','YYYY-MM-DD')
       Spotfire 의 MANUAL_RESER_24H 와 똑같이 보려면 24시간으로 준다. */
    WHERE  AR.UPDATE_DATE >= :d_from
      AND  AR.UPDATE_DATE <  :d_to
),

/* ---------------------------------------------------------------------------
   [조인 1] fab.m_lot_transn_hist  (Spotfire: MIBKM_LOT_TRANSN_TKOUT)
     Matched : LOT_ID - LOT_ID , ACTV_STEP_SEQ - STEP_SEQ
     Added   : LOT_TRANSN_TYPE, PPID, PROCESS_EQP_ID,
               TKIN_DATE, PROCESS_START_DATE, SLOT_ID
     Join    : Left single match join

   Spotfire 가 LOT_ID + STEP_SEQ 두 개로만 맞추므로 여기서도 그 두 개로만
   줄인다. 같은 LOT·STEP 이력이 여러 건이면 가장 최근 트랙인 1건을 쓴다.
   EQP_TYPE / STEP_ID / LOT_TYPE 은 Spotfire Added 목록에는 없지만
   결과 뷰에 필요하므로 같은 조인에서 같이 가져온다(추가 비용 없음).
   --------------------------------------------------------------------------- */
HIST_RANKED AS (
    SELECT
        H.LOT_ID,
        H.STEP_SEQ,
        H.LOT_TRANSN_TYPE,
        H.PPID,
        H.PROCESS_EQP_ID,
        H.TKIN_DATE,
        H.TKOUT_DATA,                   -- 트랙아웃. 파티션 키
        H.PROCESS_START_DATE,
        H.SLOT_ID,
        H.EQP_TYPE,
        H.STEP_ID,
        H.STEP_DESC,
        H.LOT_TYPE,
        H.TO_PROCESS_UNIT,              -- LINEP 분류에 쓰는 PROCESS_UNIT
        /* 같은 LOT·STEP 이력이 여러 건이면 가장 최근 트랙인 1건.
           LOT_TRANSN_TIME 은 쓰지 않는 컬럼이라 LAST_UPDATE_DATE 를 마지막
           동점 처리 기준으로 쓴다. */
        ROW_NUMBER() OVER (
            PARTITION BY H.LOT_ID, H.STEP_SEQ
            ORDER BY     H.TKIN_DATE          DESC,
                         H.PROCESS_START_DATE DESC,
                         H.LAST_UPDATE_DATE   DESC
        ) AS RN
    FROM   fab.m_lot_transn_hist H
    /* 파티션 키는 LINE_ID 와 TKOUT_DATA 다. 둘 다 걸어야 파티션이 잘린다.
       TKIN_DATE 로 거르면 파티션 가지치기가 안 돼 팹 전체 이력을 읽는다.
       ★ TKOUT_DATA IS NULL 을 반드시 같이 둔다. 지금 설비에 들어가 있는
         (= TKIN 했고 아직 TKOUT 안 한) LOT 이 바로 'TKIN 현황' 의 대상인데,
         TKOUT_DATA >= ... 만 쓰면 그 행이 통째로 빠진다. */
    WHERE  ( H.TKOUT_DATA >= :d_from - 8 OR H.TKOUT_DATA IS NULL )
      AND  H.LINE_ID  IN (SELECT DISTINCT LINE_ID FROM REQ_BASE)
      AND  H.LOT_ID   IS NOT NULL            -- 빈 값은 매칭하지 않음
      AND  H.STEP_SEQ IS NOT NULL
),
HIST AS (
    SELECT * FROM HIST_RANKED WHERE RN = 1
),

/* ---------------------------------------------------------------------------
   [조인 2] fab.m_lot_spx  (Spotfire: MIBKM_TPSS_DELAY_PRODUCT_28DAY)
     Matched : PPID - PPID , PROCESS_ID - PROCESS_ID , ACTV_STEP_SEQ - LOCATION_ID
     Added   : AVG_APT
     Join    : Left single match join

   AST_TIME = 1매 기준 평균 시간. 테이블 이름의 28DAY 를 기간 조건으로 맞춘다.
   APT_N(표본 수)은 Spotfire 에 없지만, 표본이 1~2건인 PPID 는 평균을 믿을 수
   없으므로 화면에서 '추정치' 표시를 붙이는 데 쓴다.
   AREA(=LINE_ID)는 Spotfire 매칭 키에 없어서 뺐다. 파일 하단 참고.
   --------------------------------------------------------------------------- */
APT AS (
    SELECT
        S.AREA AS LINE_ID,
        S.PPID,
        S.PROCESS_ID,
        S.LOCATION_ID,
        AVG(S.AST_TIME) AS AVG_APT,
        COUNT(*)        AS APT_N
    FROM   fab.m_lot_spx S
    /* 파티션 키는 AREA 와 OUT_TIME 이다. 둘 다 걸어야 파티션이 잘린다.
       Spotfire 매칭 키에는 AREA 가 없었지만, 빼면 전 라인 파티션을 읽고
       게다가 라인이 섞인 평균이 나온다. AREA = 다른 테이블의 LINE_ID 다. */
    WHERE  S.OUT_TIME >= :d_to - 28
      AND  S.AREA IN (SELECT DISTINCT LINE_ID FROM REQ_BASE)
      AND  S.PPID        IS NOT NULL
      AND  S.PROCESS_ID  IS NOT NULL
      AND  S.LOCATION_ID IS NOT NULL
    GROUP BY S.AREA, S.PPID, S.PROCESS_ID, S.LOCATION_ID
),

/* ---------------------------------------------------------------------------
   [보강] fab.m_lot_spx — PPID 없는 대기 건용 STEP 평균

   Spotfire 에는 없다. 처음 주신 SQL 의 APT_STEP 과 같은 역할이다.
   PPID 는 트랙인 이력에서 오므로 아직 측정 안 한 대기 건은 PPID 가 없고,
   그러면 PPID 단위 평균(APT)이 안 붙어 예상 시간이 통째로 빈다.
   사전 지정 관리는 '아직 안 한 건'을 보는 게 목적이라 그게 비면 쓸모가 없다.
   그래서 PPID 를 뺀 STEP 단위 평균을 따로 만들어 받침으로 쓴다.
   --------------------------------------------------------------------------- */
APT_STEP AS (
    SELECT
        S.AREA AS LINE_ID,
        S.PROCESS_ID,
        S.LOCATION_ID,
        AVG(S.AST_TIME) AS AVG_APT_STEP,
        COUNT(*)        AS APT_STEP_N
    FROM   fab.m_lot_spx S
    WHERE  S.OUT_TIME >= :d_to - 28
      AND  S.AREA IN (SELECT DISTINCT LINE_ID FROM REQ_BASE)
      AND  S.PROCESS_ID  IS NOT NULL
      AND  S.LOCATION_ID IS NOT NULL
    GROUP BY S.AREA, S.PROCESS_ID, S.LOCATION_ID
),

/* ---------------------------------------------------------------------------
   [조인 3] fab.g_tpss_design_rule_record  (Spotfire: MIBKM_DESIGNRULE)
     Matched : PROCESS_ID - PROCESSID
     Added   : DESIGN_RULE

   PK 가 (AREA, PROCESS_ID, DESIGN_RULE) 라 제품당 여러 행이다.
   single match 를 맞추려면 REV_TIME 최신 1건만 남겨야 한다.
   --------------------------------------------------------------------------- */
DR_RANKED AS (
    SELECT
        DRR.AREA AS LINE_ID,
        DRR.PROCESS_ID,
        DRR.DESIGN_RULE,
        ROW_NUMBER() OVER (
            /* PK 가 (AREA, PROCESS_ID, DESIGN_RULE) 다. AREA 를 빼고 묶으면
               같은 제품을 여러 라인에서 돌릴 때 다른 라인의 DESIGN_RULE 이
               붙고, 그게 LINEP 분류(P1D/P1F)까지 바꿔 버린다. */
            PARTITION BY DRR.AREA, DRR.PROCESS_ID
            ORDER BY     DRR.REV_TIME DESC, DRR.DESIGN_RULE DESC
        ) AS RN
    FROM   fab.g_tpss_design_rule_record DRR
    WHERE  DRR.AREA       IS NOT NULL
      AND  DRR.PROCESS_ID IS NOT NULL
),
DR AS (
    SELECT LINE_ID, PROCESS_ID, DESIGN_RULE FROM DR_RANKED WHERE RN = 1
),

/* ---------------------------------------------------------------------------
   [조인 4] dscrm_ds.crmadmin_if_zto_employee  (Spotfire: AREA.USER, ILP 406164)
     Matched : REQUESTER_ID - EMP_NO
     Added   : EMP_NAME(EMP_PRF_FLLNM), DEPT_NAME(ORG_DEPT_KOR_NM)
     Join    : Left outer join   ← single match 가 아니다

   Spotfire 원본은 outer join 이라 사번이 중복이면 행이 불어난다.
   여기서는 1행으로 줄여 막아 둔다. 원본 동작을 그대로 쓰려면 EMP_DEDUP 를
   빼고 EMP_RANKED 를 바로 조인한다.
   --------------------------------------------------------------------------- */
EMP_RANKED AS (
    SELECT
        E.EMP_NO,
        E.EMP_PRF_FLLNM   AS EMP_NAME,
        E.ORG_DEPT_KOR_NM AS DEPT_NAME,
        ROW_NUMBER() OVER (PARTITION BY E.EMP_NO ORDER BY E.EMP_PRF_FLLNM) AS RN
    FROM   dscrm_ds.crmadmin_if_zto_employee E
    WHERE  E.EMP_NO IS NOT NULL
),
EMP AS (
    SELECT EMP_NO, EMP_NAME, DEPT_NAME FROM EMP_RANKED WHERE RN = 1
),

/* ---------------------------------------------------------------------------
   [현재 재공] fab.m_wip_current — LOT 이 지금 어느 STEP 에 있나

   처음 주신 SQL 에 있던 조인이다(Spotfire 조인 목록에는 없다).
   ACTV_STEP_SEQ 는 '사전 지정을 건 계측 STEP', W.STEP_SEQ 는 'LOT 이 지금
   있는 STEP' 이다. 둘을 같이 봐야 그 사전 지정이 코앞인지 한참 뒤인지 안다.
   WIP 에 없으면(출하·폐기 등) 대기 현황으로 세면 안 되므로 계측유무 판정에도 쓴다.

   LINE_ID + LOT_ID + PROCESS_ID 로 묶는다. LOT 당 1행이 아니면 결과가 불어나
   FORECAST 합계가 과대 집계되므로 1행으로 줄여 둔다.
   --------------------------------------------------------------------------- */
WIP_RANKED AS (
    SELECT
        WC.LINE_ID,
        WC.LOT_ID,
        WC.PROCESS_ID,
        WC.STEP_SEQ      AS CUR_STEP_SEQ,
        WC.STEP_DESC     AS CUR_STEP_DESC,
        WC.EQP_TYPE      AS CUR_EQP_TYPE,
        WC.BAY_NAME,
        WC.LOT_TYPE      AS WIP_LOT_TYPE,
        WC.WORK_STATUS_SEQ,
        WC.LOT_STATUS_SEQ,
        ROW_NUMBER() OVER (
            PARTITION BY WC.LINE_ID, WC.LOT_ID, WC.PROCESS_ID
            ORDER BY     WC.LAST_UPDATE_DATE DESC
        ) AS RN
    FROM   fab.m_wip_current WC
    WHERE  WC.LINE_ID    IS NOT NULL
      AND  WC.LOT_ID     IS NOT NULL
      AND  WC.PROCESS_ID IS NOT NULL
),
WIP AS (
    SELECT LINE_ID, LOT_ID, PROCESS_ID, CUR_STEP_SEQ, CUR_STEP_DESC, CUR_EQP_TYPE,
           BAY_NAME, WIP_LOT_TYPE, WORK_STATUS_SEQ, LOT_STATUS_SEQ
    FROM   WIP_RANKED WHERE RN = 1
),

/* ---------------------------------------------------------------------------
   [보강] fab.m_step — 사전 지정 STEP 의 설비 유형과 공정 이름

   Spotfire 에는 없는 조인이다. 넣는 이유:
   EQP_TYPE 과 STEP_ID 는 지금 m_lot_transn_hist 에서 오는데, 트랙인 이력이
   없는 '대기 현황' 행은 그 값이 통째로 비어 버린다. 사전 지정 관리가 목적이면
   아직 측정 안 한 건이 가장 중요한데 설비 유형이 안 보이면 못 쓴다.
   m_lot_actv_req 에는 EQP_TYPE 이 없으므로(확인 완료) STEP 마스터에서 받는다.
   TKIN 현황만 볼 때는 이력 값이 우선이라 결과가 달라지지 않는다.
   --------------------------------------------------------------------------- */
STEP_M_RANKED AS (
    SELECT
        M.LINE_ID,
        M.PROCESS_ID,
        M.STEP_SEQ,
        M.EQP_TYPE,
        M.STEP_ID,
        M.STEP_DESC,
        ROW_NUMBER() OVER (
            PARTITION BY M.LINE_ID, M.PROCESS_ID, M.STEP_SEQ
            ORDER BY     M.STEP_ID
        ) AS RN
    FROM   fab.m_step M
    WHERE  M.LINE_ID    IS NOT NULL
      AND  M.PROCESS_ID IS NOT NULL
      AND  M.STEP_SEQ   IS NOT NULL
),
STEP_M AS (
    SELECT LINE_ID, PROCESS_ID, STEP_SEQ, EQP_TYPE, STEP_ID, STEP_DESC
    FROM   STEP_M_RANKED WHERE RN = 1
),

/* ---------------------------------------------------------------------------
   [연결] Spotfire 의 Add Data 4번을 한 번에 건다.
   --------------------------------------------------------------------------- */
JOINED AS (
    SELECT
        R.LINE_ID,
        R.LOT_ID,
        R.PROCESS_ID,
        R.ACTV_STEP_SEQ,
        R.ACTV_SLOT_ID,
        R.REQ_QTY,
        R.REQ_STATUS,
        R.REQ_STATUS_SEQ,
        R.REQUEST_TYPE,
        R.REQUEST_COMMENT,
        R.ROOM_NAME,
        R.UPDATE_DATE,
        R.REQUESTER_ID,

        H.LOT_TRANSN_TYPE,
        H.PPID,
        H.PROCESS_EQP_ID,
        H.TKIN_DATE,
        H.TKOUT_DATA,
        H.PROCESS_START_DATE,
        H.SLOT_ID,                      -- ★FORECAST_APT 는 이 컬럼을 쓴다
        /* 이력이 있으면 이력값, 대기 건이면 STEP 마스터값 */
        COALESCE(H.EQP_TYPE,  M.EQP_TYPE)  AS EQP_TYPE,
        COALESCE(H.STEP_ID,   M.STEP_ID)   AS STEP_ID,
        COALESCE(H.STEP_DESC, M.STEP_DESC) AS STEP_DESC,
        COALESCE(H.LOT_TYPE, W.WIP_LOT_TYPE) AS LOT_TYPE,

        W.LOT_ID         AS WIP_LOT_ID,     -- NULL 이면 지금 재공에 없는 LOT
        W.CUR_STEP_SEQ,                     -- LOT 이 지금 있는 STEP
        W.CUR_STEP_DESC,
        W.CUR_EQP_TYPE,
        W.BAY_NAME,
        W.WORK_STATUS_SEQ,                  -- RUN / HOLD / PRUN / WAIT
        W.LOT_STATUS_SEQ,
        H.TO_PROCESS_UNIT AS PROCESS_UNIT,   -- Spotfire LINEP 식의 PROCESS_UNIT

        A.AVG_APT,
        A.APT_N,
        AS2.AVG_APT_STEP,
        AS2.APT_STEP_N,
        D.DESIGN_RULE,
        U.EMP_NAME,
        U.DEPT_NAME
    FROM       REQ_BASE R
    LEFT JOIN  HIST H
           ON  R.LOT_ID        = H.LOT_ID
          AND  R.ACTV_STEP_SEQ = H.STEP_SEQ
    LEFT JOIN  APT A
           ON  R.LINE_ID       = A.LINE_ID
          AND  H.PPID          = A.PPID
          AND  R.PROCESS_ID    = A.PROCESS_ID
          AND  R.ACTV_STEP_SEQ = A.LOCATION_ID
    LEFT JOIN  DR D
           ON  R.LINE_ID       = D.LINE_ID
          AND  R.PROCESS_ID    = D.PROCESS_ID
    LEFT JOIN  EMP U
           ON  R.REQUESTER_ID  = U.EMP_NO
    LEFT JOIN  APT_STEP AS2
           ON  R.LINE_ID       = AS2.LINE_ID
          AND  R.PROCESS_ID    = AS2.PROCESS_ID
          AND  R.ACTV_STEP_SEQ = AS2.LOCATION_ID
    LEFT JOIN  WIP W
           ON  R.LINE_ID       = W.LINE_ID
          AND  R.LOT_ID        = W.LOT_ID
          AND  R.PROCESS_ID    = W.PROCESS_ID
    LEFT JOIN  STEP_M M
           ON  R.LINE_ID       = M.LINE_ID
          AND  R.PROCESS_ID    = M.PROCESS_ID
          AND  R.ACTV_STEP_SEQ = M.STEP_SEQ
),

/* ---------------------------------------------------------------------------
   [계산 컬럼] Spotfire Add calculated column 6 / 7 / 8
   --------------------------------------------------------------------------- */
CALC AS (
    SELECT
        J.*,

        /* 6. 대상
           Spotfire : CASE WHEN [UPDATE_DATE] <= [TKIN_DATE] THEN '대상' ELSE '비대상' END
           TKIN_DATE 가 NULL 이면 비교가 UNKNOWN 이라 ELSE 로 간다.
           즉 아직 트랙인 안 한 대기 건은 전부 '비대상' 이 된다 (Spotfire 원본과 동일).
           사전 감지가 목적이면 아래 주석의 대상2 를 쓴다. */
        CASE WHEN J.UPDATE_DATE <= J.TKIN_DATE THEN '대상' ELSE '비대상' END   AS 대상,
        /* CASE WHEN J.TKIN_DATE IS NULL              THEN '대상'
                WHEN J.UPDATE_DATE <= J.TKIN_DATE    THEN '대상'
                ELSE '비대상' END                                             AS 대상2, */

        /* 7. SLOT_COUNT / FORECAST_APT
           Spotfire : [AVG_APT] * (Len([SLOT_ID]) - Len(Substitute([SLOT_ID], ",", "")) + 1)
           [SLOT_ID] 는 m_lot_transn_hist 에서 붙여 온 '실제 트랙인된 슬롯' 이다.
           요청 슬롯(ACTV_SLOT_ID)이 아니다. 둘 다 내보내 비교할 수 있게 둔다. */
        LENGTH(J.SLOT_ID) - LENGTH(REPLACE(J.SLOT_ID, ',', '')) + 1            AS SLOT_COUNT,
        J.AVG_APT *
            ( LENGTH(J.SLOT_ID) - LENGTH(REPLACE(J.SLOT_ID, ',', '')) + 1 )    AS FORECAST_APT,

        CASE WHEN J.ACTV_SLOT_ID IS NULL THEN 0
             ELSE LENGTH(J.ACTV_SLOT_ID)
                  - LENGTH(REPLACE(J.ACTV_SLOT_ID, ',', '')) + 1
        END                                                                    AS REQ_SLOT_COUNT,

        /* 사전 관리용 예상 시간 — 위 FORECAST_APT 와 쓰임이 다르다.
           FORECAST_APT     : Spotfire 식 그대로. 실제 트랙인된 슬롯 기준이라
                              대기 건은 비어 있다. 실적 확인용.
           FORECAST_APT_REQ : 요청 슬롯 수 x 1매 ST 기준. 1매 ST 는 PPID 평균을
                              쓰되 PPID 가 없는 대기 건은 STEP 평균으로 받친다.
                              측정 전에 부하를 보려면 이 값을 쓴다. */
        COALESCE(J.AVG_APT, J.AVG_APT_STEP)                                    AS AVG_APT_USED,
        CASE WHEN J.AVG_APT IS NOT NULL THEN 'PPID'
             WHEN J.AVG_APT_STEP IS NOT NULL THEN 'STEP 평균'
             ELSE 'ST 미등록'
        END                                                                    AS ST_SOURCE,
        COALESCE(J.AVG_APT, J.AVG_APT_STEP) *
            CASE WHEN J.ACTV_SLOT_ID IS NULL THEN 0
                 ELSE LENGTH(J.ACTV_SLOT_ID)
                      - LENGTH(REPLACE(J.ACTV_SLOT_ID, ',', '')) + 1
            END                                                                AS FORECAST_APT_REQ,

        /* 8. LINEP
           PROCESS_UNIT = m_lot_transn_hist.TO_PROCESS_UNIT.
           PROCESS_UNIT 조건이 먼저 걸리고, 안 맞으면 DESIGN_RULE 첫 글자,
           그래도 안 맞으면 LINE_ID 그대로.
           트랙인 이력이 없는 대기 건은 PROCESS_UNIT 이 NULL 이라
           PFE1/PFE2/PFE3/KFE6/KFE7 로는 안 가고 아래 단계로 흘러간다. */
        CASE
            WHEN J.LINE_ID = 'PFBP' AND J.PROCESS_UNIT = 'PUP' THEN 'PFE1'
            WHEN J.LINE_ID = 'PFBB' AND J.PROCESS_UNIT = 'PUB' THEN 'PFE2'
            WHEN J.LINE_ID = 'PFB3' AND J.PROCESS_UNIT = 'PUT' THEN 'PFE3'
            WHEN J.LINE_ID = 'KFBH' AND J.PROCESS_UNIT = 'PUH' THEN 'KFE6'
            WHEN J.LINE_ID = 'KFBJ' AND J.PROCESS_UNIT = 'PUJ' THEN 'KFE7'
            WHEN J.LINE_ID = 'PFBP' AND SUBSTR(J.DESIGN_RULE, 1, 1) = 'D' THEN 'P1D'
            WHEN J.LINE_ID = 'PFBB' AND SUBSTR(J.DESIGN_RULE, 1, 1) = 'D' THEN 'P2D'
            WHEN J.LINE_ID = 'PFBP' THEN 'P1F'
            WHEN J.LINE_ID = 'PFBB' THEN 'P2F'
            WHEN J.LINE_ID = 'PFB3' THEN 'P3D'
            ELSE J.LINE_ID
        END                                                                    AS LINEP,

        /* 계측유무 — 처음 주신 SQL 의 VIEW_TYPE 과 같은 3분기.
           대기 현황은 '아직 트랙인 안 했고 + 지금 재공에 살아있는' LOT 만이다.
           재공에서 빠진 LOT(출하·폐기 등)까지 대기로 세면 부하가 부풀려진다. */
        CASE WHEN J.TKIN_DATE  IS NOT NULL THEN 'TKIN 현황'
             WHEN J.WIP_LOT_ID IS NOT NULL THEN '대기 현황'
             ELSE '완료/제외'
        END                                                                    AS 계측유무,

        /* 사전 지정 STEP 에 도착했나 — 현재 STEP 과 사전 지정 STEP 비교.
           STEP_SEQ 가 문자열이라 선후(앞인지 뒤인지)는 판단하지 않는다.
           선후까지 보려면 STEP_SEQ 채번 규칙을 확인한 뒤 비교식을 넣는다. */
        CASE WHEN J.CUR_STEP_SEQ IS NULL                    THEN '재공 없음'
             WHEN J.CUR_STEP_SEQ = J.ACTV_STEP_SEQ          THEN '해당 STEP'
             ELSE '다른 STEP'
        END                                                                    AS STEP_도달,

        /* 측정상태 — TKOUT_DATA 까지 보고 가른다.
           'TKIN 현황' 안에서도 지금 설비에 올라가 있는 건(측정중)과
           이미 끝난 건(완료)이 섞이므로, Real time 으로 보려면 측정중만 본다. */
        CASE WHEN J.TKIN_DATE  IS NULL     THEN '대기'
             WHEN J.TKOUT_DATA IS NULL     THEN '측정중'
             ELSE '완료'
        END                                                                    AS 측정상태
    FROM JOINED J
)

/* ---------------------------------------------------------------------------
   [결과 뷰] TKIN 현황 (Real time)
   대기 현황을 같이 보려면 아래 WHERE 의 계측유무 조건을 지운다.
   --------------------------------------------------------------------------- */
SELECT
    계측유무,
    측정상태,
    PROCESS_EQP_ID,
    ACTV_STEP_SEQ      AS ACTY_STEP_SEQ,
    CUR_STEP_SEQ,
    STEP_도달,
    CUR_STEP_DESC,
    BAY_NAME,
    WORK_STATUS_SEQ,
    PROCESS_ID         AS PROC_ID,
    EQP_TYPE,
    ACTV_SLOT_ID       AS ACTY_SLOT_ID,
    SLOT_ID,
    SLOT_COUNT,
    REQ_SLOT_COUNT,
    LOT_ID,
    LOT_TYPE,
    STEP_ID,
    PPID,
    AVG_APT,
    FORECAST_APT,
    AVG_APT_USED,
    FORECAST_APT_REQ,
    ST_SOURCE,
    APT_N,
    대상,
    REQUESTER_ID       AS REQ_USER_ID,
    EMP_NAME,
    DEPT_NAME,
    REQUEST_TYPE,
    REQ_STATUS,
    REQUEST_COMMENT    AS REQ_COMMENT,
    DESIGN_RULE,
    LINEP,
    LINE_ID,
    UPDATE_DATE        AS RESERVE_DATE,
    TKIN_DATE,
    TKOUT_DATA,
    PROCESS_START_DATE,
    LOT_TRANSN_TYPE
FROM   CALC
/* 처음 주신 SQL 과 같이 두 표(TKIN 현황 / 대기 현황)에 쓸 데이터를 함께 낸다.
   한 표만 쓰려면 계측유무로 거르고, 지금 설비에 올라가 있는 건만 보려면
   측정상태 조건까지 건다. */
WHERE  계측유무 IN ('TKIN 현황', '대기 현황')
  -- AND  계측유무 = 'TKIN 현황'
  -- AND  측정상태 = '측정중'
ORDER BY FORECAST_APT DESC NULLS LAST, TKIN_DATE DESC;


/* ============================================================================
   확인 완료 — 미확정 없음

   컬럼 정리표(사진·메모 재구성본)와 실제 DB 가 달랐던 것들. 전부 사내 확인됨.
     있음   : m_lot_actv_req.REQUESTER_ID / .REQUEST_COMMENT
              m_lot_transn_hist.TO_PROCESS_UNIT  (= LINEP 의 PROCESS_UNIT)
              m_lot_transn_hist.TKOUT_DATA       (트랙아웃. TKOUT_TIME 아님)
     없음   : m_lot_actv_req.EQP_TYPE            (m_step 에서 받는다)
     미사용 : m_lot_transn_hist.LOT_TRANSN_TIME  (정렬은 LAST_UPDATE_DATE)

   키 (성능·정확도에 직결)
     m_lot_transn_hist        파티션 키 : LINE_ID, TKOUT_DATA
     m_lot_spx                파티션 키 : AREA, OUT_TIME
     g_tpss_design_rule_record  PK      : AREA, PROCESS_ID, DESIGN_RULE
     → 셋 다 WHERE / GROUP BY / 조인에 반영했다. AREA 는 다른 테이블의 LINE_ID 다.

   ※ Spotfire 매칭 키에는 AREA 가 없었다. 라인을 넣은 쪽이 맞다고 보고 넣었으므로
     라인이 섞여 있던 Spotfire 결과와는 숫자가 다를 수 있다. 그게 정상이다.
     굳이 Spotfire 와 똑같이 맞춰야 하면 APT / APT_STEP / DR 의 LINE_ID 조건만 뺀다.
   ----------------------------------------------------------------------------
   Spotfire 와 결과가 달라 보일 때 먼저 볼 것
     - FORECAST_APT 가 비어 있다  → SLOT_ID(트랙인 슬롯)가 NULL. 대기 건은 정상.
                                     측정 전 부하는 FORECAST_APT_REQ 로 본다
     - 대기 건이 전부 '비대상'    → Spotfire 원본과 같은 동작. 대상2 주석 참고
     - 행 수가 Spotfire 보다 많다 → single match 축약(HIST/DR/EMP)이 빠졌는지 확인
     - 조회가 느리다 → 파티션 키가 WHERE 에 다 있는지 본다.
       m_lot_transn_hist = LINE_ID + TKOUT_DATA, m_lot_spx = AREA + OUT_TIME.
       TKIN_DATE 나 다른 컬럼으로 거르면 파티션이 안 잘린다
     - AVG_APT 가 전보다 자주 빈다 → 라인별로 묶기 시작해서 그렇다.
       그 라인에 그 PPID 실적이 없다는 뜻이고 ST_SOURCE 로 확인된다
     - 설비에 올라가 있는 LOT 이 안 보인다 → TKOUT_DATA IS NULL 조건이 빠졌다
   ----------------------------------------------------------------------------
   MySQL 로 옮길 때
     SYSDATE - 1        →  NOW() - INTERVAL 1 DAY
     SYSDATE - 8        →  NOW() - INTERVAL 8 DAY
     SYSDATE - 28       →  NOW() - INTERVAL 28 DAY
     SUBSTR(x, 1, 1)    →  SUBSTRING(x, 1, 1)
     CAST(NULL AS VARCHAR2(20)) → CAST(NULL AS CHAR(20))
     ORDER BY ... NULLS LAST    →  ORDER BY (FORECAST_APT IS NULL), FORECAST_APT DESC
     ※ Oracle 은 빈 문자열이 NULL 이지만 MySQL 은 아니다. MySQL 이면
       SLOT_COUNT 계산을 NULLIF(SLOT_ID,'') 로 감싸야 빈 값이 1로 세지 않는다.
   ============================================================================ */
