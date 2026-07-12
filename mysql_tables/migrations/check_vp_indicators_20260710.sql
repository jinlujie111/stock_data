-- =============================================================================
-- VP 六维指标校验 SQL（20260710 或任意交易日）
-- 用法: mysql -u... -p stock_data < mysql_tables/migrations/check_vp_indicators_20260710.sql
-- 说明:
--   · 与 ETL 逻辑对齐: etl/volume_price/industry_agg.py + industry_score.py
--   · 百分位为 pandas rank(pct=True)*100，MySQL 用 PERCENT_RANK 近似，允许 ±1.5 误差
--   · continuity_strength 含衰减递推，SQL 仅做量级/符号抽检，精确值请用 Python 脚本
-- 判定:
--   · 每条校验 SELECT 含 expected（预期）与 status（PASS/FAIL/INFO）
--   · status = PASS 表示达到预期；末尾 FINAL-SUMMARY 全 PASS 即认为 batch 无误
-- =============================================================================

USE stock_data;

SET @td = '2026-07-10';
SET @w   = 20;
SET @tol = 0.02;          -- 原始指标相对误差容忍
SET @pct_tol = 1.5;        -- 百分位子分容忍（pandas vs PERCENT_RANK）

-- 预期阈值（可按环境调整）
SET @min_score_rows  = 100;   -- 板块评分行数下限
SET @min_factor_rows = 3000;  -- 个股因子行数下限

-- 20 交易日前的 lag 日（与 ETL list_trading_days(trade_date, 21) 的 days[0] 一致）
-- ods_trading_day 仅含 trade_date，表中一行即一个交易日
SET @lag_td = (
    SELECT trade_date FROM (
        SELECT trade_date,
               ROW_NUMBER() OVER (ORDER BY trade_date DESC) AS rn
        FROM ods_trading_day
        WHERE trade_date <= @td
    ) t WHERE rn = 21
    LIMIT 1
);
-- fallback（无 ods_trading_day 时取消注释下面，注释上面）
-- SET @lag_td = (
--     SELECT trade_date FROM (
--         SELECT DISTINCT trade_date,
--                ROW_NUMBER() OVER (ORDER BY trade_date DESC) AS rn
--         FROM ods_stock_detail_di WHERE trade_date <= @td
--     ) t WHERE rn = 21 LIMIT 1
-- );

SELECT @td AS check_trade_date,
       @lag_td AS lag_trade_date_20d,
       @w AS vp_window,
       'NOT NULL' AS expected_lag,
       CASE WHEN @lag_td IS NOT NULL THEN 'PASS' ELSE 'FAIL' END AS status;

-- =============================================================================
-- CHK-0 基础产出
-- =============================================================================
SELECT 'CHK-0' AS chk, 'score_rows' AS item,
       COUNT(*) AS actual,
       CONCAT('>= ', @min_score_rows) AS expected,
       CASE WHEN COUNT(*) >= @min_score_rows THEN 'PASS' ELSE 'FAIL' END AS status
FROM dwm_industry_vp_score_di
WHERE trade_date = @td AND vp_window = @w;

SELECT 'CHK-0' AS chk, 'factor_rows' AS item,
       COUNT(*) AS actual,
       CONCAT('>= ', @min_factor_rows) AS expected,
       CASE WHEN COUNT(*) >= @min_factor_rows THEN 'PASS' ELSE 'FAIL' END AS status
FROM dwm_stock_vp_factor_di WHERE trade_date = @td AND vp_window = @w;

SELECT 'CHK-0' AS chk, 'strict_breakout_stocks' AS item,
       SUM(is_breakout_strict = 1) AS actual,
       '>= 0' AS expected,
       CASE WHEN SUM(is_breakout_strict = 1) >= 0 THEN 'PASS' ELSE 'FAIL' END AS status
FROM dwm_stock_vp_factor_di WHERE trade_date = @td AND vp_window = @w;

-- =============================================================================
-- CHK-1 行业量比 industry_vol_ratio_20 = 当日 total_amount / 近20日 total_amount 均值
-- 预期: mismatch_cnt = 0
-- =============================================================================
WITH hist AS (
    SELECT industry_code,
           trade_date,
           total_amount,
           AVG(total_amount) OVER (
               PARTITION BY industry_code
               ORDER BY trade_date
               ROWS BETWEEN 19 PRECEDING AND CURRENT ROW
           ) AS ma20_amt
    FROM dwm_industry_vp_agg_di
    WHERE vp_window = @w AND trade_date <= @td
)
SELECT 'CHK-1' AS chk, 'industry_vol_ratio_mismatch' AS item,
       COUNT(*) AS actual,
       0 AS expected,
       CASE WHEN COUNT(*) = 0 THEN 'PASS' ELSE 'FAIL' END AS status
FROM dwm_industry_vp_agg_di a
JOIN hist h
  ON h.industry_code = a.industry_code AND h.trade_date = a.trade_date
WHERE a.trade_date = @td AND a.vp_window = @w
  AND h.ma20_amt > 0
  AND ABS(a.industry_vol_ratio_20 - a.total_amount / h.ma20_amt) > @tol;

-- 明细（预期: 0 行；有行则 FAIL）
SELECT 'CHK-1-detail' AS chk,
       a.industry_code, a.industry_name,
       a.industry_vol_ratio_20 AS val_stored,
       ROUND(a.total_amount / h.ma20_amt, 6) AS calc,
       ROUND(a.industry_vol_ratio_20 - a.total_amount / h.ma20_amt, 6) AS diff,
       '0 rows' AS expected
FROM dwm_industry_vp_agg_di a
JOIN (
    SELECT industry_code, trade_date, total_amount,
           AVG(total_amount) OVER (
               PARTITION BY industry_code ORDER BY trade_date
               ROWS BETWEEN 19 PRECEDING AND CURRENT ROW
           ) AS ma20_amt
    FROM dwm_industry_vp_agg_di
    WHERE vp_window = @w AND trade_date <= @td
) h ON h.industry_code = a.industry_code AND h.trade_date = a.trade_date
WHERE a.trade_date = @td AND a.vp_window = @w
  AND h.ma20_amt > 0
  AND ABS(a.industry_vol_ratio_20 - a.total_amount / h.ma20_amt) > @tol
ORDER BY ABS(a.industry_vol_ratio_20 - a.total_amount / h.ma20_amt) DESC
LIMIT 20;

-- =============================================================================
-- CHK-2 上涨占比 rising_ratio = Σ(上涨股 circ_mv) / Σ(circ_mv)
-- 预期: mismatch_cnt = 0
-- =============================================================================
WITH board_codes AS (
    SELECT industry_code,
           industry_code AS bc1,
           REPLACE(industry_code, '.DC', '') AS bc2,
           CASE WHEN industry_code LIKE '%.DC' THEN industry_code
                ELSE CONCAT(industry_code, '.DC') END AS bc3
    FROM dwm_industry_vp_agg_di
    WHERE trade_date = @td AND vp_window = @w
),
member_mv AS (
    SELECT bc.industry_code,
           SUM(CASE WHEN COALESCE(f.pct_chg, 0) > 0
                    THEN CASE WHEN COALESCE(db.circ_mv, 0) > 0 THEN db.circ_mv ELSE 1 END
                    ELSE 0 END) AS rise_mv,
           SUM(CASE WHEN COALESCE(db.circ_mv, 0) > 0 THEN db.circ_mv ELSE 1 END) AS total_mv_w,
           SUM(CASE WHEN db.circ_mv IS NULL OR db.circ_mv <= 0 THEN 1 ELSE 0 END) AS no_mv_cnt
    FROM board_codes bc
    JOIN ods_dc_member_di mem
      ON mem.trade_date = @td
     AND mem.ts_code IN (bc.bc1, bc.bc2, bc.bc3)
    JOIN dwm_stock_vp_factor_di f
      ON f.trade_date = @td AND f.vp_window = @w AND f.ts_code = mem.con_code
    LEFT JOIN ods_daily_basic_di db
      ON db.trade_date = @td AND db.ts_code = mem.con_code
    GROUP BY bc.industry_code
)
SELECT 'CHK-2' AS chk, 'rising_ratio_mismatch' AS item,
       COUNT(*) AS actual,
       0 AS expected,
       CASE WHEN COUNT(*) = 0 THEN 'PASS' ELSE 'FAIL' END AS status
FROM dwm_industry_vp_agg_di a
JOIN member_mv m ON m.industry_code = a.industry_code
WHERE a.trade_date = @td AND a.vp_window = @w
  AND m.total_mv_w > 0
  AND ABS(a.rising_ratio - m.rise_mv / m.total_mv_w) > @tol;

SELECT 'CHK-2-detail' AS chk,
       a.industry_code, a.industry_name,
       a.rising_ratio AS val_stored,
       ROUND(m.rise_mv / m.total_mv_w, 6) AS calc,
       m.no_mv_cnt AS members_without_circ_mv,
       '0 rows' AS expected
