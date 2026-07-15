-- =============================================================================
-- 量化选股 / 回测：ODS → DWM → data_industry 数据完整性校验
--
-- 用法（先改区间，再执行）:
--   mysql -u root -p < mysql_tables/migrations/check_quant_data_completeness.sql
--
-- 依赖说明（与 etl/quant 对齐）:
--   硬依赖(FAIL 须补齐后再跑信号/回测):
--     ods_trading_day
--     ods_stock_detail_di          行情 close/amount
--     ods_adj_factor_di            后复权
--     ods_daily_basic_di           换手/估值/市值
--     ods_stock_fund_flow_di       主力净流入(短线 netflow)
--     ods_stk_limit_di             涨停价(不可买)
--     ods_stock_basic_di           ST / 上市日过滤
--   长线额外硬依赖:
--     ods_fina_indicator           ROE / 净利同比(as-of)
--   回测基准(缺则基准曲线为空，回测仍可跑 → WARN):
--     ods_index_daily_di(000300.SH)
--   短线软依赖(缺 → WARN，vp_score/breakout 空、短线权重偏软):
--     dwm_stock_vp_factor_di
--   产出层(信号跑完后才看):
--     data_industry.quant_strategy
--     data_industry.quant_signal_di
--
-- 判定: status = PASS / WARN / FAIL
--   · 先看 FINAL-SUMMARY 中所有 FAIL
--   · WARN 可先跑信号，但短线/基准质量下降
-- =============================================================================

-- 校验区间（与回填命令对齐；可改）
SET @start = '2025-01-01';
SET @end   = '2026-07-14';

-- 阈值（可按环境微调）
SET @min_daily_stocks   = 4000;   -- 全日 A 股日线大致下限
SET @min_daily_adj      = 4000;
SET @min_daily_basic    = 4000;
SET @min_daily_flow     = 3500;   -- 资金流偶有覆盖略低
SET @min_daily_limit    = 4000;
SET @min_vp_factor      = 3000;   -- 个股 VP 因子
SET @min_signal_per_day = 10;     -- 单策略单日 BUY+HOLD 大致下限
SET @min_strategy_cnt   = 2;      -- 至少短线+长线两套内置模板
SET @lookback_td        = 130;    -- mom120/ma60 预热交易日数
SET @coverage_tol       = 0.95;   -- 区间交易日覆盖率下限（≥95% 才 PASS）

SELECT
    @start AS range_start,
    @end   AS range_end,
    @lookback_td AS lookback_trading_days_needed,
    'quant ODS→DWM→signal completeness' AS scope;

-- =============================================================================
-- CHK-0 交易日历
-- =============================================================================
SELECT 'CHK-0' AS chk, 'trading_days_in_range' AS item,
       COUNT(*) AS actual,
       CONCAT('> 0 AND cover ', @start, '~', @end) AS expected,
       CASE WHEN COUNT(*) > 0 THEN 'PASS' ELSE 'FAIL' END AS status
FROM stock_data.ods_trading_day
WHERE trade_date BETWEEN @start AND @end;

SET @cal_days = (
    SELECT COUNT(*) FROM stock_data.ods_trading_day
    WHERE trade_date BETWEEN @start AND @end
);

-- 预热窗口起点（信号区间前 N 个交易日）
SET @warmup_start = (
    SELECT MIN(trade_date) FROM (
        SELECT trade_date
        FROM stock_data.ods_trading_day
        WHERE trade_date < @start
        ORDER BY trade_date DESC
        LIMIT @lookback_td
    ) t
);

SELECT 'CHK-0' AS chk, 'warmup_start' AS item,
       CAST(@warmup_start AS CHAR) AS actual,
       CONCAT('NOT NULL (lookback=', @lookback_td, ')') AS expected,
       CASE WHEN @warmup_start IS NOT NULL THEN 'PASS' ELSE 'FAIL' END AS status;

-- =============================================================================
-- CHK-1 ODS 硬依赖：区间按日汇总 + 缺天 + 行数不足天
-- =============================================================================

-- 1.1 日线行情
SELECT 'CHK-1' AS chk, 'ods_stock_detail_coverage' AS item,
       COUNT(DISTINCT d.trade_date) AS days_with_data,
       @cal_days AS cal_days,
       ROUND(COUNT(DISTINCT d.trade_date) / NULLIF(@cal_days, 0), 4) AS coverage,
       CONCAT('>= ', @coverage_tol) AS expected,
       CASE WHEN COUNT(DISTINCT d.trade_date) / NULLIF(@cal_days, 0) >= @coverage_tol
            THEN 'PASS' ELSE 'FAIL' END AS status
FROM stock_data.ods_stock_detail_di d
WHERE d.trade_date BETWEEN @start AND @end;

