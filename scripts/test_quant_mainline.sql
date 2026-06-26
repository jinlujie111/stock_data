-- 需求3 量化主线 — 手工 SQL 验收（行业 Top10 + 概念 Top10 分榜）
-- 用法: mysql -u app_user -p stock_data < scripts/test_quant_mainline.sql

SET @td = (SELECT MAX(trade_date) FROM dwm_dc_industry_fund_flow_di);

SELECT @top_n := COALESCE(
    (SELECT top_n FROM quant_mainline_config
     WHERE config_key = '__global__' AND is_active = 1
     ORDER BY effective_date DESC LIMIT 1),
    10
) AS cfg_top_n;

SELECT '=== 1. 前置 DWM 行数 ===' AS step;
SELECT 'fund_flow' AS tbl, COUNT(*) AS cnt FROM dwm_dc_industry_fund_flow_di WHERE trade_date = @td
UNION ALL SELECT 'market_heat', COUNT(*) FROM dwm_dc_industry_market_heat_di WHERE trade_date = @td
UNION ALL SELECT 'trend', COUNT(*) FROM dwm_dc_industry_trend_strength_di WHERE trade_date = @td
UNION ALL SELECT 'diffusion', COUNT(*) FROM dwm_dc_industry_diffusion_di WHERE trade_date = @td
UNION ALL SELECT 'prosperity', COUNT(*) FROM dwm_dc_industry_prosperity_di WHERE trade_date = @td
UNION ALL SELECT 'dragon_summary', COUNT(*) FROM sector_dragon_summary_di WHERE trade_date = @td AND score_mode = 'mvp';

SELECT '=== 2. 配置 ===' AS step;
SELECT content_types, top_n, ma_window_rank, effective_date
FROM quant_mainline_config
WHERE config_key = '__global__' AND is_active = 1
ORDER BY effective_date DESC LIMIT 1;

SELECT '=== 3. 主表汇总 ===' AS step;
SELECT
    trade_date,
    COUNT(*) AS total,
    SUM(content_type = '行业') AS cnt_industry,
    SUM(content_type = '概念') AS cnt_concept,
    SUM(content_type = '行业' AND is_top3 = 1) AS top_industry,
    SUM(content_type = '概念' AND is_top3 = 1) AS top_concept,
    SUM(is_top3 = 1) AS topn_total,
    ROUND(AVG(main_score), 2) AS avg_main_score
FROM dws_dc_industry_quant_mainline_di
WHERE trade_date = @td;

SELECT '=== 4. 行业 TopN ===' AS step;
SELECT rank_no, industry_name, industry_code, main_score, main_score_ma5, rank_score
FROM dws_dc_industry_quant_mainline_di
WHERE trade_date = @td AND content_type = '行业' AND is_top3 = 1
ORDER BY rank_no;

SELECT '=== 5. 概念 TopN ===' AS step;
SELECT rank_no, industry_name, industry_code, main_score, main_score_ma5, rank_score
FROM dws_dc_industry_quant_mainline_di
WHERE trade_date = @td AND content_type = '概念' AND is_top3 = 1
ORDER BY rank_no;

SELECT '=== 6. 信号分布 ===' AS step;
SELECT signal_status, COUNT(*) AS cnt,
    SUM(signal_start = 1) AS start_flag,
    SUM(signal_exit = 1) AS exit_flag
FROM dws_dc_industry_quant_mainline_signal_di
WHERE trade_date = @td
GROUP BY signal_status;

SELECT '=== 7. 一致性检查（应为 0 行）===' AS step;
-- 行业 TopN 数量（不足 @top_n 块时允许更少）
SELECT 'industry_top_count' AS check_name, COUNT(*) AS bad
FROM dws_dc_industry_quant_mainline_di m
WHERE m.trade_date = @td AND m.content_type = '行业' AND m.is_top3 = 1
HAVING COUNT(*) <> LEAST(@top_n, (
    SELECT COUNT(*) FROM dws_dc_industry_quant_mainline_di
    WHERE trade_date = @td AND content_type = '行业'
))
UNION ALL
SELECT 'concept_top_count', COUNT(*)
FROM dws_dc_industry_quant_mainline_di m
WHERE m.trade_date = @td AND m.content_type = '概念' AND m.is_top3 = 1
HAVING COUNT(*) <> LEAST(@top_n, (
    SELECT COUNT(*) FROM dws_dc_industry_quant_mainline_di
    WHERE trade_date = @td AND content_type = '概念'
))
UNION ALL
SELECT 'row_mismatch', ABS(m.c - s.c)
FROM (SELECT COUNT(*) AS c FROM dws_dc_industry_quant_mainline_di WHERE trade_date = @td) m,
     (SELECT COUNT(*) AS c FROM dws_dc_industry_quant_mainline_signal_di WHERE trade_date = @td) s
WHERE m.c <> s.c
UNION ALL
SELECT 'null_ftelp', COUNT(*)
FROM dws_dc_industry_quant_mainline_di
WHERE trade_date = @td
  AND (score_f IS NULL OR score_t IS NULL OR score_e IS NULL
       OR score_l IS NULL OR score_p IS NULL OR main_score IS NULL)
HAVING COUNT(*) > 0
UNION ALL
SELECT 'dup_rank_per_type', COUNT(*)
FROM (
    SELECT content_type, rank_no
    FROM dws_dc_industry_quant_mainline_di
    WHERE trade_date = @td AND rank_no IS NOT NULL
    GROUP BY content_type, rank_no
    HAVING COUNT(*) > 1
) x
UNION ALL
SELECT 'top_flag_rank_mismatch', COUNT(*)
FROM dws_dc_industry_quant_mainline_di
WHERE trade_date = @td
  AND content_type IN ('行业', '概念')
  AND (
    (is_top3 = 1 AND rank_no > @top_n)
    OR (is_top3 = 0 AND rank_no IS NOT NULL AND rank_no <= @top_n)
  );

SELECT '=== 8. TopN 类型构成 ===' AS step;
SELECT content_type, COUNT(*) AS cnt
FROM dws_dc_industry_quant_mainline_di
WHERE trade_date = @td AND is_top3 = 1
GROUP BY content_type;
