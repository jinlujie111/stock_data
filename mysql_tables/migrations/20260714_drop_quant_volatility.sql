-- 下线：量化主线（需求3）+ 波动率 Web 报表
-- 执行: mysql -u root -p stock_data < mysql_tables/migrations/20260714_drop_quant_volatility.sql

DROP TABLE IF EXISTS dws_dc_industry_quant_mainline_signal_di;
DROP TABLE IF EXISTS dws_dc_industry_quant_mainline_di;
DROP TABLE IF EXISTS dwm_dc_mainline_config;
DROP TABLE IF EXISTS dwm_dc_industry_volatility_di;
DROP TABLE IF EXISTS dwm_market_volatility_di;