SELECT 'CHK-1' AS chk, 'ods_stock_detail_missing_days' AS item,
       COUNT(*) AS actual, 0 AS expected,
       CASE WHEN COUNT(*) = 0 THEN 'PASS' ELSE 'FAIL' END AS status
FROM stock_data.ods_trading_day c
LEFT JOIN (
    SELECT trade_date, COUNT(*) AS cnt
    FROM stock_data.ods_stock_detail_di
    WHERE trade_date BETWEEN @start AND @end
    GROUP BY trade_date
) d ON d.trade_date = c.trade_date
WHERE c.trade_date BETWEEN @start AND @end
  AND (d.trade_date IS NULL OR d.cnt < @min_daily_stocks);

SELECT 'CHK-1-detail' AS chk, 'ods_stock_detail_low_or_missing' AS item,
       c.trade_date, COALESCE(d.cnt, 0) AS row_cnt,
       @min_daily_stocks AS min_expected
FROM stock_data.ods_trading_day c
LEFT JOIN (
    SELECT trade_date, COUNT(*) AS cnt
    FROM stock_data.ods_stock_detail_di
    WHERE trade_date BETWEEN @start AND @end
    GROUP BY trade_date
) d ON d.trade_date = c.trade_date
WHERE c.trade_date BETWEEN @start AND @end
  AND (d.trade_date IS NULL OR d.cnt < @min_daily_stocks)
ORDER BY c.trade_date
LIMIT 50;

-- 1.2 复权因子
SELECT 'CHK-1' AS chk, 'ods_adj_factor_coverage' AS item,
       COUNT(DISTINCT trade_date) AS days_with_data,
       @cal_days AS cal_days,
       ROUND(COUNT(DISTINCT trade_date) / NULLIF(@cal_days, 0), 4) AS coverage,
       CONCAT('>= ', @coverage_tol) AS expected,
       CASE WHEN COUNT(DISTINCT trade_date) / NULLIF(@cal_days, 0) >= @coverage_tol
            THEN 'PASS' ELSE 'FAIL' END AS status
FROM stock_data.ods_adj_factor_di
WHERE trade_date BETWEEN @start AND @end;

SELECT 'CHK-1' AS chk, 'ods_adj_factor_missing_days' AS item,
       COUNT(*) AS actual, 0 AS expected,
       CASE WHEN COUNT(*) = 0 THEN 'PASS' ELSE 'FAIL' END AS status
FROM stock_data.ods_trading_day c
LEFT JOIN (
    SELECT trade_date, COUNT(*) AS cnt
    FROM stock_data.ods_adj_factor_di
    WHERE trade_date BETWEEN @start AND @end
    GROUP BY trade_date
) d ON d.trade_date = c.trade_date
WHERE c.trade_date BETWEEN @start AND @end
  AND (d.trade_date IS NULL OR d.cnt < @min_daily_adj);

-- 1.3 每日指标
SELECT 'CHK-1' AS chk, 'ods_daily_basic_coverage' AS item,
       COUNT(DISTINCT trade_date) AS days_with_data,
       @cal_days AS cal_days,
       ROUND(COUNT(DISTINCT trade_date) / NULLIF(@cal_days, 0), 4) AS coverage,
       CONCAT('>= ', @coverage_tol) AS expected,
       CASE WHEN COUNT(DISTINCT trade_date) / NULLIF(@cal_days, 0) >= @coverage_tol
            THEN 'PASS' ELSE 'FAIL' END AS status
FROM stock_data.ods_daily_basic_di
WHERE trade_date BETWEEN @start AND @end;

SELECT 'CHK-1' AS chk, 'ods_daily_basic_missing_days' AS item,
       COUNT(*) AS actual, 0 AS expected,
       CASE WHEN COUNT(*) = 0 THEN 'PASS' ELSE 'FAIL' END AS status
FROM stock_data.ods_trading_day c
LEFT JOIN (
    SELECT trade_date, COUNT(*) AS cnt
    FROM stock_data.ods_daily_basic_di
    WHERE trade_date BETWEEN @start AND @end
    GROUP BY trade_date
) d ON d.trade_date = c.trade_date
WHERE c.trade_date BETWEEN @start AND @end
  AND (d.trade_date IS NULL OR d.cnt < @min_daily_basic);

-- 1.4 个股资金流
SELECT 'CHK-1' AS chk, 'ods_stock_fund_flow_coverage' AS item,
       COUNT(DISTINCT trade_date) AS days_with_data,
       @cal_days AS cal_days,
       ROUND(COUNT(DISTINCT trade_date) / NULLIF(@cal_days, 0), 4) AS coverage,
       CONCAT('>= ', @coverage_tol) AS expected,
       CASE WHEN COUNT(DISTINCT trade_date) / NULLIF(@cal_days, 0) >= @coverage_tol
            THEN 'PASS' ELSE 'FAIL' END AS status
