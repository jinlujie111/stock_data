-- 下线：量化选板块（申万一级轮动）业务表
-- 执行: mysql -u root -p < mysql_tables/migrations/20260723_drop_rotation_sector_selection.sql
--
-- 仅删除 rotation_*；ODS（含 sw_daily → ods_industry_daily_di）继续同步，不停用。

DROP TABLE IF EXISTS stock_data.rotation_backtest_nav;
DROP TABLE IF EXISTS stock_data.rotation_backtest_trade;
DROP TABLE IF EXISTS stock_data.rotation_backtest_run;
DROP TABLE IF EXISTS stock_data.rotation_signal_di;
DROP TABLE IF EXISTS stock_data.rotation_strategy;

-- 若曾误建在 data_industry，一并清理
DROP TABLE IF EXISTS data_industry.rotation_backtest_nav;
DROP TABLE IF EXISTS data_industry.rotation_backtest_trade;
DROP TABLE IF EXISTS data_industry.rotation_backtest_run;
DROP TABLE IF EXISTS data_industry.rotation_signal_di;
DROP TABLE IF EXISTS data_industry.rotation_strategy;