FROM (
    WITH board_codes AS (
        SELECT industry_code,
               industry_code AS bc1,
               REPLACE(industry_code, '.DC', '') AS bc2,
               CASE WHEN industry_code LIKE '%.DC' THEN industry_code
                    ELSE CONCAT(industry_code, '.DC') END AS bc3
        FROM dwm_industry_vp_agg_di
        WHERE trade_date = @td AND vp_window = @w
    ),
    member_mv AS (
        SELECT bc.industry_code,
               SUM(CASE WHEN COALESCE(f.pct_chg, 0) > 0
                        THEN CASE WHEN COALESCE(db.circ_mv, 0) > 0 THEN db.circ_mv ELSE 1 END
                        ELSE 0 END) AS rise_mv,
               SUM(CASE WHEN COALESCE(db.circ_mv, 0) > 0 THEN db.circ_mv ELSE 1 END) AS total_mv_w,
               SUM(CASE WHEN db.circ_mv IS NULL OR db.circ_mv <= 0 THEN 1 ELSE 0 END) AS no_mv_cnt
        FROM board_codes bc
        JOIN ods_dc_member_di mem
          ON mem.trade_date = @td
         AND mem.ts_code IN (bc.bc1, bc.bc2, bc.bc3)
        JOIN dwm_stock_vp_factor_di f
          ON f.trade_date = @td AND f.vp_window = @w AND f.ts_code = mem.con_code
        LEFT JOIN ods_daily_basic_di db
          ON db.trade_date = @td AND db.ts_code = mem.con_code
        GROUP BY bc.industry_code
    )
    SELECT * FROM member_mv
) m
JOIN dwm_industry_vp_agg_di a ON m.industry_code = a.industry_code
WHERE a.trade_date = @td AND a.vp_window = @w
  AND m.total_mv_w > 0
  AND ABS(a.rising_ratio - m.rise_mv / m.total_mv_w) > @tol
ORDER BY ABS(a.rising_ratio - m.rise_mv / m.total_mv_w) DESC
LIMIT 20;

-- =============================================================================
-- CHK-3 严格突破占比 breakout_ratio = Σ(严格突破成交额) / 板块总成交额
-- 预期: mismatch_cnt = 0
-- =============================================================================
WITH board_codes AS (
    SELECT industry_code,
           industry_code AS bc1,
           REPLACE(industry_code, '.DC', '') AS bc2,
           CASE WHEN industry_code LIKE '%.DC' THEN industry_code
                ELSE CONCAT(industry_code, '.DC') END AS bc3
    FROM dwm_industry_vp_agg_di
    WHERE trade_date = @td AND vp_window = @w
),
brk AS (
    SELECT bc.industry_code,
           SUM(CASE WHEN f.is_breakout_strict = 1 THEN COALESCE(f.amount, 0) ELSE 0 END) AS brk_amt,
           SUM(COALESCE(f.amount, 0)) AS tot_amt
    FROM board_codes bc
    JOIN ods_dc_member_di mem
      ON mem.trade_date = @td
     AND mem.ts_code IN (bc.bc1, bc.bc2, bc.bc3)
    JOIN dwm_stock_vp_factor_di f
      ON f.trade_date = @td AND f.vp_window = @w AND f.ts_code = mem.con_code
    GROUP BY bc.industry_code
)
SELECT 'CHK-3' AS chk, 'breakout_ratio_mismatch' AS item,
       COUNT(*) AS actual,
       0 AS expected,
       CASE WHEN COUNT(*) = 0 THEN 'PASS' ELSE 'FAIL' END AS status
FROM dwm_industry_vp_agg_di a
JOIN brk b ON b.industry_code = a.industry_code
WHERE a.trade_date = @td AND a.vp_window = @w
  AND b.tot_amt > 0
  AND ABS(a.breakout_ratio - b.brk_amt / b.tot_amt) > @tol;

SELECT 'CHK-3-detail' AS chk,
       a.industry_code, a.industry_name,
       a.breakout_ratio AS val_stored,
       ROUND(b.brk_amt / b.tot_amt, 6) AS calc,
       '0 rows' AS expected
FROM (
    WITH board_codes AS (
        SELECT industry_code,
               industry_code AS bc1,
               REPLACE(industry_code, '.DC', '') AS bc2,
               CASE WHEN industry_code LIKE '%.DC' THEN industry_code
                    ELSE CONCAT(industry_code, '.DC') END AS bc3
        FROM dwm_industry_vp_agg_di
        WHERE trade_date = @td AND vp_window = @w
    ),
    brk AS (
        SELECT bc.industry_code,
               SUM(CASE WHEN f.is_breakout_strict = 1 THEN COALESCE(f.amount, 0) ELSE 0 END) AS brk_amt,
               SUM(COALESCE(f.amount, 0)) AS tot_amt
        FROM board_codes bc
        JOIN ods_dc_member_di mem
          ON mem.trade_date = @td
         AND mem.ts_code IN (bc.bc1, bc.bc2, bc.bc3)
        JOIN dwm_stock_vp_factor_di f
          ON f.trade_date = @td AND f.vp_window = @w AND f.ts_code = mem.con_code
        GROUP BY bc.industry_code
    )
    SELECT * FROM brk
) b
JOIN dwm_industry_vp_agg_di a ON b.industry_code = a.industry_code
WHERE a.trade_date = @td AND a.vp_window = @w
  AND b.tot_amt > 0
  AND ABS(a.breakout_ratio - b.brk_amt / b.tot_amt) > @tol
ORDER BY ABS(a.breakout_ratio - b.brk_amt / b.tot_amt) DESC
LIMIT 20;

-- =============================================================================
-- CHK-4 趋势强度 trend_return_20d = (close_t / close_lag - 1) * 100  （ods_dc_daily_di）
-- 预期: mismatch_cnt = 0
--       trend_null_etl_bug = 0（有指数却未落库才算 FAIL）
--       trend_null 因 ods_dc_daily_di 缺指数 → INFO，不影响 batch 判定
-- =============================================================================
WITH board_px AS (
    SELECT s.industry_code,
           s.trend_return_20d AS val_stored,
           c1.close AS close_t,
           c0.close AS close_lag,
           ROUND((c1.close / c0.close - 1) * 100, 6) AS calc
    FROM dwm_industry_vp_score_di s
    LEFT JOIN ods_dc_daily_di c1
      ON c1.trade_date = @td
     AND c1.ts_code IN (
         s.industry_code,
         REPLACE(s.industry_code, '.DC', ''),
         CASE WHEN s.industry_code LIKE '%.DC' THEN s.industry_code
              ELSE CONCAT(s.industry_code, '.DC') END
     )
    LEFT JOIN ods_dc_daily_di c0
      ON c0.trade_date = @lag_td
     AND c0.ts_code = c1.ts_code
    WHERE s.trade_date = @td AND s.vp_window = @w
)
SELECT 'CHK-4' AS chk, 'trend_return_20d_mismatch' AS item,
       COUNT(*) AS actual,
       0 AS expected,
       CASE WHEN COUNT(*) = 0 THEN 'PASS' ELSE 'FAIL' END AS status
FROM board_px
WHERE close_t IS NOT NULL AND close_lag IS NOT NULL AND close_lag > 0
  AND ABS(val_stored - calc) > 0.05;

SELECT 'CHK-4-detail' AS chk, industry_code, val_stored, calc,
       ROUND(val_stored - calc, 6) AS diff, close_t, close_lag,
       '0 rows' AS expected
FROM (
    WITH board_px AS (
        SELECT s.industry_code,
               s.trend_return_20d AS val_stored,
               c1.close AS close_t,
               c0.close AS close_lag,
               ROUND((c1.close / c0.close - 1) * 100, 6) AS calc
        FROM dwm_industry_vp_score_di s
        LEFT JOIN ods_dc_daily_di c1
          ON c1.trade_date = @td
         AND c1.ts_code IN (
             s.industry_code,
             REPLACE(s.industry_code, '.DC', ''),
             CASE WHEN s.industry_code LIKE '%.DC' THEN s.industry_code
                  ELSE CONCAT(s.industry_code, '.DC') END
         )
        LEFT JOIN ods_dc_daily_di c0
          ON c0.trade_date = @lag_td
         AND c0.ts_code = c1.ts_code
        WHERE s.trade_date = @td AND s.vp_window = @w
    )
    SELECT * FROM board_px
) board_px
WHERE close_t IS NOT NULL AND close_lag IS NOT NULL AND close_lag > 0
  AND ABS(val_stored - calc) > 0.05
ORDER BY ABS(val_stored - calc) DESC
LIMIT 20;

-- NULL 诊断：区分「缺板块指数」与「ETL 应算未算」
SELECT 'CHK-4' AS chk, 'trend_null_total' AS item,
       COUNT(*) AS actual,
       'INFO' AS expected,
       'INFO' AS status
