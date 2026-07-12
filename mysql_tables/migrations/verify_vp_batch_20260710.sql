-- VP 批次结果核查（替换 @td 为交易日 YYYY-MM-DD）
USE stock_data;

SET @td = '2026-07-10';

-- 1) 评分表是否有当日数据
SELECT 'vp_score_cnt' AS metric, COUNT(*) AS val
FROM dwm_industry_vp_score_di
WHERE trade_date = @td AND vp_window = 20;

-- 2) 六维新字段是否已写入（升级后非 NULL 应 > 0）
SELECT
    COUNT(*) AS total,
    SUM(continuity_strength IS NOT NULL) AS has_continuity,
    SUM(trend_return_20d IS NOT NULL) AS has_trend20,
    SUM(leader_strength IS NOT NULL) AS has_leader,
    SUM(score_leader IS NOT NULL) AS has_score_leader
FROM dwm_industry_vp_score_di
WHERE trade_date = @td AND vp_window = 20;

-- 3) VP 分分布（合并池）
SELECT
    MIN(vp_score) AS min_score,
    MAX(vp_score) AS max_score,
    ROUND(AVG(vp_score), 2) AS avg_score,
    SUM(vp_score >= 80) AS cnt_burst,
    COUNT(*) AS cnt_all
FROM dwm_industry_vp_score_di
WHERE trade_date = @td AND vp_window = 20;

-- 4) Top10（行业+概念合并排名）
SELECT rank_vp, content_type, industry_name, vp_score,
       score_continuity, score_vol, score_trend, score_breadth, score_breakout, score_leader,
       continuity_strength, trend_return_20d, leader_strength
FROM dwm_industry_vp_score_di
WHERE trade_date = @td AND vp_window = 20
ORDER BY rank_vp
LIMIT 10;

-- 5) 严格突破因子是否计算
SELECT
    SUM(is_breakout_strict = 1) AS strict_breakout_stocks,
    COUNT(*) AS factor_rows
FROM dwm_stock_vp_factor_di
WHERE trade_date = @td AND vp_window = 20;

-- 6) 配置权重是否为六维新权重
SELECT weight_vol, weight_trend, weight_continuity, weight_breadth, weight_breakout, weight_leader
FROM dwm_vp_config
WHERE config_key = '__global__' AND is_active = 1
ORDER BY effective_date DESC
LIMIT 1;