FROM stock_data.ods_stock_fund_flow_di
WHERE trade_date BETWEEN @start AND @end;

SELECT 'CHK-1' AS chk, 'ods_stock_fund_flow_missing_days' AS item,
       COUNT(*) AS actual, 0 AS expected,
       CASE WHEN COUNT(*) = 0 THEN 'PASS' ELSE 'FAIL' END AS status
FROM stock_data.ods_trading_day c
LEFT JOIN (
    SELECT trade_date, COUNT(*) AS cnt
    FROM stock_data.ods_stock_fund_flow_di
    WHERE trade_date BETWEEN @start AND @end
    GROUP BY trade_date
) d ON d.trade_date = c.trade_date
WHERE c.trade_date BETWEEN @start AND @end
  AND (d.trade_date IS NULL OR d.cnt < @min_daily_flow);

-- 1.5 涨跌停价
SELECT 'CHK-1' AS chk, 'ods_stk_limit_coverage' AS item,
       COUNT(DISTINCT trade_date) AS days_with_data,
       @cal_days AS cal_days,
       ROUND(COUNT(DISTINCT trade_date) / NULLIF(@cal_days, 0), 4) AS coverage,
       CONCAT('>= ', @coverage_tol) AS expected,
       CASE WHEN COUNT(DISTINCT trade_date) / NULLIF(@cal_days, 0) >= @coverage_tol
            THEN 'PASS' ELSE 'FAIL' END AS status
FROM stock_data.ods_stk_limit_di
WHERE trade_date BETWEEN @start AND @end;

SELECT 'CHK-1' AS chk, 'ods_stk_limit_missing_days' AS item,
       COUNT(*) AS actual, 0 AS expected,
       CASE WHEN COUNT(*) = 0 THEN 'PASS' ELSE 'FAIL' END AS status
FROM stock_data.ods_trading_day c
LEFT JOIN (
    SELECT trade_date, COUNT(*) AS cnt
    FROM stock_data.ods_stk_limit_di
    WHERE trade_date BETWEEN @start AND @end
    GROUP BY trade_date
) d ON d.trade_date = c.trade_date
WHERE c.trade_date BETWEEN @start AND @end
  AND (d.trade_date IS NULL OR d.cnt < @min_daily_limit);

-- 1.6 股票基础信息（全量表）
SELECT 'CHK-1' AS chk, 'ods_stock_basic_rows' AS item,
       COUNT(*) AS actual,
       CONCAT('>= ', @min_daily_stocks) AS expected,
       CASE WHEN COUNT(*) >= @min_daily_stocks THEN 'PASS' ELSE 'FAIL' END AS status
FROM stock_data.ods_stock_basic_di;

-- =============================================================================
-- CHK-2 预热窗口 ODS（信号区间前 lookback；缺失 → mom120/ma60 早期天失效）
-- =============================================================================
SELECT 'CHK-2' AS chk, 'warmup_stock_detail_days' AS item,
       COUNT(DISTINCT trade_date) AS actual,
       CONCAT('>= ', @lookback_td) AS expected,
       CASE WHEN COUNT(DISTINCT trade_date) >= @lookback_td THEN 'PASS' ELSE 'WARN' END AS status
FROM stock_data.ods_stock_detail_di
WHERE trade_date >= @warmup_start AND trade_date < @start;

SELECT 'CHK-2' AS chk, 'warmup_adj_factor_days' AS item,
       COUNT(DISTINCT trade_date) AS actual,
       CONCAT('>= ', @lookback_td) AS expected,
       CASE WHEN COUNT(DISTINCT trade_date) >= @lookback_td THEN 'PASS' ELSE 'WARN' END AS status
FROM stock_data.ods_adj_factor_di
WHERE trade_date >= @warmup_start AND trade_date < @start;

-- =============================================================================
-- CHK-3 长线因子 / 回测基准
-- =============================================================================
SELECT 'CHK-3' AS chk, 'ods_fina_indicator_rows' AS item,
       COUNT(*) AS actual,
       '>= 10000' AS expected,
       CASE WHEN COUNT(*) >= 10000 THEN 'PASS' ELSE 'FAIL' END AS status
FROM stock_data.ods_fina_indicator
WHERE ann_date <= @end;

SELECT 'CHK-3' AS chk, 'ods_fina_coverage_vs_listed' AS item,
       (SELECT COUNT(DISTINCT ts_code) FROM stock_data.ods_fina_indicator WHERE ann_date <= @end) AS fina_codes,
       (SELECT COUNT(*) FROM stock_data.ods_stock_basic_di) AS basic_codes,
       ROUND(
           (SELECT COUNT(DISTINCT ts_code) FROM stock_data.ods_fina_indicator WHERE ann_date <= @end)
         / NULLIF((SELECT COUNT(*) FROM stock_data.ods_stock_basic_di), 0), 4
       ) AS coverage,
       '>= 0.70' AS expected,
       CASE WHEN (
           (SELECT COUNT(DISTINCT ts_code) FROM stock_data.ods_fina_indicator WHERE ann_date <= @end)
         / NULLIF((SELECT COUNT(*) FROM stock_data.ods_stock_basic_di), 0)
       ) >= 0.70 THEN 'PASS' ELSE 'WARN' END AS status;