FROM dwm_industry_vp_score_di
WHERE trade_date = @td AND vp_window = @w AND trend_return_20d IS NULL;

SELECT 'CHK-4' AS chk, 'trend_null_missing_index' AS item,
       COUNT(*) AS actual,
       'INFO' AS expected,
       'INFO' AS status
FROM (
    WITH null_boards AS (
        SELECT s.industry_code, s.industry_name, s.content_type, s.trend_return_20d
        FROM dwm_industry_vp_score_di s
        WHERE s.trade_date = @td AND s.vp_window = @w AND s.trend_return_20d IS NULL
    ),
    px AS (
        SELECT nb.industry_code,
               (SELECT MAX(d.close) FROM ods_dc_daily_di d
                WHERE d.trade_date = @td
                  AND d.ts_code IN (
                      nb.industry_code,
                      REPLACE(nb.industry_code, '.DC', ''),
                      CASE WHEN nb.industry_code LIKE '%.DC' THEN nb.industry_code
                           ELSE CONCAT(nb.industry_code, '.DC') END)) AS close_t,
               (SELECT MAX(d.close) FROM ods_dc_daily_di d
                WHERE d.trade_date = @lag_td
                  AND d.ts_code IN (
                      nb.industry_code,
                      REPLACE(nb.industry_code, '.DC', ''),
                      CASE WHEN nb.industry_code LIKE '%.DC' THEN nb.industry_code
                           ELSE CONCAT(nb.industry_code, '.DC') END)) AS close_lag
        FROM null_boards nb
    )
    SELECT * FROM px
    WHERE close_t IS NULL OR close_lag IS NULL OR close_lag <= 0
) missing_idx;

SELECT 'CHK-4' AS chk, 'trend_null_etl_bug' AS item,
       COUNT(*) AS actual,
       0 AS expected,
       CASE WHEN COUNT(*) = 0 THEN 'PASS' ELSE 'FAIL' END AS status
FROM (
    WITH null_boards AS (
        SELECT s.industry_code, s.trend_return_20d
        FROM dwm_industry_vp_score_di s
        WHERE s.trade_date = @td AND s.vp_window = @w AND s.trend_return_20d IS NULL
    ),
    px AS (
        SELECT nb.industry_code,
               (SELECT MAX(d.close) FROM ods_dc_daily_di d
                WHERE d.trade_date = @td
                  AND d.ts_code IN (
                      nb.industry_code,
                      REPLACE(nb.industry_code, '.DC', ''),
                      CASE WHEN nb.industry_code LIKE '%.DC' THEN nb.industry_code
                           ELSE CONCAT(nb.industry_code, '.DC') END)) AS close_t,
               (SELECT MAX(d.close) FROM ods_dc_daily_di d
                WHERE d.trade_date = @lag_td
                  AND d.ts_code IN (
                      nb.industry_code,
                      REPLACE(nb.industry_code, '.DC', ''),
                      CASE WHEN nb.industry_code LIKE '%.DC' THEN nb.industry_code
                           ELSE CONCAT(nb.industry_code, '.DC') END)) AS close_lag
        FROM null_boards nb
    )
    SELECT * FROM px
    WHERE close_t IS NOT NULL AND close_lag IS NOT NULL AND close_lag > 0
) etl_bug;

SELECT 'CHK-4-null-detail' AS chk,
       nb.industry_code, nb.industry_name, nb.content_type,
       nb.trend_return_20d AS val_stored,
       px.close_t, px.close_lag, @lag_td AS lag_trade_date,
       CASE
           WHEN px.close_t IS NULL AND px.close_lag IS NULL THEN 'missing_both_closes'
           WHEN px.close_t IS NULL THEN 'missing_close_t'
           WHEN px.close_lag IS NULL OR px.close_lag <= 0 THEN 'missing_close_lag'
           ELSE 'should_have_value'
       END AS null_reason,
       CASE
           WHEN px.close_t IS NOT NULL AND px.close_lag IS NOT NULL AND px.close_lag > 0
           THEN 'FAIL'
           ELSE 'INFO'
       END AS expected
FROM (
    SELECT industry_code, industry_name, content_type, trend_return_20d
    FROM dwm_industry_vp_score_di
    WHERE trade_date = @td AND vp_window = @w AND trend_return_20d IS NULL
) nb
JOIN (
    SELECT nb2.industry_code,
           (SELECT MAX(d.close) FROM ods_dc_daily_di d
            WHERE d.trade_date = @td
              AND d.ts_code IN (
                  nb2.industry_code,
                  REPLACE(nb2.industry_code, '.DC', ''),
                  CASE WHEN nb2.industry_code LIKE '%.DC' THEN nb2.industry_code
                       ELSE CONCAT(nb2.industry_code, '.DC') END)) AS close_t,
           (SELECT MAX(d.close) FROM ods_dc_daily_di d
            WHERE d.trade_date = @lag_td
              AND d.ts_code IN (
                  nb2.industry_code,
                  REPLACE(nb2.industry_code, '.DC', ''),
                  CASE WHEN nb2.industry_code LIKE '%.DC' THEN nb2.industry_code
                       ELSE CONCAT(nb2.industry_code, '.DC') END)) AS close_lag
    FROM (
        SELECT industry_code FROM dwm_industry_vp_score_di
        WHERE trade_date = @td AND vp_window = @w AND trend_return_20d IS NULL
    ) nb2
) px ON px.industry_code = nb.industry_code
ORDER BY null_reason DESC, nb.industry_code;

-- =============================================================================
-- CHK-5 龙头强度 leader_strength = (Top3 circ_mv 涨幅均值 + Top3 量比均值) / 2
-- 预期: mismatch_cnt = 0
-- =============================================================================
WITH board_codes AS (
    SELECT industry_code,
           industry_code AS bc1,
           REPLACE(industry_code, '.DC', '') AS bc2,
           CASE WHEN industry_code LIKE '%.DC' THEN industry_code
                ELSE CONCAT(industry_code, '.DC') END AS bc3
    FROM dwm_industry_vp_agg_di
    WHERE trade_date = @td AND vp_window = @w
),
ranked AS (
    SELECT bc.industry_code,
           f.pct_chg,
           COALESCE(f.vol_ratio_20, 0) AS vol_ratio_20,
           COALESCE(db.circ_mv, 0) AS circ_mv,
           ROW_NUMBER() OVER (
               PARTITION BY bc.industry_code
               ORDER BY COALESCE(db.circ_mv, 0) DESC, f.ts_code
           ) AS rn
    FROM board_codes bc
    JOIN ods_dc_member_di mem
      ON mem.trade_date = @td
     AND mem.ts_code IN (bc.bc1, bc.bc2, bc.bc3)
    JOIN dwm_stock_vp_factor_di f
      ON f.trade_date = @td AND f.vp_window = @w AND f.ts_code = mem.con_code
    LEFT JOIN ods_daily_basic_di db
      ON db.trade_date = @td AND db.ts_code = mem.con_code
),
top3 AS (
    SELECT industry_code,
           ROUND((AVG(pct_chg) + AVG(vol_ratio_20)) / 2, 6) AS calc
    FROM ranked
    WHERE rn <= 3
    GROUP BY industry_code
)
SELECT 'CHK-5' AS chk, 'leader_strength_mismatch' AS item,
       COUNT(*) AS actual,
       0 AS expected,
       CASE WHEN COUNT(*) = 0 THEN 'PASS' ELSE 'FAIL' END AS status
FROM dwm_industry_vp_agg_di a
JOIN top3 t ON t.industry_code = a.industry_code
WHERE a.trade_date = @td AND a.vp_window = @w
  AND ABS(a.leader_strength - t.calc) > 0.05;

SELECT 'CHK-5-detail' AS chk,
       a.industry_code, a.industry_name,
       a.leader_strength AS val_stored, t.calc,
       ROUND(a.leader_strength - t.calc, 6) AS diff,
       '0 rows' AS expected
