-- =============================================================================
-- VP 六维指标校验 SQL（20260710 或任意交易日）
-- 用法: mysql -u... -p stock_data < mysql_tables/migrations/check_vp_indicators_20260710.sql
-- 说明:
--   · 与 ETL 逻辑对齐: etl/volume_price/industry_agg.py + industry_score.py
--   · 百分位为 pandas rank(pct=True)*100，MySQL 用 PERCENT_RANK 近似，允许 ±1.5 误差
--   · continuity_strength 含衰减递推，SQL 仅做量级/符号抽检，精确值请用 Python 脚本
-- =============================================================================

USE stock_data;

SET @td = '2026-07-10';
SET @w   = 20;
SET @tol = 0.02;          -- 原始指标相对误差容忍
SET @pct_tol = 1.5;        -- 百分位子分容忍（pandas vs PERCENT_RANK）

-- 20 交易日前的 lag 日（与 ETL list_trading_days(trade_date, 21) 的 days[0] 一致）
SET @lag_td = (
    SELECT trade_date FROM (
        SELECT trade_date,
               ROW_NUMBER() OVER (ORDER BY trade_date DESC) AS rn
        FROM ods_trading_day
        WHERE is_open = 1 AND trade_date <= @td
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

SELECT @td AS check_trade_date, @lag_td AS lag_trade_date_20d, @w AS vp_window;

-- =============================================================================
-- CHK-0 基础产出
-- =============================================================================
SELECT 'CHK-0' AS chk, 'score_rows' AS item,
       COUNT(*) AS val,
       CASE WHEN COUNT(*) > 100 THEN 'OK' ELSE 'WARN' END AS status
FROM dwm_industry_vp_score_di
WHERE trade_date = @td AND vp_window = @w;

SELECT 'CHK-0' AS chk, 'factor_rows' AS item, COUNT(*) AS val
FROM dwm_stock_vp_factor_di WHERE trade_date = @td AND vp_window = @w;

SELECT 'CHK-0' AS chk, 'strict_breakout_stocks' AS item,
       SUM(is_breakout_strict = 1) AS val
FROM dwm_stock_vp_factor_di WHERE trade_date = @td AND vp_window = @w;

-- =============================================================================
-- CHK-1 行业量比 industry_vol_ratio_20 = 当日 total_amount / 近20日 total_amount 均值
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
       COUNT(*) AS mismatch_cnt
FROM dwm_industry_vp_agg_di a
JOIN hist h
  ON h.industry_code = a.industry_code AND h.trade_date = a.trade_date
WHERE a.trade_date = @td AND a.vp_window = @w
  AND h.ma20_amt > 0
  AND ABS(a.industry_vol_ratio_20 - a.total_amount / h.ma20_amt) > @tol;

-- 明细（前 20 条异常）
SELECT 'CHK-1-detail' AS chk,
       a.industry_code, a.industry_name,
       a.industry_vol_ratio_20 AS stored,
       ROUND(a.total_amount / h.ma20_amt, 6) AS calc,
       ROUND(a.industry_vol_ratio_20 - a.total_amount / h.ma20_amt, 6) AS diff
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
SELECT 'CHK-2' AS chk, 'rising_ratio_mismatch' AS item, COUNT(*) AS mismatch_cnt
FROM dwm_industry_vp_agg_di a
JOIN member_mv m ON m.industry_code = a.industry_code
WHERE a.trade_date = @td AND a.vp_window = @w
  AND m.total_mv_w > 0
  AND ABS(a.rising_ratio - m.rise_mv / m.total_mv_w) > @tol;

SELECT 'CHK-2-detail' AS chk,
       a.industry_code, a.industry_name,
       a.rising_ratio AS stored,
       ROUND(m.rise_mv / m.total_mv_w, 6) AS calc,
       m.no_mv_cnt AS members_without_circ_mv
FROM dwm_industry_vp_agg_di a
JOIN member_mv m ON m.industry_code = a.industry_code
WHERE a.trade_date = @td AND a.vp_window = @w
  AND m.total_mv_w > 0
  AND ABS(a.rising_ratio - m.rise_mv / m.total_mv_w) > @tol
ORDER BY ABS(a.rising_ratio - m.rise_mv / m.total_mv_w) DESC
LIMIT 20;

-- =============================================================================
-- CHK-3 严格突破占比 breakout_ratio = Σ(严格突破成交额) / 板块总成交额
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
SELECT 'CHK-3' AS chk, 'breakout_ratio_mismatch' AS item, COUNT(*) AS mismatch_cnt
FROM dwm_industry_vp_agg_di a
JOIN brk b ON b.industry_code = a.industry_code
WHERE a.trade_date = @td AND a.vp_window = @w
  AND b.tot_amt > 0
  AND ABS(a.breakout_ratio - b.brk_amt / b.tot_amt) > @tol;

SELECT 'CHK-3-detail' AS chk,
       a.industry_code, a.industry_name,
       a.breakout_ratio AS stored,
       ROUND(b.brk_amt / b.tot_amt, 6) AS calc
FROM dwm_industry_vp_agg_di a
JOIN brk b ON b.industry_code = a.industry_code
WHERE a.trade_date = @td AND a.vp_window = @w
  AND b.tot_amt > 0
  AND ABS(a.breakout_ratio - b.brk_amt / b.tot_amt) > @tol
ORDER BY ABS(a.breakout_ratio - b.brk_amt / b.tot_amt) DESC
LIMIT 20;

-- =============================================================================
-- CHK-4 趋势强度 trend_return_20d = (close_t / close_lag - 1) * 100  （ods_dc_daily_di）
-- =============================================================================
WITH board_px AS (
    SELECT s.industry_code,
           s.trend_return_20d AS stored,
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
SELECT 'CHK-4' AS chk, 'trend_return_20d_mismatch' AS item, COUNT(*) AS mismatch_cnt
FROM board_px
WHERE close_t IS NOT NULL AND close_lag IS NOT NULL AND close_lag > 0
  AND ABS(stored - calc) > 0.05;

SELECT 'CHK-4-detail' AS chk, industry_code, stored, calc,
       ROUND(stored - calc, 6) AS diff, close_t, close_lag
FROM board_px
WHERE close_t IS NOT NULL AND close_lag IS NOT NULL AND close_lag > 0
  AND ABS(stored - calc) > 0.05
ORDER BY ABS(stored - calc) DESC
LIMIT 20;

SELECT 'CHK-4' AS chk, 'trend_return_null' AS item, COUNT(*) AS null_cnt
FROM dwm_industry_vp_score_di
WHERE trade_date = @td AND vp_window = @w AND trend_return_20d IS NULL;

-- =============================================================================
-- CHK-5 龙头强度 leader_strength = (Top3 circ_mv 涨幅均值 + Top3 量比均值) / 2
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
SELECT 'CHK-5' AS chk, 'leader_strength_mismatch' AS item, COUNT(*) AS mismatch_cnt
FROM dwm_industry_vp_agg_di a
JOIN top3 t ON t.industry_code = a.industry_code
WHERE a.trade_date = @td AND a.vp_window = @w
  AND ABS(a.leader_strength - t.calc) > 0.05;

SELECT 'CHK-5-detail' AS chk,
       a.industry_code, a.industry_name,
       a.leader_strength AS stored, t.calc,
       ROUND(a.leader_strength - t.calc, 6) AS diff
FROM dwm_industry_vp_agg_di a
JOIN top3 t ON t.industry_code = a.industry_code
WHERE a.trade_date = @td AND a.vp_window = @w
  AND ABS(a.leader_strength - t.calc) > 0.05
ORDER BY ABS(a.leader_strength - t.calc) DESC
LIMIT 20;

-- =============================================================================
-- CHK-6 连续放量天数 amount_streak_days（简易：当日成交额 > 近20日均）
-- =============================================================================
SELECT 'CHK-6' AS chk, 'amount_streak_days_sample' AS item,
       a.industry_code, a.industry_name,
       a.amount_streak_days,
       a.continuity_strength,
       CASE WHEN a.total_amount > h.ma20_amt THEN 'above_ma' ELSE 'below_ma' END AS today_vs_ma20
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

-- continuity_strength 精确校验需 Python；此处检查：有连续放量天数则强度应 > 0
SELECT 'CHK-6' AS chk, 'continuity_strength_zero_but_streak' AS item, COUNT(*) AS bad_cnt
FROM dwm_industry_vp_agg_di
WHERE trade_date = @td AND vp_window = @w
  AND amount_streak_days > 0
  AND COALESCE(continuity_strength, 0) <= 0;

-- =============================================================================
-- CHK-7 VP 综合分 = 六维子分 × 权重（0.25/0.20/0.20/0.15/0.15/0.05）
-- =============================================================================
SELECT 'CHK-7' AS chk, 'vp_score_mismatch' AS item, COUNT(*) AS mismatch_cnt
FROM dwm_industry_vp_score_di
WHERE trade_date = @td AND vp_window = @w
  AND ABS(
        vp_score - ROUND(
            score_continuity * 0.25 + score_vol * 0.20 + score_trend * 0.20
          + score_breadth * 0.15 + score_breakout * 0.15 + score_leader * 0.05,
        2)
      ) > 0.02;

SELECT 'CHK-7-detail' AS chk,
       industry_code, industry_name, vp_score AS stored,
       ROUND(
         score_continuity * 0.25 + score_vol * 0.20 + score_trend * 0.20
       + score_breadth * 0.15 + score_breakout * 0.15 + score_leader * 0.05,
       2) AS calc,
       score_continuity, score_vol, score_trend, score_breadth, score_breakout, score_leader
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
-- =============================================================================
SELECT 'CHK-8' AS chk, 'ascending_percentile_violation' AS item, COUNT(*) AS violation_pairs
FROM dwm_industry_vp_score_di a
JOIN dwm_industry_vp_score_di b
  ON b.trade_date = a.trade_date AND b.vp_window = a.vp_window
 AND a.industry_code < b.industry_code
WHERE a.trade_date = @td AND a.vp_window = @w
  AND a.continuity_strength > b.continuity_strength + 1e-9
  AND a.score_continuity + 0.01 < b.score_continuity;

SELECT 'CHK-8' AS chk, 'trend_zero_floor_spread' AS item,
       ROUND(MAX(score_trend) - MIN(score_trend), 4) AS spread,
       CASE WHEN MAX(score_trend) - MIN(score_trend) <= @pct_tol THEN 'OK' ELSE 'WARN' END AS status
FROM dwm_industry_vp_score_di
WHERE trade_date = @td AND vp_window = @w
  AND COALESCE(trend_return_20d, 0) <= 0;

-- =============================================================================
-- CHK-9 rank_vp：合并池唯一且与 vp_score 降序一致
-- =============================================================================
SELECT 'CHK-9' AS chk, 'rank_vp_duplicate' AS item, COUNT(*) AS dup_cnt
FROM (
    SELECT rank_vp, COUNT(*) AS n
    FROM dwm_industry_vp_score_di
    WHERE trade_date = @td AND vp_window = @w
    GROUP BY rank_vp HAVING n > 1
) t;

SELECT 'CHK-9' AS chk, 'rank_order_mismatch' AS item, COUNT(*) AS mismatch_cnt
FROM (
    SELECT industry_code, vp_score, rank_vp,
           ROW_NUMBER() OVER (ORDER BY vp_score DESC, industry_code) AS expected_rank
    FROM dwm_industry_vp_score_di
    WHERE trade_date = @td AND vp_window = @w
) x
WHERE rank_vp <> expected_rank;

-- =============================================================================
-- CHK-10 子分与 PERCENT_RANK 近似对比（六维，允许 @pct_tol）
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
       SUM(CASE WHEN ABS(score_leader - pct_leader) > @pct_tol THEN 1 ELSE 0 END) AS leader_diff
FROM pool;

-- =============================================================================
-- 汇总：Top10 全指标一览
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
       ROUND(score_leader, 2) AS s_leader
FROM dwm_industry_vp_score_di
WHERE trade_date = @td AND vp_window = @w
ORDER BY rank_vp
LIMIT 10;

-- =============================================================================
-- 一键异常汇总（mismatch_cnt > 0 则需排查）
-- =============================================================================
SELECT chk, item, mismatch_cnt, CASE WHEN mismatch_cnt = 0 THEN 'PASS' ELSE 'FAIL' END AS result
FROM (
    SELECT 'CHK-1' AS chk, 'industry_vol_ratio' AS item,
           (SELECT COUNT(*) FROM dwm_industry_vp_agg_di a
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
           ) AS mismatch_cnt
    UNION ALL
    SELECT 'CHK-7', 'vp_score_formula',
           (SELECT COUNT(*) FROM dwm_industry_vp_score_di
            WHERE trade_date = @td AND vp_window = @w
              AND ABS(vp_score - ROUND(
                    score_continuity * 0.25 + score_vol * 0.20 + score_trend * 0.20
                  + score_breadth * 0.15 + score_breakout * 0.15 + score_leader * 0.05, 2)) > 0.02)
    UNION ALL
    SELECT 'CHK-9', 'rank_vp_order',
           (SELECT COUNT(*) FROM (
                SELECT rank_vp,
                       ROW_NUMBER() OVER (ORDER BY vp_score DESC, industry_code) AS er
                FROM dwm_industry_vp_score_di
                WHERE trade_date = @td AND vp_window = @w
            ) x WHERE rank_vp <> er)
) summary
ORDER BY chk;