SELECT 'CHK-3' AS chk, 'ods_index_hs300_coverage' AS item,
       COUNT(*) AS actual,
       CONCAT('≈ cal_days=', @cal_days) AS expected,
       CASE WHEN COUNT(*) / NULLIF(@cal_days, 0) >= @coverage_tol THEN 'PASS'
            WHEN COUNT(*) > 0 THEN 'WARN'
            ELSE 'WARN' END AS status
FROM stock_data.ods_index_daily_di
WHERE ts_code = '000300.SH'
  AND trade_date BETWEEN @start AND @end;

-- =============================================================================
-- CHK-4 短线软依赖：个股 VP 因子
-- =============================================================================
SELECT 'CHK-4' AS chk, 'dwm_stock_vp_factor_coverage' AS item,
       COUNT(DISTINCT trade_date) AS days_with_data,
       @cal_days AS cal_days,
       ROUND(COUNT(DISTINCT trade_date) / NULLIF(@cal_days, 0), 4) AS coverage,
       CONCAT('>= ', @coverage_tol, ' (short strategy)') AS expected,
       CASE WHEN COUNT(DISTINCT trade_date) / NULLIF(@cal_days, 0) >= @coverage_tol THEN 'PASS'
            WHEN COUNT(DISTINCT trade_date) > 0 THEN 'WARN'
            ELSE 'WARN' END AS status
FROM stock_data.dwm_stock_vp_factor_di
WHERE trade_date BETWEEN @start AND @end;

SELECT 'CHK-4' AS chk, 'dwm_stock_vp_factor_missing_days' AS item,
       COUNT(*) AS actual,
       '0 ideal; WARN if >0' AS expected,
       CASE WHEN COUNT(*) = 0 THEN 'PASS' ELSE 'WARN' END AS status
FROM stock_data.ods_trading_day c
LEFT JOIN (
    SELECT trade_date, COUNT(*) AS cnt
    FROM stock_data.dwm_stock_vp_factor_di
    WHERE trade_date BETWEEN @start AND @end
    GROUP BY trade_date
) d ON d.trade_date = c.trade_date
WHERE c.trade_date BETWEEN @start AND @end
  AND (d.trade_date IS NULL OR d.cnt < @min_vp_factor);

SELECT 'CHK-4-detail' AS chk, 'vp_factor_low_or_missing' AS item,
       c.trade_date, COALESCE(d.cnt, 0) AS row_cnt
FROM stock_data.ods_trading_day c
LEFT JOIN (
    SELECT trade_date, COUNT(*) AS cnt
    FROM stock_data.dwm_stock_vp_factor_di
    WHERE trade_date BETWEEN @start AND @end
    GROUP BY trade_date
) d ON d.trade_date = c.trade_date
WHERE c.trade_date BETWEEN @start AND @end
  AND (d.trade_date IS NULL OR d.cnt < @min_vp_factor)
ORDER BY c.trade_date
LIMIT 50;

-- =============================================================================
-- CHK-5 跨表对齐抽样：日线 ∩ 复权 ∩ 指标（末日）
-- =============================================================================
SET @sample_td = (
    SELECT MAX(trade_date) FROM stock_data.ods_trading_day
    WHERE trade_date BETWEEN @start AND @end
);

SELECT 'CHK-5' AS chk, 'sample_trade_date' AS item,
       CAST(@sample_td AS CHAR) AS actual,
       'latest trading day in range' AS expected,
       CASE WHEN @sample_td IS NOT NULL THEN 'PASS' ELSE 'FAIL' END AS status;

SELECT 'CHK-5' AS chk, 'detail_vs_adj_match_ratio' AS item,
       (SELECT COUNT(*) FROM stock_data.ods_stock_detail_di WHERE trade_date = @sample_td) AS detail_n,
       (SELECT COUNT(*) FROM stock_data.ods_adj_factor_di WHERE trade_date = @sample_td) AS adj_n,
       (
           SELECT COUNT(*)
           FROM stock_data.ods_stock_detail_di d
           JOIN stock_data.ods_adj_factor_di a
             ON a.trade_date = d.trade_date AND a.ts_code = d.ts_code
           WHERE d.trade_date = @sample_td
       ) AS matched,
       ROUND(
           (
               SELECT COUNT(*)
               FROM stock_data.ods_stock_detail_di d
               JOIN stock_data.ods_adj_factor_di a
                 ON a.trade_date = d.trade_date AND a.ts_code = d.ts_code
               WHERE d.trade_date = @sample_td
           ) / NULLIF((SELECT COUNT(*) FROM stock_data.ods_stock_detail_di WHERE trade_date = @sample_td), 0)
       , 4) AS match_ratio,
       '>= 0.95' AS expected,
       CASE WHEN (
           SELECT COUNT(*)
           FROM stock_data.ods_stock_detail_di d
           JOIN stock_data.ods_adj_factor_di a
             ON a.trade_date = d.trade_date AND a.ts_code = d.ts_code
           WHERE d.trade_date = @sample_td
       ) / NULLIF((SELECT COUNT(*) FROM stock_data.ods_stock_detail_di WHERE trade_date = @sample_td), 0)
            >= 0.95 THEN 'PASS' ELSE 'FAIL' END AS status;

