-- 下线：量化选股（策略 / 信号 / 买卖点 / 回测）
-- 执行: mysql -u root -p data_industry < mysql_tables/migrations/20260716_drop_quant_stock_selection.sql

DROP TABLE IF EXISTS quant_backtest_nav;
DROP TABLE IF EXISTS quant_backtest_trade;
DROP TABLE IF EXISTS quant_backtest_run;
DROP TABLE IF EXISTS quant_signal_di;
DROP TABLE IF EXISTS quant_trade_log;
DROP TABLE IF EXISTS quant_strategy;
