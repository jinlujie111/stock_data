-- =============================================================================
-- 同花顺 DWM 数据正确性核查
-- 表: dwm_ths_industry_fund_flow_di / dwm_ths_industry_trend_strength_di
-- 用法: SET @v_date = '2026-06-09'; 然后逐段执行
-- =============================================================================
SET @v_date = '2026-06-09';
SET @board  = '881162.TI';   -- 样例板块：通信服务

-- =============================================================================
-- A. 基础完整性（两表通用）
-- =============================================================================

-- A1) 当日是否有数据、按类型条数
SELECT 'fund_flow' AS tbl, content_type, COUNT(*) AS cnt
FROM dwm_ths_industry_fund_flow_di WHERE trade_date = @v_date
GROUP BY content_type
UNION ALL
SELECT 'trend', content_type, COUNT(*)
FROM dwm_ths_industry_trend_strength_di WHERE trade_date = @v_date
GROUP BY content_type
ORDER BY tbl, content_type;

-- A2) 重复键（应为 0）
SELECT 'fund_flow_dup' AS chk, COUNT(*) - COUNT(DISTINCT industry_code) AS dup_cnt
FROM dwm_ths_industry_fund_flow_di WHERE trade_date = @v_date
UNION ALL
SELECT 'trend_dup', COUNT(*) - COUNT(DISTINCT industry_code)
FROM dwm_ths_industry_trend_strength_di WHERE trade_date = @v_date;

-- A3) 两表板块覆盖是否一致（I/N/R 应对齐）
SELECT content_type,
       SUM(CASE WHEN src = 'fund' THEN cnt ELSE 0 END) AS fund_cnt,
       SUM(CASE WHEN src = 'trend' THEN cnt ELSE 0 END) AS trend_cnt
FROM (
    SELECT content_type, COUNT(*) cnt, 'fund' AS src
    FROM dwm_ths_industry_fund_flow_di WHERE trade_date = @v_date GROUP BY content_type
    UNION ALL
    SELECT content_type, COUNT(*), 'trend'
    FROM dwm_ths_industry_trend_strength_di WHERE trade_date = @v_date GROUP BY content_type
) x GROUP BY content_type ORDER BY content_type;

-- =============================================================================
-- B. 资金强度 dwm_ths_industry_fund_flow_di
-- =============================================================================

-- B1) 衍生字段自洽性（diff 应全为 0）
SELECT COUNT(*) AS bad_rows
FROM dwm_ths_industry_fund_flow_di
WHERE trade_date = @v_date
  AND (
       ABS(IFNULL(net_amount_wan, 0) - IFNULL(net_amount, 0) / 10000) > 0.01
    OR (board_amount IS NOT NULL AND board_amount <> 0
        AND ABS(IFNULL(fund_inflow_strength, 0) - net_amount / board_amount) > 1e-6)
    OR (board_amount IS NOT NULL AND board_amount <> 0
        AND ABS(IFNULL(net_amount_rate, 0) - net_amount / board_amount * 100) > 0.01)
    OR (net_amount IS NOT NULL AND net_amount <> 0
        AND ABS(IFNULL(elg_net_ratio, 0) - buy_elg_amount / net_amount) > 0.001)
    OR (net_amount_5d_avg IS NOT NULL
        AND ABS(IFNULL(fund_accel, 0) - (net_amount - net_amount_5d_avg)) > 0.01)
    OR (IFNULL(net_amount, 0) <= 0 AND net_inflow_days <> 0)
    OR (IFNULL(net_amount, 0) > 0 AND net_inflow_days <= 0)
  );

-- B2) pct_change 与 ods_ths_daily_di 一致（diff 应全为 0）
SELECT COUNT(*) AS pct_mismatch
FROM dwm_ths_industry_fund_flow_di f
JOIN ods_ths_daily_di d
  ON f.trade_date = d.trade_date AND f.industry_code = d.ts_code
WHERE f.trade_date = @v_date
  AND ABS(IFNULL(f.pct_change, 0) - IFNULL(d.pct_change, 0)) > 0.0001;