SELECT 'CHK-5' AS chk, 'detail_vs_basic_match_ratio' AS item,
       ROUND(
           (
               SELECT COUNT(*)
               FROM stock_data.ods_stock_detail_di d
               JOIN stock_data.ods_daily_basic_di b
                 ON b.trade_date = d.trade_date AND b.ts_code = d.ts_code
               WHERE d.trade_date = @sample_td
           ) / NULLIF((SELECT COUNT(*) FROM stock_data.ods_stock_detail_di WHERE trade_date = @sample_td), 0)
       , 4) AS match_ratio,
       '>= 0.90' AS expected,
       CASE WHEN (
           SELECT COUNT(*)
           FROM stock_data.ods_stock_detail_di d
           JOIN stock_data.ods_daily_basic_di b
             ON b.trade_date = d.trade_date AND b.ts_code = d.ts_code
           WHERE d.trade_date = @sample_td
       ) / NULLIF((SELECT COUNT(*) FROM stock_data.ods_stock_detail_di WHERE trade_date = @sample_td), 0)
            >= 0.90 THEN 'PASS' ELSE 'WARN' END AS status;

-- =============================================================================
-- CHK-6 data_industry 产出层（策略模板 + 信号）
-- =============================================================================
SELECT 'CHK-6' AS chk, 'quant_strategy_active' AS item,
       COUNT(*) AS actual,
       CONCAT('>= ', @min_strategy_cnt) AS expected,
       CASE WHEN COUNT(*) >= @min_strategy_cnt THEN 'PASS' ELSE 'FAIL' END AS status
FROM data_industry.quant_strategy
WHERE is_active = 1;

SELECT 'CHK-6' AS chk, 'quant_strategy_templates' AS item,
       code, name, horizon, is_system, is_active
FROM data_industry.quant_strategy
ORDER BY is_system DESC, id;

SELECT 'CHK-6' AS chk, 'quant_signal_coverage' AS item,
       COUNT(DISTINCT trade_date) AS signal_days,
       @cal_days AS cal_days,
       ROUND(COUNT(DISTINCT trade_date) / NULLIF(@cal_days, 0), 4) AS coverage,
       CONCAT('>= ', @coverage_tol, ' after backfill') AS expected,
       CASE WHEN COUNT(DISTINCT trade_date) / NULLIF(@cal_days, 0) >= @coverage_tol THEN 'PASS'
            WHEN COUNT(DISTINCT trade_date) > 0 THEN 'WARN'
            ELSE 'WARN' END AS status
FROM data_industry.quant_signal_di
WHERE trade_date BETWEEN @start AND @end;

-- 按策略：区间缺信号天数
SELECT 'CHK-6' AS chk, 'quant_signal_missing_by_strategy' AS item,
       s.id AS strategy_id, s.code, s.horizon,
       COUNT(*) AS missing_or_thin_days,
       CASE WHEN COUNT(*) = 0 THEN 'PASS' ELSE 'WARN' END AS status
FROM data_industry.quant_strategy s
CROSS JOIN stock_data.ods_trading_day c
LEFT JOIN (
    SELECT strategy_id, trade_date,
           SUM(action IN ('BUY', 'HOLD')) AS hold_n
    FROM data_industry.quant_signal_di
    WHERE trade_date BETWEEN @start AND @end
    GROUP BY strategy_id, trade_date
) sig ON sig.strategy_id = s.id AND sig.trade_date = c.trade_date
WHERE s.is_active = 1
  AND c.trade_date BETWEEN @start AND @end
  AND (sig.trade_date IS NULL OR COALESCE(sig.hold_n, 0) < @min_signal_per_day)
GROUP BY s.id, s.code, s.horizon;

-- 末日信号抽样
SELECT 'CHK-6' AS chk, 'quant_signal_sample_latest' AS item,
       s.code, sig.trade_date, sig.action, COUNT(*) AS cnt