FROM (
    WITH board_codes AS (
        SELECT industry_code,
               industry_code AS bc1,
               REPLACE(industry_code, '.DC', '') AS bc2,
               CASE WHEN industry_code LIKE '%.DC' THEN industry_code
                    ELSE CONCAT(industry_code, '.DC') END AS bc3
        FROM dwm_industry_vp_agg_di
        WHERE trade_date = @td AND vp_window = @w
    ),
    ranked AS (
        SELECT bc.industry_code,
               f.pct_chg,
               COALESCE(f.vol_ratio_20, 0) AS vol_ratio_20,
               COALESCE(db.circ_mv, 0) AS circ_mv,
               ROW_NUMBER() OVER (
                   PARTITION BY bc.industry_code
                   ORDER BY COALESCE(db.circ_mv, 0) DESC, f.ts_code
               ) AS rn
        FROM board_codes bc
        JOIN ods_dc_member_di mem
          ON mem.trade_date = @td
         AND mem.ts_code IN (bc.bc1, bc.bc2, bc.bc3)
        JOIN dwm_stock_vp_factor_di f
          ON f.trade_date = @td AND f.vp_window = @w AND f.ts_code = mem.con_code
        LEFT JOIN ods_daily_basic_di db
          ON db.trade_date = @td AND db.ts_code = mem.con_code
    ),
    top3 AS (
        SELECT industry_code,
               ROUND((AVG(pct_chg) + AVG(vol_ratio_20)) / 2, 6) AS calc
        FROM ranked
        WHERE rn <= 3
        GROUP BY industry_code
    )
    SELECT * FROM top3
) t
JOIN dwm_industry_vp_agg_di a ON t.industry_code = a.industry_code
WHERE a.trade_date = @td AND a.vp_window = @w
  AND ABS(a.leader_strength - t.calc) > 0.05
ORDER BY ABS(a.leader_strength - t.calc) DESC
LIMIT 20;

-- =============================================================================
-- CHK-6 连续放量 continuity_strength（SQL 仅抽检）
-- 预期: bad_cnt = 0；sample 为 INFO 人工浏览
-- =============================================================================
SELECT 'CHK-6' AS chk, 'amount_streak_days_sample' AS item,
       a.industry_code, a.industry_name,
       a.amount_streak_days,
       a.continuity_strength,
       CASE WHEN a.total_amount > h.ma20_amt THEN 'above_ma' ELSE 'below_ma' END AS today_vs_ma20,
       'INFO' AS expected,
       'INFO' AS status
FROM dwm_industry_vp_agg_di a
JOIN (
    SELECT industry_code, trade_date, total_amount,
           AVG(total_amount) OVER (
               PARTITION BY industry_code ORDER BY trade_date
               ROWS BETWEEN 19 PRECEDING AND CURRENT ROW
           ) AS ma20_amt
    FROM dwm_industry_vp_agg_di
    WHERE vp_window = @w AND trade_date <= @td
) h ON h.industry_code = a.industry_code AND h.trade_date = a.trade_date
WHERE a.trade_date = @td AND a.vp_window = @w
ORDER BY a.continuity_strength DESC
LIMIT 10;

SELECT 'CHK-6' AS chk, 'continuity_strength_zero_but_streak' AS item,
       COUNT(*) AS actual,
       0 AS expected,
       CASE WHEN COUNT(*) = 0 THEN 'PASS' ELSE 'FAIL' END AS status
FROM dwm_industry_vp_agg_di
WHERE trade_date = @td AND vp_window = @w
  AND amount_streak_days > 0
  AND COALESCE(continuity_strength, 0) <= 0;

-- =============================================================================
-- CHK-7 VP 综合分 = 六维子分 × 权重（0.25/0.20/0.20/0.15/0.15/0.05）
-- 预期: mismatch_cnt = 0
-- =============================================================================
SELECT 'CHK-7' AS chk, 'vp_score_mismatch' AS item,
       COUNT(*) AS actual,
       0 AS expected,
       CASE WHEN COUNT(*) = 0 THEN 'PASS' ELSE 'FAIL' END AS status
FROM dwm_industry_vp_score_di
WHERE trade_date = @td AND vp_window = @w
  AND ABS(
        vp_score - ROUND(
            score_continuity * 0.25 + score_vol * 0.20 + score_trend * 0.20
          + score_breadth * 0.15 + score_breakout * 0.15 + score_leader * 0.05,
        2)
      ) > 0.02;

SELECT 'CHK-7-detail' AS chk,
       industry_code, industry_name, vp_score AS val_stored,
       ROUND(
         score_continuity * 0.25 + score_vol * 0.20 + score_trend * 0.20
       + score_breadth * 0.15 + score_breakout * 0.15 + score_leader * 0.05,
       2) AS calc,
       score_continuity, score_vol, score_trend, score_breadth, score_breakout, score_leader,
       '0 rows' AS expected
FROM dwm_industry_vp_score_di
WHERE trade_date = @td AND vp_window = @w
  AND ABS(
        vp_score - ROUND(
            score_continuity * 0.25 + score_vol * 0.20 + score_trend * 0.20
          + score_breadth * 0.15 + score_breakout * 0.15 + score_leader * 0.05,
        2)
      ) > 0.02
LIMIT 20;

-- =============================================================================
-- CHK-8 升序百分位：原始值更大 → 子分不应明显更低（合并池内）
-- 预期: violation_pairs = 0；spread <= @pct_tol
-- =============================================================================
SELECT 'CHK-8' AS chk, 'ascending_percentile_violation' AS item,
       COUNT(*) AS actual,
       0 AS expected,
       CASE WHEN COUNT(*) = 0 THEN 'PASS' ELSE 'FAIL' END AS status
FROM dwm_industry_vp_score_di a
JOIN dwm_industry_vp_score_di b
  ON b.trade_date = a.trade_date AND b.vp_window = a.vp_window
 AND a.industry_code < b.industry_code
WHERE a.trade_date = @td AND a.vp_window = @w
  AND a.continuity_strength > b.continuity_strength + 1e-9
  AND a.score_continuity + 0.01 < b.score_continuity;

SELECT 'CHK-8' AS chk, 'trend_zero_floor_spread' AS item,
       ROUND(MAX(score_trend) - MIN(score_trend), 4) AS actual,
       CONCAT('<= ', @pct_tol) AS expected,
       CASE WHEN MAX(score_trend) - MIN(score_trend) <= @pct_tol THEN 'PASS' ELSE 'FAIL' END AS status
FROM dwm_industry_vp_score_di
WHERE trade_date = @td AND vp_window = @w
  AND COALESCE(trend_return_20d, 0) <= 0;

-- =============================================================================
-- CHK-9 rank_vp：合并池唯一且与 vp_score 降序一致
-- 预期: dup_cnt = 0；mismatch_cnt = 0；score_order_violation = 0
-- 排序规则（与 ETL industry_score.py 一致）: vp_score DESC, industry_code ASC
-- =============================================================================
SELECT 'CHK-9' AS chk, 'rank_vp_duplicate' AS item,
       COUNT(*) AS actual,
       0 AS expected,
       CASE WHEN COUNT(*) = 0 THEN 'PASS' ELSE 'FAIL' END AS status
FROM (
    SELECT rank_vp, COUNT(*) AS n
    FROM dwm_industry_vp_score_di
    WHERE trade_date = @td AND vp_window = @w
    GROUP BY rank_vp HAVING n > 1
) t;

SELECT 'CHK-9' AS chk, 'rank_order_mismatch' AS item,
       COUNT(*) AS actual,
       0 AS expected,
       CASE WHEN COUNT(*) = 0 THEN 'PASS' ELSE 'FAIL' END AS status
FROM (
    SELECT industry_code, vp_score, rank_vp,
           ROW_NUMBER() OVER (ORDER BY vp_score DESC, industry_code) AS expected_rank
    FROM dwm_industry_vp_score_di
    WHERE trade_date = @td AND vp_window = @w
) x
WHERE rank_vp <> expected_rank;

SELECT 'CHK-9' AS chk, 'rank_score_order_violation' AS item,
       COUNT(*) AS actual,
       0 AS expected,
       CASE WHEN COUNT(*) = 0 THEN 'PASS' ELSE 'FAIL' END AS status
FROM dwm_industry_vp_score_di a
JOIN dwm_industry_vp_score_di b
  ON b.trade_date = a.trade_date AND b.vp_window = a.vp_window
 AND a.rank_vp < b.rank_vp
WHERE a.trade_date = @td AND a.vp_window = @w
  AND a.vp_score < b.vp_score;

SELECT 'CHK-9-detail' AS chk,
       x.industry_code, x.industry_name, x.content_type,
       x.vp_score, x.rank_vp, x.expected_rank,
       x.rank_vp - x.expected_rank AS rank_diff,
       '0 rows' AS expected
FROM (
    SELECT s.industry_code, s.industry_name, s.content_type,
           s.vp_score, s.rank_vp,
           ROW_NUMBER() OVER (ORDER BY s.vp_score DESC, s.industry_code) AS expected_rank
    FROM dwm_industry_vp_score_di s
    WHERE s.trade_date = @td AND s.vp_window = @w
) x
WHERE x.rank_vp <> x.expected_rank
ORDER BY ABS(x.rank_vp - x.expected_rank) DESC, x.vp_score DESC
LIMIT 20;

SELECT 'CHK-9' AS chk, 'vp_score_tie_groups' AS item,
       vp_score,
       COUNT(*) AS tie_cnt,
       'INFO' AS expected,
       'INFO' AS status
FROM dwm_industry_vp_score_di
WHERE trade_date = @td AND vp_window = @w
GROUP BY vp_score
HAVING COUNT(*) > 1
ORDER BY tie_cnt DESC, vp_score DESC
LIMIT 10;