-- B3) 手工 ODS 汇总 vs DWM（样例板块，应完全一致）
WITH member_norm AS (
    SELECT CASE
        WHEN INSTR(m.con_code, '.') > 0 THEN m.con_code
        WHEN LEFT(m.con_code, 1) IN ('6', '5', '9') THEN CONCAT(m.con_code, '.SH')
        WHEN LEFT(m.con_code, 1) IN ('8', '4') THEN CONCAT(m.con_code, '.BJ')
        ELSE CONCAT(m.con_code, '.SZ')
    END AS stock_code
    FROM ods_ths_member_di m WHERE m.ts_code = @board
),
calc AS (
    SELECT
        SUM((st.buy_lg_amount + st.buy_elg_amount - st.sell_lg_amount - st.sell_elg_amount) * 10000) AS net_amount,
        SUM((st.buy_elg_amount - st.sell_elg_amount) * 10000) AS buy_elg_amount,
        SUM(sto.amount * 1000) AS board_amount
    FROM member_norm mn
    LEFT JOIN ods_stock_fund_flow_di st
      ON mn.stock_code = st.ts_code AND st.trade_date = @v_date
    LEFT JOIN ods_stock_detail_di sto
      ON mn.stock_code = sto.ts_code AND sto.trade_date = @v_date
)
SELECT 'ods_calc' AS src, c.net_amount, c.buy_elg_amount, c.board_amount
FROM calc c
UNION ALL
SELECT 'dwm', f.net_amount, f.buy_elg_amount, f.board_amount
FROM dwm_ths_industry_fund_flow_di f
WHERE f.trade_date = @v_date AND f.industry_code = @board;

-- B4) 成分股 moneyflow 匹配率（应 >= 95%，低于则汇总可能偏）
WITH member_norm AS (
    SELECT m.ts_code,
           CASE
               WHEN INSTR(m.con_code, '.') > 0 THEN m.con_code
               WHEN LEFT(m.con_code, 1) IN ('6', '5', '9') THEN CONCAT(m.con_code, '.SH')
               WHEN LEFT(m.con_code, 1) IN ('8', '4') THEN CONCAT(m.con_code, '.BJ')
               ELSE CONCAT(m.con_code, '.SZ')
           END AS stock_code
    FROM ods_ths_member_di m
    JOIN ods_ths_index_di i ON m.ts_code = i.ts_code AND i.index_type IN ('I', 'N', 'R')
)
SELECT i.index_type,
       COUNT(DISTINCT mn.stock_code) AS members,
       COUNT(DISTINCT st.ts_code) AS mf_hit,
       ROUND(COUNT(DISTINCT st.ts_code) / COUNT(DISTINCT mn.stock_code) * 100, 2) AS mf_pct
FROM member_norm mn
JOIN ods_ths_index_di i ON mn.ts_code = i.ts_code
LEFT JOIN ods_stock_fund_flow_di st
  ON mn.stock_code = st.ts_code AND st.trade_date = @v_date
GROUP BY i.index_type;

-- B5) 与东财同名行业粗对比（行业类；符号/量级参考，非严格相等）
SELECT d.industry_name,
       ROUND(d.net_amount_wan, 2) AS dc_wan,
       ROUND(t.net_amount_wan, 2) AS ths_wan,
       ROUND(t.net_amount_wan / NULLIF(d.net_amount_wan, 0), 2) AS ratio,
       CASE WHEN d.net_amount * t.net_amount < 0 THEN 'SIGN_FLIP' ELSE 'OK' END AS sign_chk
FROM dwm_dc_industry_fund_flow_di d
JOIN dwm_ths_industry_fund_flow_di t
  ON d.trade_date = t.trade_date
 AND d.content_type = t.content_type
 AND d.industry_name = t.industry_name
 AND d.content_type = '行业'
WHERE d.trade_date = @v_date
ORDER BY ABS(d.net_amount_wan - t.net_amount_wan) DESC
LIMIT 20;

-- =============================================================================
-- C. 趋势强度 dwm_ths_industry_trend_strength_di
-- =============================================================================

-- C1) 衍生字段自洽性（bad_rows 应为 0）
SELECT COUNT(*) AS bad_rows
FROM dwm_ths_industry_trend_strength_di
WHERE trade_date = @v_date
  AND (
       (ma5 IS NOT NULL AND ma10 IS NOT NULL AND ma20 IS NOT NULL
        AND ma_bullish <> IF(ma5 > ma10 AND ma10 > ma20, 1, 0))
    OR (high_60d IS NOT NULL AND high_60d <> 0
        AND ABS(IFNULL(drawdown_pct, 0) - (close - high_60d) / high_60d * 100) > 0.01)
    OR (is_new_high_60d = 1 AND drawdown_pct IS NOT NULL AND drawdown_pct < -0.1)
    OR (drawdown_pct IS NULL OR drawdown_pct > -3) AND recovery_days <> 0
  );

-- C2) pct_change / close 与 ods_ths_daily_di 一致
SELECT COUNT(*) AS pct_mismatch
FROM dwm_ths_industry_trend_strength_di t
JOIN ods_ths_daily_di d
  ON t.trade_date = d.trade_date AND t.industry_code = d.ts_code