FROM data_industry.quant_signal_di sig
JOIN data_industry.quant_strategy s ON s.id = sig.strategy_id
WHERE sig.trade_date = (
    SELECT MAX(trade_date) FROM data_industry.quant_signal_di
    WHERE trade_date BETWEEN @start AND @end
)
GROUP BY s.code, sig.trade_date, sig.action
ORDER BY s.code, FIELD(sig.action, 'BUY', 'HOLD', 'SELL');

-- =============================================================================
-- 按日总览（INFO）：一眼看出哪天哪张表缺
-- =============================================================================
SELECT 'DAILY-OVERVIEW' AS chk,
       c.trade_date,
       COALESCE(d.cnt, 0)  AS detail_n,
       COALESCE(a.cnt, 0)  AS adj_n,
       COALESCE(b.cnt, 0)  AS basic_n,
       COALESCE(f.cnt, 0)  AS flow_n,
       COALESCE(l.cnt, 0)  AS limit_n,
       COALESCE(v.cnt, 0)  AS vp_factor_n,
       COALESCE(q.cnt, 0)  AS signal_n,
       CASE
         WHEN COALESCE(d.cnt,0) < @min_daily_stocks
           OR COALESCE(a.cnt,0) < @min_daily_adj
           OR COALESCE(b.cnt,0) < @min_daily_basic
           OR COALESCE(f.cnt,0) < @min_daily_flow
           OR COALESCE(l.cnt,0) < @min_daily_limit
         THEN 'ODS_GAP'
         WHEN COALESCE(v.cnt,0) < @min_vp_factor THEN 'VP_GAP'
         WHEN COALESCE(q.cnt,0) = 0 THEN 'SIGNAL_GAP'
         ELSE 'OK'
       END AS day_status
FROM stock_data.ods_trading_day c
LEFT JOIN (SELECT trade_date, COUNT(*) cnt FROM stock_data.ods_stock_detail_di
           WHERE trade_date BETWEEN @start AND @end GROUP BY trade_date) d
  ON d.trade_date = c.trade_date
LEFT JOIN (SELECT trade_date, COUNT(*) cnt FROM stock_data.ods_adj_factor_di
           WHERE trade_date BETWEEN @start AND @end GROUP BY trade_date) a
  ON a.trade_date = c.trade_date
LEFT JOIN (SELECT trade_date, COUNT(*) cnt FROM stock_data.ods_daily_basic_di
           WHERE trade_date BETWEEN @start AND @end GROUP BY trade_date) b
  ON b.trade_date = c.trade_date
LEFT JOIN (SELECT trade_date, COUNT(*) cnt FROM stock_data.ods_stock_fund_flow_di
           WHERE trade_date BETWEEN @start AND @end GROUP BY trade_date) f
  ON f.trade_date = c.trade_date
LEFT JOIN (SELECT trade_date, COUNT(*) cnt FROM stock_data.ods_stk_limit_di
           WHERE trade_date BETWEEN @start AND @end GROUP BY trade_date) l
  ON l.trade_date = c.trade_date
LEFT JOIN (SELECT trade_date, COUNT(*) cnt FROM stock_data.dwm_stock_vp_factor_di
           WHERE trade_date BETWEEN @start AND @end GROUP BY trade_date) v
  ON v.trade_date = c.trade_date
LEFT JOIN (SELECT trade_date, COUNT(*) cnt FROM data_industry.quant_signal_di
           WHERE trade_date BETWEEN @start AND @end GROUP BY trade_date) q
  ON q.trade_date = c.trade_date
WHERE c.trade_date BETWEEN @start AND @end
ORDER BY c.trade_date;

SELECT 'DAILY-OVERVIEW-SUMMARY' AS chk,
       SUM(day_status = 'OK') AS ok_days,
       SUM(day_status = 'ODS_GAP') AS ods_gap_days,
       SUM(day_status = 'VP_GAP') AS vp_gap_days,
       SUM(day_status = 'SIGNAL_GAP') AS signal_gap_days,
       COUNT(*) AS total_days
