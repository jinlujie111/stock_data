-- ============================================================================
-- 已有 stock_data 环境：配置/摘要表重命名（2026-06）
-- 新环境直接 mysql < mysql_tables/stock_data.sql 即可，无需本脚本
-- ============================================================================
USE stock_data;

RENAME TABLE quant_mainline_config TO dwm_dc_mainline_config;
RENAME TABLE sector_dragon_config TO dwm_dc_sector_dragon_config;
RENAME TABLE sector_dragon_summary_di TO dwm_sector_dragon_summary_di;

-- Web 只读授权（若已执行过旧版 grants，补跑新表名）
-- mysql -u root -p < industry_fund_flow/sql/stock_read_grants.sql