WHERE t.trade_date = @v_date
  AND (ABS(IFNULL(t.pct_change, 0) - IFNULL(d.pct_change, 0)) > 0.0001
    OR ABS(IFNULL(t.close, 0) - IFNULL(d.close, 0)) > 0.0001);

-- C3) 手工重算 rs_5d（样例板块，与 DWM 差应 < 0.01）
WITH bench AS (
    SELECT trade_date, pct_chg AS bench_pct
    FROM ods_index_daily_di
    WHERE ts_code = '000300.SH'
      AND trade_date <= @v_date
      AND trade_date >= DATE_SUB(@v_date, INTERVAL 120 DAY)
),
daily AS (
    SELECT d.trade_date, d.pct_change, b.bench_pct
    FROM ods_ths_daily_di d
    JOIN bench b ON d.trade_date = b.trade_date
    WHERE d.ts_code = @board
      AND d.trade_date <= @v_date
),
calc AS (
    SELECT trade_date,
           SUM(pct_change) OVER (ORDER BY trade_date ROWS BETWEEN 4 PRECEDING AND CURRENT ROW)
         - SUM(bench_pct) OVER (ORDER BY trade_date ROWS BETWEEN 4 PRECEDING AND CURRENT ROW) AS rs_5d_calc
    FROM daily
)
SELECT 'ods_calc' AS src, ROUND(rs_5d_calc, 6) AS rs_5d
FROM calc WHERE trade_date = @v_date
UNION ALL
SELECT 'dwm', rs_5d
FROM dwm_ths_industry_trend_strength_di
WHERE trade_date = @v_date AND industry_code = @board;

-- C4) rs_rank 同类型内是否唯一且连续
SELECT content_type,
       COUNT(*) AS cnt,
       COUNT(DISTINCT rs_rank) AS rank_cnt,
       MIN(rs_rank) AS min_rank,
       MAX(rs_rank) AS max_rank
FROM dwm_ths_industry_trend_strength_di
WHERE trade_date = @v_date
GROUP BY content_type;
-- 期望: cnt = rank_cnt, min_rank = 1

-- C5) 与东财同名行业 rs_5d 对比（趋势类通常比资金类更接近）
SELECT d.industry_name,
       ROUND(d.rs_5d, 4) AS dc_rs5,
       ROUND(t.rs_5d, 4) AS ths_rs5,
       ROUND(t.rs_5d - d.rs_5d, 4) AS diff,
       d.ma_bullish AS dc_ma_bull,
       t.ma_bullish AS ths_ma_bull
FROM dwm_dc_industry_trend_strength_di d
JOIN dwm_ths_industry_trend_strength_di t
  ON d.trade_date = t.trade_date
 AND d.content_type = t.content_type
 AND d.industry_name = t.industry_name
 AND d.content_type = '行业'
WHERE d.trade_date = @v_date
ORDER BY ABS(t.rs_5d - d.rs_5d) DESC
LIMIT 20;

-- =============================================================================
-- D. 跨表一致性（同一板块同日）
-- =============================================================================

-- D1) 资金表 vs 趋势表：pct_change 应相同
SELECT COUNT(*) AS pct_cross_mismatch
FROM dwm_ths_industry_fund_flow_di f
JOIN dwm_ths_industry_trend_strength_di t
  ON f.trade_date = t.trade_date AND f.industry_code = t.industry_code
WHERE f.trade_date = @v_date
  AND ABS(IFNULL(f.pct_change, 0) - IFNULL(t.pct_change, 0)) > 0.0001;

-- D2) 仅在一表出现的板块（应为 0 或极少）
SELECT 'fund_only' AS side, industry_code, industry_name
FROM dwm_ths_industry_fund_flow_di f
LEFT JOIN dwm_ths_industry_trend_strength_di t
  ON f.trade_date = t.trade_date AND f.industry_code = t.industry_code
WHERE f.trade_date = @v_date AND t.industry_code IS NULL
LIMIT 10;

-- =============================================================================
-- E. 多日稳定性（排查单日 ODS 异常，如 2026-06-02）
-- =============================================================================

SELECT d.trade_date,
       SUM(CASE WHEN d.net_amount * t.net_amount < 0 THEN 1 ELSE 0 END) AS fund_sign_flip,
       COUNT(*) AS matched_industry
FROM dwm_dc_industry_fund_flow_di d
JOIN dwm_ths_industry_fund_flow_di t
  ON d.trade_date = t.trade_date
 AND d.content_type = t.content_type
 AND d.industry_name = t.industry_name
 AND d.content_type = '行业'
WHERE d.trade_date BETWEEN DATE_SUB(@v_date, INTERVAL 10 DAY) AND @v_date
GROUP BY d.trade_date
ORDER BY d.trade_date;