FROM (
    SELECT
       CASE
         WHEN COALESCE(d.cnt,0) < @min_daily_stocks
           OR COALESCE(a.cnt,0) < @min_daily_adj
           OR COALESCE(b.cnt,0) < @min_daily_basic
           OR COALESCE(f.cnt,0) < @min_daily_flow
           OR COALESCE(l.cnt,0) < @min_daily_limit
         THEN 'ODS_GAP'
         WHEN COALESCE(v.cnt,0) < @min_vp_factor THEN 'VP_GAP'
         WHEN COALESCE(q.cnt,0) = 0 THEN 'SIGNAL_GAP'
         ELSE 'OK'
       END AS day_status
    FROM stock_data.ods_trading_day c
    LEFT JOIN (SELECT trade_date, COUNT(*) cnt FROM stock_data.ods_stock_detail_di
               WHERE trade_date BETWEEN @start AND @end GROUP BY trade_date) d
      ON d.trade_date = c.trade_date
    LEFT JOIN (SELECT trade_date, COUNT(*) cnt FROM stock_data.ods_adj_factor_di
               WHERE trade_date BETWEEN @start AND @end GROUP BY trade_date) a
      ON a.trade_date = c.trade_date
    LEFT JOIN (SELECT trade_date, COUNT(*) cnt FROM stock_data.ods_daily_basic_di
               WHERE trade_date BETWEEN @start AND @end GROUP BY trade_date) b
      ON b.trade_date = c.trade_date
    LEFT JOIN (SELECT trade_date, COUNT(*) cnt FROM stock_data.ods_stock_fund_flow_di
               WHERE trade_date BETWEEN @start AND @end GROUP BY trade_date) f
      ON f.trade_date = c.trade_date
    LEFT JOIN (SELECT trade_date, COUNT(*) cnt FROM stock_data.ods_stk_limit_di
               WHERE trade_date BETWEEN @start AND @end GROUP BY trade_date) l
      ON l.trade_date = c.trade_date
    LEFT JOIN (SELECT trade_date, COUNT(*) cnt FROM stock_data.dwm_stock_vp_factor_di
               WHERE trade_date BETWEEN @start AND @end GROUP BY trade_date) v
      ON v.trade_date = c.trade_date
    LEFT JOIN (SELECT trade_date, COUNT(*) cnt FROM data_industry.quant_signal_di
               WHERE trade_date BETWEEN @start AND @end GROUP BY trade_date) q
      ON q.trade_date = c.trade_date
    WHERE c.trade_date BETWEEN @start AND @end
) t;

