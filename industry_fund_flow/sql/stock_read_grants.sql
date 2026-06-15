-- 行业资金流网站只读账号：stock_data 库 DWM + 个股 ODS（root 执行一次）
--   mysql -u root -p < industry_fund_flow/sql/stock_read_grants.sql

GRANT SELECT ON stock_data.dwm_dc_industry_fund_flow_di TO 'app_user'@'localhost';
GRANT SELECT ON stock_data.dwm_dc_industry_fund_flow_di TO 'app_user'@'%';
GRANT SELECT ON stock_data.dwm_dc_industry_trend_strength_di TO 'app_user'@'localhost';
GRANT SELECT ON stock_data.dwm_dc_industry_trend_strength_di TO 'app_user'@'%';
GRANT SELECT ON stock_data.dwm_dc_industry_market_heat_di TO 'app_user'@'localhost';
GRANT SELECT ON stock_data.dwm_dc_industry_market_heat_di TO 'app_user'@'%';
GRANT SELECT ON stock_data.dwm_dc_industry_prosperity_di TO 'app_user'@'localhost';
GRANT SELECT ON stock_data.dwm_dc_industry_prosperity_di TO 'app_user'@'%';
GRANT SELECT ON stock_data.dwm_dc_industry_diffusion_di TO 'app_user'@'localhost';
GRANT SELECT ON stock_data.dwm_dc_industry_diffusion_di TO 'app_user'@'%';
GRANT SELECT ON stock_data.dwm_market_breadth_di TO 'app_user'@'localhost';
GRANT SELECT ON stock_data.dwm_market_breadth_di TO 'app_user'@'%';

GRANT SELECT ON stock_data.ods_stock_fund_flow_di TO 'app_user'@'localhost';
GRANT SELECT ON stock_data.ods_stock_fund_flow_di TO 'app_user'@'%';
GRANT SELECT ON stock_data.ods_stock_detail_di TO 'app_user'@'localhost';
GRANT SELECT ON stock_data.ods_stock_detail_di TO 'app_user'@'%';
GRANT SELECT ON stock_data.ods_limit_list_di TO 'app_user'@'localhost';
GRANT SELECT ON stock_data.ods_limit_list_di TO 'app_user'@'%';
GRANT SELECT ON stock_data.ods_ths_member_di TO 'app_user'@'localhost';
GRANT SELECT ON stock_data.ods_ths_member_di TO 'app_user'@'%';

GRANT SELECT ON stock_data.dwm_sector_stock_dragon_score_di TO 'app_user'@'localhost';
GRANT SELECT ON stock_data.dwm_sector_stock_dragon_score_di TO 'app_user'@'%';
GRANT SELECT ON stock_data.sector_dragon_summary_di TO 'app_user'@'localhost';
GRANT SELECT ON stock_data.sector_dragon_summary_di TO 'app_user'@'%';
GRANT SELECT ON stock_data.sector_dragon_config TO 'app_user'@'localhost';
GRANT SELECT ON stock_data.sector_dragon_config TO 'app_user'@'%';
GRANT SELECT ON stock_data.ods_dc_member_di TO 'app_user'@'localhost';
GRANT SELECT ON stock_data.ods_dc_member_di TO 'app_user'@'%';
GRANT SELECT ON stock_data.ods_report_rc_di TO 'app_user'@'localhost';
GRANT SELECT ON stock_data.ods_report_rc_di TO 'app_user'@'%';
GRANT SELECT ON stock_data.ods_dc_daily_di TO 'app_user'@'localhost';
GRANT SELECT ON stock_data.ods_dc_daily_di TO 'app_user'@'%';

FLUSH PRIVILEGES;