-- =============================================================================
-- CHK-10 子分与 PERCENT_RANK 近似对比（六维，允许 @pct_tol）
-- 预期: 各维 diff 计数均为 0（或极少数边界并列可忽略）
-- =============================================================================
WITH pool AS (
    SELECT industry_code, industry_name,
           continuity_strength,
           industry_vol_ratio_20,
           GREATEST(COALESCE(trend_return_20d, 0), 0) AS trend_for_score,
           rising_ratio,
           breakout_ratio,
           leader_strength,
           score_continuity, score_vol, score_trend,
           score_breadth, score_breakout, score_leader,
           ROUND(PERCENT_RANK() OVER (ORDER BY continuity_strength) * 100, 2) AS pct_cont,
           ROUND(PERCENT_RANK() OVER (ORDER BY industry_vol_ratio_20) * 100, 2) AS pct_vol,
           ROUND(PERCENT_RANK() OVER (ORDER BY GREATEST(COALESCE(trend_return_20d,0),0)) * 100, 2) AS pct_trend,
           ROUND(PERCENT_RANK() OVER (ORDER BY rising_ratio) * 100, 2) AS pct_breadth,
           ROUND(PERCENT_RANK() OVER (ORDER BY breakout_ratio) * 100, 2) AS pct_breakout,
           ROUND(PERCENT_RANK() OVER (ORDER BY leader_strength) * 100, 2) AS pct_leader
    FROM dwm_industry_vp_score_di
    WHERE trade_date = @td AND vp_window = @w
)
SELECT 'CHK-10' AS chk, 'percentile_approx_diff' AS item,
       SUM(CASE WHEN ABS(score_continuity - pct_cont) > @pct_tol THEN 1 ELSE 0 END) AS cont_diff,
       SUM(CASE WHEN ABS(score_vol - pct_vol) > @pct_tol THEN 1 ELSE 0 END) AS vol_diff,
       SUM(CASE WHEN ABS(score_trend - pct_trend) > @pct_tol THEN 1 ELSE 0 END) AS trend_diff,
       SUM(CASE WHEN ABS(score_breadth - pct_breadth) > @pct_tol THEN 1 ELSE 0 END) AS breadth_diff,
       SUM(CASE WHEN ABS(score_breakout - pct_breakout) > @pct_tol THEN 1 ELSE 0 END) AS breakout_diff,
       SUM(CASE WHEN ABS(score_leader - pct_leader) > @pct_tol THEN 1 ELSE 0 END) AS leader_diff,
       0 AS expected_each_dim,
       CASE WHEN
           SUM(CASE WHEN ABS(score_continuity - pct_cont) > @pct_tol THEN 1 ELSE 0 END) = 0
        AND SUM(CASE WHEN ABS(score_vol - pct_vol) > @pct_tol THEN 1 ELSE 0 END) = 0
        AND SUM(CASE WHEN ABS(score_trend - pct_trend) > @pct_tol THEN 1 ELSE 0 END) = 0
        AND SUM(CASE WHEN ABS(score_breadth - pct_breadth) > @pct_tol THEN 1 ELSE 0 END) = 0
        AND SUM(CASE WHEN ABS(score_breakout - pct_breakout) > @pct_tol THEN 1 ELSE 0 END) = 0
        AND SUM(CASE WHEN ABS(score_leader - pct_leader) > @pct_tol THEN 1 ELSE 0 END) = 0
       THEN 'PASS' ELSE 'FAIL' END AS status
FROM pool;

-- =============================================================================
-- 汇总：Top10 全指标一览（INFO，人工对照）
-- =============================================================================
SELECT 'SUMMARY-TOP10' AS chk,
       rank_vp, content_type, industry_name,
       ROUND(vp_score, 2) AS vp_score,
       ROUND(continuity_strength, 4) AS cont_str,
       ROUND(industry_vol_ratio_20, 4) AS vol_ratio,
       ROUND(trend_return_20d, 4) AS ret20,
       ROUND(rising_ratio, 4) AS rise_ratio,
       ROUND(breakout_ratio, 4) AS brk_ratio,
       ROUND(leader_strength, 4) AS leader,
       ROUND(score_continuity, 2) AS s_cont,
       ROUND(score_vol, 2) AS s_vol,
       ROUND(score_trend, 2) AS s_trend,
       ROUND(score_breadth, 2) AS s_brd,
       ROUND(score_breakout, 2) AS s_brk,
       ROUND(score_leader, 2) AS s_leader,
       'INFO' AS expected
FROM dwm_industry_vp_score_di
WHERE trade_date = @td AND vp_window = @w
ORDER BY rank_vp
LIMIT 10;