-- =============================================================================
-- FINAL-SUMMARY：先清 FAIL，再处理 WARN
-- =============================================================================
SELECT chk, item, actual, expected, status
FROM (
    SELECT 'CHK-0' AS chk, 'trading_days_in_range' AS item,
           CAST(@cal_days AS CHAR) AS actual, '>0' AS expected,
           CASE WHEN @cal_days > 0 THEN 'PASS' ELSE 'FAIL' END AS status
    UNION ALL
    SELECT 'CHK-0', 'warmup_start',
           IFNULL(CAST(@warmup_start AS CHAR), 'NULL'),
           'NOT NULL',
           CASE WHEN @warmup_start IS NOT NULL THEN 'PASS' ELSE 'FAIL' END
    UNION ALL
    SELECT 'CHK-1', 'ods_stock_detail_coverage',
           CAST((SELECT ROUND(COUNT(DISTINCT trade_date)/NULLIF(@cal_days,0),4)
                 FROM stock_data.ods_stock_detail_di
                 WHERE trade_date BETWEEN @start AND @end) AS CHAR),
           CONCAT('>=', @coverage_tol),
           CASE WHEN (SELECT COUNT(DISTINCT trade_date)
                      FROM stock_data.ods_stock_detail_di
                      WHERE trade_date BETWEEN @start AND @end)/NULLIF(@cal_days,0)
                     >= @coverage_tol THEN 'PASS' ELSE 'FAIL' END
    UNION ALL
    SELECT 'CHK-1', 'ods_adj_factor_coverage',
           CAST((SELECT ROUND(COUNT(DISTINCT trade_date)/NULLIF(@cal_days,0),4)
                 FROM stock_data.ods_adj_factor_di
                 WHERE trade_date BETWEEN @start AND @end) AS CHAR),
           CONCAT('>=', @coverage_tol),
           CASE WHEN (SELECT COUNT(DISTINCT trade_date)
                      FROM stock_data.ods_adj_factor_di
                      WHERE trade_date BETWEEN @start AND @end)/NULLIF(@cal_days,0)
                     >= @coverage_tol THEN 'PASS' ELSE 'FAIL' END
    UNION ALL
    SELECT 'CHK-1', 'ods_daily_basic_coverage',
           CAST((SELECT ROUND(COUNT(DISTINCT trade_date)/NULLIF(@cal_days,0),4)
                 FROM stock_data.ods_daily_basic_di
                 WHERE trade_date BETWEEN @start AND @end) AS CHAR),
           CONCAT('>=', @coverage_tol),
           CASE WHEN (SELECT COUNT(DISTINCT trade_date)
                      FROM stock_data.ods_daily_basic_di
                      WHERE trade_date BETWEEN @start AND @end)/NULLIF(@cal_days,0)
                     >= @coverage_tol THEN 'PASS' ELSE 'FAIL' END
    UNION ALL
    SELECT 'CHK-1', 'ods_stock_fund_flow_coverage',
           CAST((SELECT ROUND(COUNT(DISTINCT trade_date)/NULLIF(@cal_days,0),4)
                 FROM stock_data.ods_stock_fund_flow_di
                 WHERE trade_date BETWEEN @start AND @end) AS CHAR),
           CONCAT('>=', @coverage_tol),
           CASE WHEN (SELECT COUNT(DISTINCT trade_date)
                      FROM stock_data.ods_stock_fund_flow_di
                      WHERE trade_date BETWEEN @start AND @end)/NULLIF(@cal_days,0)
                     >= @coverage_tol THEN 'PASS' ELSE 'FAIL' END
    UNION ALL
    SELECT 'CHK-1', 'ods_stk_limit_coverage',
           CAST((SELECT ROUND(COUNT(DISTINCT trade_date)/NULLIF(@cal_days,0),4)
                 FROM stock_data.ods_stk_limit_di
                 WHERE trade_date BETWEEN @start AND @end) AS CHAR),
           CONCAT('>=', @coverage_tol),
           CASE WHEN (SELECT COUNT(DISTINCT trade_date)
                      FROM stock_data.ods_stk_limit_di
                      WHERE trade_date BETWEEN @start AND @end)/NULLIF(@cal_days,0)
                     >= @coverage_tol THEN 'PASS' ELSE 'FAIL' END
    UNION ALL
    SELECT 'CHK-1', 'ods_stock_basic_rows',
           CAST((SELECT COUNT(*) FROM stock_data.ods_stock_basic_di) AS CHAR),
           CONCAT('>=', @min_daily_stocks),
           CASE WHEN (SELECT COUNT(*) FROM stock_data.ods_stock_basic_di) >= @min_daily_stocks
                THEN 'PASS' ELSE 'FAIL' END
    UNION ALL
    SELECT 'CHK-3', 'ods_fina_indicator_rows',
           CAST((SELECT COUNT(*) FROM stock_data.ods_fina_indicator WHERE ann_date <= @end) AS CHAR),
           '>=10000',
           CASE WHEN (SELECT COUNT(*) FROM stock_data.ods_fina_indicator WHERE ann_date <= @end) >= 10000
                THEN 'PASS' ELSE 'FAIL' END
    UNION ALL
    SELECT 'CHK-3', 'ods_index_hs300_coverage',
           CAST((SELECT COUNT(*) FROM stock_data.ods_index_daily_di
                 WHERE ts_code='000300.SH' AND trade_date BETWEEN @start AND @end) AS CHAR),
           CONCAT('≈', @cal_days),
           CASE WHEN (SELECT COUNT(*) FROM stock_data.ods_index_daily_di
                      WHERE ts_code='000300.SH' AND trade_date BETWEEN @start AND @end)
                      / NULLIF(@cal_days,0) >= @coverage_tol THEN 'PASS' ELSE 'WARN' END
    UNION ALL
    SELECT 'CHK-4', 'dwm_stock_vp_factor_coverage',
           CAST((SELECT ROUND(COUNT(DISTINCT trade_date)/NULLIF(@cal_days,0),4)
                 FROM stock_data.dwm_stock_vp_factor_di
                 WHERE trade_date BETWEEN @start AND @end) AS CHAR),
           CONCAT('>=', @coverage_tol, ' short'),
           CASE WHEN (SELECT COUNT(DISTINCT trade_date)
                      FROM stock_data.dwm_stock_vp_factor_di
                      WHERE trade_date BETWEEN @start AND @end)/NULLIF(@cal_days,0)
                     >= @coverage_tol THEN 'PASS' ELSE 'WARN' END
    UNION ALL
    SELECT 'CHK-6', 'quant_strategy_active',
           CAST((SELECT COUNT(*) FROM data_industry.quant_strategy WHERE is_active=1) AS CHAR),
           CONCAT('>=', @min_strategy_cnt),
           CASE WHEN (SELECT COUNT(*) FROM data_industry.quant_strategy WHERE is_active=1)
                     >= @min_strategy_cnt THEN 'PASS' ELSE 'FAIL' END
    UNION ALL
    SELECT 'CHK-6', 'quant_signal_coverage',
           CAST((SELECT ROUND(COUNT(DISTINCT trade_date)/NULLIF(@cal_days,0),4)
                 FROM data_industry.quant_signal_di
                 WHERE trade_date BETWEEN @start AND @end) AS CHAR),
           CONCAT('>=', @coverage_tol, ' after signal backfill'),
           CASE WHEN (SELECT COUNT(DISTINCT trade_date)
                      FROM data_industry.quant_signal_di
                      WHERE trade_date BETWEEN @start AND @end)/NULLIF(@cal_days,0)
                     >= @coverage_tol THEN 'PASS'
                WHEN (SELECT COUNT(*) FROM data_industry.quant_signal_di
                      WHERE trade_date BETWEEN @start AND @end) > 0 THEN 'WARN'
                ELSE 'WARN' END
) final_summary
ORDER BY FIELD(status, 'FAIL', 'WARN', 'PASS'), chk, item;