-- =============================================================================
-- FINAL-SUMMARY：全部 status=PASS 即认为 run_vp_batch 执行正确
-- =============================================================================
SELECT chk, item, actual, expected, status
FROM (
    SELECT 'SETUP' AS chk, 'lag_trade_date' AS item,
           IFNULL(CAST(@lag_td AS CHAR), 'NULL') AS actual,
           'NOT NULL' AS expected,
           CASE WHEN @lag_td IS NOT NULL THEN 'PASS' ELSE 'FAIL' END AS status

    UNION ALL
    SELECT 'CHK-0', 'score_rows',
           CAST((SELECT COUNT(*) FROM dwm_industry_vp_score_di
                 WHERE trade_date = @td AND vp_window = @w) AS CHAR),
           CONCAT('>= ', @min_score_rows),
           CASE WHEN (SELECT COUNT(*) FROM dwm_industry_vp_score_di
                      WHERE trade_date = @td AND vp_window = @w) >= @min_score_rows
                THEN 'PASS' ELSE 'FAIL' END

    UNION ALL
    SELECT 'CHK-0', 'factor_rows',
           CAST((SELECT COUNT(*) FROM dwm_stock_vp_factor_di
                 WHERE trade_date = @td AND vp_window = @w) AS CHAR),
           CONCAT('>= ', @min_factor_rows),
           CASE WHEN (SELECT COUNT(*) FROM dwm_stock_vp_factor_di
                      WHERE trade_date = @td AND vp_window = @w) >= @min_factor_rows
                THEN 'PASS' ELSE 'FAIL' END

    UNION ALL
    SELECT 'CHK-1', 'industry_vol_ratio_mismatch',
           CAST((SELECT COUNT(*) FROM dwm_industry_vp_agg_di a
                 JOIN (
                     SELECT industry_code, trade_date, total_amount,
                            AVG(total_amount) OVER (
                                PARTITION BY industry_code ORDER BY trade_date
                                ROWS BETWEEN 19 PRECEDING AND CURRENT ROW
                            ) AS ma20_amt
                     FROM dwm_industry_vp_agg_di WHERE vp_window = @w AND trade_date <= @td
                 ) h ON h.industry_code = a.industry_code AND h.trade_date = a.trade_date
                 WHERE a.trade_date = @td AND a.vp_window = @w AND h.ma20_amt > 0
                   AND ABS(a.industry_vol_ratio_20 - a.total_amount / h.ma20_amt) > @tol) AS CHAR),
           '0', CASE WHEN (
                 SELECT COUNT(*) FROM dwm_industry_vp_agg_di a
                 JOIN (
                     SELECT industry_code, trade_date, total_amount,
                            AVG(total_amount) OVER (
                                PARTITION BY industry_code ORDER BY trade_date
                                ROWS BETWEEN 19 PRECEDING AND CURRENT ROW
                            ) AS ma20_amt
                     FROM dwm_industry_vp_agg_di WHERE vp_window = @w AND trade_date <= @td
                 ) h ON h.industry_code = a.industry_code AND h.trade_date = a.trade_date
                 WHERE a.trade_date = @td AND a.vp_window = @w AND h.ma20_amt > 0
                   AND ABS(a.industry_vol_ratio_20 - a.total_amount / h.ma20_amt) > @tol
           ) = 0 THEN 'PASS' ELSE 'FAIL' END

    UNION ALL
    SELECT 'CHK-2', 'rising_ratio_mismatch',
           CAST((
               WITH board_codes AS (
                   SELECT industry_code,
                          industry_code AS bc1,
                          REPLACE(industry_code, '.DC', '') AS bc2,
                          CASE WHEN industry_code LIKE '%.DC' THEN industry_code
                               ELSE CONCAT(industry_code, '.DC') END AS bc3
                   FROM dwm_industry_vp_agg_di
                   WHERE trade_date = @td AND vp_window = @w
               ),
               member_mv AS (
                   SELECT bc.industry_code,
                          SUM(CASE WHEN COALESCE(f.pct_chg, 0) > 0
                                   THEN CASE WHEN COALESCE(db.circ_mv, 0) > 0 THEN db.circ_mv ELSE 1 END
                                   ELSE 0 END) AS rise_mv,
                          SUM(CASE WHEN COALESCE(db.circ_mv, 0) > 0 THEN db.circ_mv ELSE 1 END) AS total_mv_w
                   FROM board_codes bc
                   JOIN ods_dc_member_di mem
                     ON mem.trade_date = @td
                    AND mem.ts_code IN (bc.bc1, bc.bc2, bc.bc3)
                   JOIN dwm_stock_vp_factor_di f
                     ON f.trade_date = @td AND f.vp_window = @w AND f.ts_code = mem.con_code
                   LEFT JOIN ods_daily_basic_di db
                     ON db.trade_date = @td AND db.ts_code = mem.con_code
                   GROUP BY bc.industry_code
               )
               SELECT COUNT(*) FROM dwm_industry_vp_agg_di a
               JOIN member_mv m ON m.industry_code = a.industry_code
               WHERE a.trade_date = @td AND a.vp_window = @w
                 AND m.total_mv_w > 0
                 AND ABS(a.rising_ratio - m.rise_mv / m.total_mv_w) > @tol
           ) AS CHAR),
           '0',
           CASE WHEN (
               WITH board_codes AS (
                   SELECT industry_code,
                          industry_code AS bc1,
                          REPLACE(industry_code, '.DC', '') AS bc2,
                          CASE WHEN industry_code LIKE '%.DC' THEN industry_code
                               ELSE CONCAT(industry_code, '.DC') END AS bc3
                   FROM dwm_industry_vp_agg_di
                   WHERE trade_date = @td AND vp_window = @w
               ),
               member_mv AS (
                   SELECT bc.industry_code,
                          SUM(CASE WHEN COALESCE(f.pct_chg, 0) > 0
                                   THEN CASE WHEN COALESCE(db.circ_mv, 0) > 0 THEN db.circ_mv ELSE 1 END
                                   ELSE 0 END) AS rise_mv,
                          SUM(CASE WHEN COALESCE(db.circ_mv, 0) > 0 THEN db.circ_mv ELSE 1 END) AS total_mv_w
                   FROM board_codes bc
                   JOIN ods_dc_member_di mem
                     ON mem.trade_date = @td
                    AND mem.ts_code IN (bc.bc1, bc.bc2, bc.bc3)
                   JOIN dwm_stock_vp_factor_di f
                     ON f.trade_date = @td AND f.vp_window = @w AND f.ts_code = mem.con_code
                   LEFT JOIN ods_daily_basic_di db
                     ON db.trade_date = @td AND db.ts_code = mem.con_code
                   GROUP BY bc.industry_code
               )
               SELECT COUNT(*) FROM dwm_industry_vp_agg_di a
               JOIN member_mv m ON m.industry_code = a.industry_code
               WHERE a.trade_date = @td AND a.vp_window = @w
                 AND m.total_mv_w > 0
                 AND ABS(a.rising_ratio - m.rise_mv / m.total_mv_w) > @tol
           ) = 0 THEN 'PASS' ELSE 'FAIL' END

    UNION ALL
    SELECT 'CHK-3', 'breakout_ratio_mismatch',
           CAST((
               WITH board_codes AS (
                   SELECT industry_code,
                          industry_code AS bc1,
                          REPLACE(industry_code, '.DC', '') AS bc2,
                          CASE WHEN industry_code LIKE '%.DC' THEN industry_code
                               ELSE CONCAT(industry_code, '.DC') END AS bc3
                   FROM dwm_industry_vp_agg_di
                   WHERE trade_date = @td AND vp_window = @w
               ),
               brk AS (
                   SELECT bc.industry_code,
                          SUM(CASE WHEN f.is_breakout_strict = 1 THEN COALESCE(f.amount, 0) ELSE 0 END) AS brk_amt,
                          SUM(COALESCE(f.amount, 0)) AS tot_amt
                   FROM board_codes bc
                   JOIN ods_dc_member_di mem
                     ON mem.trade_date = @td
                    AND mem.ts_code IN (bc.bc1, bc.bc2, bc.bc3)
                   JOIN dwm_stock_vp_factor_di f
                     ON f.trade_date = @td AND f.vp_window = @w AND f.ts_code = mem.con_code
                   GROUP BY bc.industry_code
               )
               SELECT COUNT(*) FROM dwm_industry_vp_agg_di a
               JOIN brk b ON b.industry_code = a.industry_code
               WHERE a.trade_date = @td AND a.vp_window = @w
                 AND b.tot_amt > 0
                 AND ABS(a.breakout_ratio - b.brk_amt / b.tot_amt) > @tol
           ) AS CHAR),
           '0',
           CASE WHEN (
               WITH board_codes AS (
                   SELECT industry_code,
                          industry_code AS bc1,
                          REPLACE(industry_code, '.DC', '') AS bc2,
                          CASE WHEN industry_code LIKE '%.DC' THEN industry_code
                               ELSE CONCAT(industry_code, '.DC') END AS bc3
                   FROM dwm_industry_vp_agg_di
                   WHERE trade_date = @td AND vp_window = @w
               ),
               brk AS (
                   SELECT bc.industry_code,
                          SUM(CASE WHEN f.is_breakout_strict = 1 THEN COALESCE(f.amount, 0) ELSE 0 END) AS brk_amt,
                          SUM(COALESCE(f.amount, 0)) AS tot_amt
                   FROM board_codes bc
                   JOIN ods_dc_member_di mem
                     ON mem.trade_date = @td
                    AND mem.ts_code IN (bc.bc1, bc.bc2, bc.bc3)
                   JOIN dwm_stock_vp_factor_di f
                     ON f.trade_date = @td AND f.vp_window = @w AND f.ts_code = mem.con_code
                   GROUP BY bc.industry_code
               )
               SELECT COUNT(*) FROM dwm_industry_vp_agg_di a
               JOIN brk b ON b.industry_code = a.industry_code
               WHERE a.trade_date = @td AND a.vp_window = @w
                 AND b.tot_amt > 0
                 AND ABS(a.breakout_ratio - b.brk_amt / b.tot_amt) > @tol
           ) = 0 THEN 'PASS' ELSE 'FAIL' END

    UNION ALL
    SELECT 'CHK-4', 'trend_return_20d_mismatch',
           CAST((SELECT COUNT(*) FROM (
               SELECT s.industry_code,
                      s.trend_return_20d AS val_stored,
                      ROUND((c1.close / c0.close - 1) * 100, 6) AS calc
               FROM dwm_industry_vp_score_di s
               LEFT JOIN ods_dc_daily_di c1
                 ON c1.trade_date = @td
                AND c1.ts_code IN (
                    s.industry_code,
                    REPLACE(s.industry_code, '.DC', ''),
                    CASE WHEN s.industry_code LIKE '%.DC' THEN s.industry_code
                         ELSE CONCAT(s.industry_code, '.DC') END)
               LEFT JOIN ods_dc_daily_di c0
                 ON c0.trade_date = @lag_td AND c0.ts_code = c1.ts_code
               WHERE s.trade_date = @td AND s.vp_window = @w
           ) bp WHERE ABS(val_stored - calc) > 0.05) AS CHAR),
           '0',
           CASE WHEN (SELECT COUNT(*) FROM (
               SELECT s.trend_return_20d AS val_stored,
                      ROUND((c1.close / c0.close - 1) * 100, 6) AS calc
               FROM dwm_industry_vp_score_di s
               LEFT JOIN ods_dc_daily_di c1
                 ON c1.trade_date = @td
                AND c1.ts_code IN (
                    s.industry_code,
                    REPLACE(s.industry_code, '.DC', ''),
                    CASE WHEN s.industry_code LIKE '%.DC' THEN s.industry_code
                         ELSE CONCAT(s.industry_code, '.DC') END)
               LEFT JOIN ods_dc_daily_di c0
                 ON c0.trade_date = @lag_td AND c0.ts_code = c1.ts_code
               WHERE s.trade_date = @td AND s.vp_window = @w
                 AND c1.close IS NOT NULL AND c0.close IS NOT NULL AND c0.close > 0
           ) x WHERE ABS(val_stored - calc) > 0.05) = 0 THEN 'PASS' ELSE 'FAIL' END

    UNION ALL
    SELECT 'CHK-4', 'trend_null_etl_bug',
           CAST((
               WITH null_boards AS (
                   SELECT s.industry_code
                   FROM dwm_industry_vp_score_di s
                   WHERE s.trade_date = @td AND s.vp_window = @w AND s.trend_return_20d IS NULL
               ),
               px AS (
                   SELECT nb.industry_code,
                          (SELECT MAX(d.close) FROM ods_dc_daily_di d
                           WHERE d.trade_date = @td
                             AND d.ts_code IN (
                                 nb.industry_code,
                                 REPLACE(nb.industry_code, '.DC', ''),
                                 CASE WHEN nb.industry_code LIKE '%.DC' THEN nb.industry_code
                                      ELSE CONCAT(nb.industry_code, '.DC') END)) AS close_t,
                          (SELECT MAX(d.close) FROM ods_dc_daily_di d
                           WHERE d.trade_date = @lag_td
                             AND d.ts_code IN (
                                 nb.industry_code,
                                 REPLACE(nb.industry_code, '.DC', ''),
                                 CASE WHEN nb.industry_code LIKE '%.DC' THEN nb.industry_code
                                      ELSE CONCAT(nb.industry_code, '.DC') END)) AS close_lag
                   FROM null_boards nb
               )
               SELECT COUNT(*) FROM px
               WHERE close_t IS NOT NULL AND close_lag IS NOT NULL AND close_lag > 0
           ) AS CHAR),
           '0',
           CASE WHEN (
               WITH null_boards AS (
                   SELECT s.industry_code
                   FROM dwm_industry_vp_score_di s
                   WHERE s.trade_date = @td AND s.vp_window = @w AND s.trend_return_20d IS NULL
               ),
               px AS (
                   SELECT nb.industry_code,
                          (SELECT MAX(d.close) FROM ods_dc_daily_di d
                           WHERE d.trade_date = @td
                             AND d.ts_code IN (
                                 nb.industry_code,
                                 REPLACE(nb.industry_code, '.DC', ''),
                                 CASE WHEN nb.industry_code LIKE '%.DC' THEN nb.industry_code
                                      ELSE CONCAT(nb.industry_code, '.DC') END)) AS close_t,
                          (SELECT MAX(d.close) FROM ods_dc_daily_di d
                           WHERE d.trade_date = @lag_td
                             AND d.ts_code IN (
                                 nb.industry_code,
                                 REPLACE(nb.industry_code, '.DC', ''),
                                 CASE WHEN nb.industry_code LIKE '%.DC' THEN nb.industry_code
                                      ELSE CONCAT(nb.industry_code, '.DC') END)) AS close_lag
                   FROM null_boards nb
               )
               SELECT COUNT(*) FROM px
               WHERE close_t IS NOT NULL AND close_lag IS NOT NULL AND close_lag > 0
           ) = 0 THEN 'PASS' ELSE 'FAIL' END

    UNION ALL
    SELECT 'CHK-4', 'trend_null_missing_index',
           CAST((
               WITH null_boards AS (
                   SELECT s.industry_code
                   FROM dwm_industry_vp_score_di s
                   WHERE s.trade_date = @td AND s.vp_window = @w AND s.trend_return_20d IS NULL
               ),
               px AS (
                   SELECT nb.industry_code,
                          (SELECT MAX(d.close) FROM ods_dc_daily_di d
                           WHERE d.trade_date = @td
                             AND d.ts_code IN (
                                 nb.industry_code,
                                 REPLACE(nb.industry_code, '.DC', ''),
                                 CASE WHEN nb.industry_code LIKE '%.DC' THEN nb.industry_code
                                      ELSE CONCAT(nb.industry_code, '.DC') END)) AS close_t,
                          (SELECT MAX(d.close) FROM ods_dc_daily_di d
                           WHERE d.trade_date = @lag_td
                             AND d.ts_code IN (
                                 nb.industry_code,
                                 REPLACE(nb.industry_code, '.DC', ''),
                                 CASE WHEN nb.industry_code LIKE '%.DC' THEN nb.industry_code
                                      ELSE CONCAT(nb.industry_code, '.DC') END)) AS close_lag
                   FROM null_boards nb
               )
               SELECT COUNT(*) FROM px
               WHERE close_t IS NULL OR close_lag IS NULL OR close_lag <= 0
           ) AS CHAR),
           'INFO',
           'INFO'

    UNION ALL
    SELECT 'CHK-5', 'leader_strength_mismatch',
           CAST((
               WITH board_codes AS (
                   SELECT industry_code,
                          industry_code AS bc1,
                          REPLACE(industry_code, '.DC', '') AS bc2,
                          CASE WHEN industry_code LIKE '%.DC' THEN industry_code
                               ELSE CONCAT(industry_code, '.DC') END AS bc3
                   FROM dwm_industry_vp_agg_di
                   WHERE trade_date = @td AND vp_window = @w
               ),
               ranked AS (
                   SELECT bc.industry_code,
                          f.pct_chg,
                          COALESCE(f.vol_ratio_20, 0) AS vol_ratio_20,
                          COALESCE(db.circ_mv, 0) AS circ_mv,
                          ROW_NUMBER() OVER (
                              PARTITION BY bc.industry_code
                              ORDER BY COALESCE(db.circ_mv, 0) DESC, f.ts_code
                          ) AS rn
                   FROM board_codes bc
                   JOIN ods_dc_member_di mem
                     ON mem.trade_date = @td
                    AND mem.ts_code IN (bc.bc1, bc.bc2, bc.bc3)
                   JOIN dwm_stock_vp_factor_di f
                     ON f.trade_date = @td AND f.vp_window = @w AND f.ts_code = mem.con_code
                   LEFT JOIN ods_daily_basic_di db
                     ON db.trade_date = @td AND db.ts_code = mem.con_code
               ),
               top3 AS (
                   SELECT industry_code,
                          ROUND((AVG(pct_chg) + AVG(vol_ratio_20)) / 2, 6) AS calc
                   FROM ranked WHERE rn <= 3 GROUP BY industry_code
               )
               SELECT COUNT(*) FROM dwm_industry_vp_agg_di a
               JOIN top3 t ON t.industry_code = a.industry_code
               WHERE a.trade_date = @td AND a.vp_window = @w
                 AND ABS(a.leader_strength - t.calc) > 0.05
           ) AS CHAR),
           '0',
           CASE WHEN (
               WITH board_codes AS (
                   SELECT industry_code,
                          industry_code AS bc1,
                          REPLACE(industry_code, '.DC', '') AS bc2,
                          CASE WHEN industry_code LIKE '%.DC' THEN industry_code
                               ELSE CONCAT(industry_code, '.DC') END AS bc3
                   FROM dwm_industry_vp_agg_di
                   WHERE trade_date = @td AND vp_window = @w
               ),
               ranked AS (
                   SELECT bc.industry_code,
                          f.pct_chg,
                          COALESCE(f.vol_ratio_20, 0) AS vol_ratio_20,
                          COALESCE(db.circ_mv, 0) AS circ_mv,
                          ROW_NUMBER() OVER (
                              PARTITION BY bc.industry_code
                              ORDER BY COALESCE(db.circ_mv, 0) DESC, f.ts_code
                          ) AS rn
                   FROM board_codes bc
                   JOIN ods_dc_member_di mem
                     ON mem.trade_date = @td
                    AND mem.ts_code IN (bc.bc1, bc.bc2, bc.bc3)
                   JOIN dwm_stock_vp_factor_di f
                     ON f.trade_date = @td AND f.vp_window = @w AND f.ts_code = mem.con_code
                   LEFT JOIN ods_daily_basic_di db
                     ON db.trade_date = @td AND db.ts_code = mem.con_code
               ),
               top3 AS (
                   SELECT industry_code,
                          ROUND((AVG(pct_chg) + AVG(vol_ratio_20)) / 2, 6) AS calc
                   FROM ranked WHERE rn <= 3 GROUP BY industry_code
               )
               SELECT COUNT(*) FROM dwm_industry_vp_agg_di a
               JOIN top3 t ON t.industry_code = a.industry_code
               WHERE a.trade_date = @td AND a.vp_window = @w
                 AND ABS(a.leader_strength - t.calc) > 0.05
           ) = 0 THEN 'PASS' ELSE 'FAIL' END

    UNION ALL
    SELECT 'CHK-6', 'continuity_strength_zero_but_streak',
           CAST((SELECT COUNT(*) FROM dwm_industry_vp_agg_di
                 WHERE trade_date = @td AND vp_window = @w
                   AND amount_streak_days > 0
                   AND COALESCE(continuity_strength, 0) <= 0) AS CHAR),
           '0',
           CASE WHEN (SELECT COUNT(*) FROM dwm_industry_vp_agg_di
                      WHERE trade_date = @td AND vp_window = @w
                        AND amount_streak_days > 0
                        AND COALESCE(continuity_strength, 0) <= 0) = 0
                THEN 'PASS' ELSE 'FAIL' END

    UNION ALL
    SELECT 'CHK-7', 'vp_score_formula',
           CAST((SELECT COUNT(*) FROM dwm_industry_vp_score_di
                 WHERE trade_date = @td AND vp_window = @w
                   AND ABS(vp_score - ROUND(
                         score_continuity * 0.25 + score_vol * 0.20 + score_trend * 0.20
                       + score_breadth * 0.15 + score_breakout * 0.15 + score_leader * 0.05, 2)) > 0.02) AS CHAR),
           '0',
           CASE WHEN (SELECT COUNT(*) FROM dwm_industry_vp_score_di
                      WHERE trade_date = @td AND vp_window = @w
                        AND ABS(vp_score - ROUND(
                              score_continuity * 0.25 + score_vol * 0.20 + score_trend * 0.20
                            + score_breadth * 0.15 + score_breakout * 0.15 + score_leader * 0.05, 2)) > 0.02) = 0
                THEN 'PASS' ELSE 'FAIL' END

    UNION ALL
    SELECT 'CHK-8', 'ascending_percentile_violation',
           CAST((SELECT COUNT(*) FROM dwm_industry_vp_score_di a
                 JOIN dwm_industry_vp_score_di b
                   ON b.trade_date = a.trade_date AND b.vp_window = a.vp_window
                  AND a.industry_code < b.industry_code
                 WHERE a.trade_date = @td AND a.vp_window = @w
                   AND a.continuity_strength > b.continuity_strength + 1e-9
                   AND a.score_continuity + 0.01 < b.score_continuity) AS CHAR),
           '0',
           CASE WHEN (SELECT COUNT(*) FROM dwm_industry_vp_score_di a
                      JOIN dwm_industry_vp_score_di b
                        ON b.trade_date = a.trade_date AND b.vp_window = a.vp_window
                       AND a.industry_code < b.industry_code
                      WHERE a.trade_date = @td AND a.vp_window = @w
                        AND a.continuity_strength > b.continuity_strength + 1e-9
                        AND a.score_continuity + 0.01 < b.score_continuity) = 0
                THEN 'PASS' ELSE 'FAIL' END

    UNION ALL
    SELECT 'CHK-8', 'trend_zero_floor_spread',
           CAST((SELECT ROUND(MAX(score_trend) - MIN(score_trend), 4)
                 FROM dwm_industry_vp_score_di
                 WHERE trade_date = @td AND vp_window = @w
                   AND COALESCE(trend_return_20d, 0) <= 0) AS CHAR),
           CONCAT('<= ', @pct_tol),
           CASE WHEN (SELECT MAX(score_trend) - MIN(score_trend)
                      FROM dwm_industry_vp_score_di
                      WHERE trade_date = @td AND vp_window = @w
                        AND COALESCE(trend_return_20d, 0) <= 0) <= @pct_tol
                THEN 'PASS' ELSE 'FAIL' END

    UNION ALL
    SELECT 'CHK-9', 'rank_vp_duplicate',
           CAST((SELECT COUNT(*) FROM (
                 SELECT rank_vp FROM dwm_industry_vp_score_di
                 WHERE trade_date = @td AND vp_window = @w
                 GROUP BY rank_vp HAVING COUNT(*) > 1) t) AS CHAR),
           '0',
           CASE WHEN (SELECT COUNT(*) FROM (
                      SELECT rank_vp FROM dwm_industry_vp_score_di
                      WHERE trade_date = @td AND vp_window = @w
                      GROUP BY rank_vp HAVING COUNT(*) > 1) t) = 0
                THEN 'PASS' ELSE 'FAIL' END

    UNION ALL
    SELECT 'CHK-9', 'rank_order_mismatch',
           CAST((SELECT COUNT(*) FROM (
                 SELECT rank_vp,
                        ROW_NUMBER() OVER (ORDER BY vp_score DESC, industry_code) AS er
                 FROM dwm_industry_vp_score_di
                 WHERE trade_date = @td AND vp_window = @w) x
                 WHERE rank_vp <> er) AS CHAR),
           '0',
           CASE WHEN (SELECT COUNT(*) FROM (
                      SELECT rank_vp,
                             ROW_NUMBER() OVER (ORDER BY vp_score DESC, industry_code) AS er
                      FROM dwm_industry_vp_score_di
                      WHERE trade_date = @td AND vp_window = @w) x
                      WHERE rank_vp <> er) = 0
                THEN 'PASS' ELSE 'FAIL' END

    UNION ALL
    SELECT 'CHK-9', 'rank_score_order_violation',
           CAST((SELECT COUNT(*) FROM dwm_industry_vp_score_di a
                 JOIN dwm_industry_vp_score_di b
                   ON b.trade_date = a.trade_date AND b.vp_window = a.vp_window
                  AND a.rank_vp < b.rank_vp
                 WHERE a.trade_date = @td AND a.vp_window = @w
                   AND a.vp_score < b.vp_score) AS CHAR),
           '0',
           CASE WHEN (SELECT COUNT(*) FROM dwm_industry_vp_score_di a
                      JOIN dwm_industry_vp_score_di b
                        ON b.trade_date = a.trade_date AND b.vp_window = a.vp_window
                       AND a.rank_vp < b.rank_vp
                      WHERE a.trade_date = @td AND a.vp_window = @w
                        AND a.vp_score < b.vp_score) = 0
                THEN 'PASS' ELSE 'FAIL' END

    UNION ALL
    SELECT 'CHK-10', 'percentile_approx_all_dims',
           CAST((
               WITH pool AS (
                   SELECT score_continuity, score_vol, score_trend,
                          score_breadth, score_breakout, score_leader,
                          ROUND(PERCENT_RANK() OVER (ORDER BY continuity_strength) * 100, 2) AS pct_cont,
                          ROUND(PERCENT_RANK() OVER (ORDER BY industry_vol_ratio_20) * 100, 2) AS pct_vol,
                          ROUND(PERCENT_RANK() OVER (ORDER BY GREATEST(COALESCE(trend_return_20d,0),0)) * 100, 2) AS pct_trend,
                          ROUND(PERCENT_RANK() OVER (ORDER BY rising_ratio) * 100, 2) AS pct_breadth,
                          ROUND(PERCENT_RANK() OVER (ORDER BY breakout_ratio) * 100, 2) AS pct_breakout,
                          ROUND(PERCENT_RANK() OVER (ORDER BY leader_strength) * 100, 2) AS pct_leader
                   FROM dwm_industry_vp_score_di
                   WHERE trade_date = @td AND vp_window = @w
               )
               SELECT
                   SUM(CASE WHEN ABS(score_continuity - pct_cont) > @pct_tol THEN 1 ELSE 0 END)
                 + SUM(CASE WHEN ABS(score_vol - pct_vol) > @pct_tol THEN 1 ELSE 0 END)
                 + SUM(CASE WHEN ABS(score_trend - pct_trend) > @pct_tol THEN 1 ELSE 0 END)
                 + SUM(CASE WHEN ABS(score_breadth - pct_breadth) > @pct_tol THEN 1 ELSE 0 END)
                 + SUM(CASE WHEN ABS(score_breakout - pct_breakout) > @pct_tol THEN 1 ELSE 0 END)
                 + SUM(CASE WHEN ABS(score_leader - pct_leader) > @pct_tol THEN 1 ELSE 0 END)
               FROM pool
           ) AS CHAR),
           '0',
           CASE WHEN (
               WITH pool AS (
                   SELECT score_continuity, score_vol, score_trend,
                          score_breadth, score_breakout, score_leader,
                          ROUND(PERCENT_RANK() OVER (ORDER BY continuity_strength) * 100, 2) AS pct_cont,
                          ROUND(PERCENT_RANK() OVER (ORDER BY industry_vol_ratio_20) * 100, 2) AS pct_vol,
                          ROUND(PERCENT_RANK() OVER (ORDER BY GREATEST(COALESCE(trend_return_20d,0),0)) * 100, 2) AS pct_trend,
                          ROUND(PERCENT_RANK() OVER (ORDER BY rising_ratio) * 100, 2) AS pct_breadth,
                          ROUND(PERCENT_RANK() OVER (ORDER BY breakout_ratio) * 100, 2) AS pct_breakout,
                          ROUND(PERCENT_RANK() OVER (ORDER BY leader_strength) * 100, 2) AS pct_leader
                   FROM dwm_industry_vp_score_di
                   WHERE trade_date = @td AND vp_window = @w
               )
               SELECT
                   SUM(CASE WHEN ABS(score_continuity - pct_cont) > @pct_tol THEN 1 ELSE 0 END)
                 + SUM(CASE WHEN ABS(score_vol - pct_vol) > @pct_tol THEN 1 ELSE 0 END)
                 + SUM(CASE WHEN ABS(score_trend - pct_trend) > @pct_tol THEN 1 ELSE 0 END)
                 + SUM(CASE WHEN ABS(score_breadth - pct_breadth) > @pct_tol THEN 1 ELSE 0 END)
                 + SUM(CASE WHEN ABS(score_breakout - pct_breakout) > @pct_tol THEN 1 ELSE 0 END)
                 + SUM(CASE WHEN ABS(score_leader - pct_leader) > @pct_tol THEN 1 ELSE 0 END)
               FROM pool
           ) = 0 THEN 'PASS' ELSE 'FAIL' END
) final_summary
ORDER BY chk, item;
