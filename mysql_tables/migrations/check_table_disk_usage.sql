-- =============================================================================
-- 磁盘占用排查：各库表体积 + 日期跨度（在生产机执行）
--
--   source dw-utils/func.sh
--   mysql -h "$MYSQL_HOST" -P "$MYSQL_PORT" -u "$MYSQL_USER" -p"$MYSQL_PASSWORD" \
--     < mysql_tables/migrations/check_table_disk_usage.sql
--
-- 或 root：
--   mysql -uroot -p < mysql_tables/migrations/check_table_disk_usage.sql
-- =============================================================================

-- 1) 各库总占用
SELECT
    table_schema AS db_name,
    ROUND(SUM(data_length + index_length) / 1024 / 1024 / 1024, 2) AS size_gb,
    ROUND(SUM(data_length) / 1024 / 1024 / 1024, 2) AS data_gb,
    ROUND(SUM(index_length) / 1024 / 1024 / 1024, 2) AS index_gb,
    COUNT(*) AS table_cnt
FROM information_schema.tables
WHERE table_schema IN ('stock_data', 'data_industry', 'data_config')
GROUP BY table_schema
ORDER BY size_gb DESC;

-- 2) 单表 Top 40（优先看这个决定清谁）
SELECT
    table_schema AS db_name,
    table_name,
    ROUND((data_length + index_length) / 1024 / 1024, 1) AS size_mb,
    ROUND(data_length / 1024 / 1024, 1) AS data_mb,
    ROUND(index_length / 1024 / 1024, 1) AS index_mb,
    table_rows AS approx_rows,
    ROUND(index_length / NULLIF(data_length, 0), 2) AS index_to_data_ratio,
    engine,
    create_options
FROM information_schema.tables
WHERE table_schema IN ('stock_data', 'data_industry', 'data_config')
ORDER BY (data_length + index_length) DESC
LIMIT 40;

-- 3) stock_data 大表常见日期跨度（确认能否按保留期删）
--    若某表极慢可跳过或拆开执行
SELECT 'ods_cyq_chips_di' AS tbl, MIN(trade_date) AS min_d, MAX(trade_date) AS max_d, COUNT(*) AS row_cnt
FROM stock_data.ods_cyq_chips_di
UNION ALL
SELECT 'ods_stock_detail_di', MIN(trade_date), MAX(trade_date), COUNT(*) FROM stock_data.ods_stock_detail_di
UNION ALL
SELECT 'ods_daily_basic_di', MIN(trade_date), MAX(trade_date), COUNT(*) FROM stock_data.ods_daily_basic_di
UNION ALL
SELECT 'ods_stock_fund_flow_di', MIN(trade_date), MAX(trade_date), COUNT(*) FROM stock_data.ods_stock_fund_flow_di
UNION ALL
SELECT 'ods_adj_factor_di', MIN(trade_date), MAX(trade_date), COUNT(*) FROM stock_data.ods_adj_factor_di
UNION ALL
SELECT 'ods_stk_limit_di', MIN(trade_date), MAX(trade_date), COUNT(*) FROM stock_data.ods_stk_limit_di
UNION ALL
SELECT 'ods_hk_hold_di', MIN(trade_date), MAX(trade_date), COUNT(*) FROM stock_data.ods_hk_hold_di
UNION ALL
SELECT 'ods_margin_detail_di', MIN(trade_date), MAX(trade_date), COUNT(*) FROM stock_data.ods_margin_detail_di
UNION ALL
SELECT 'ods_limit_list_di', MIN(trade_date), MAX(trade_date), COUNT(*) FROM stock_data.ods_limit_list_di
UNION ALL
SELECT 'dwm_stock_vp_factor_di', MIN(trade_date), MAX(trade_date), COUNT(*) FROM stock_data.dwm_stock_vp_factor_di
UNION ALL
SELECT 'dwm_sector_stock_dragon_score_di', MIN(trade_date), MAX(trade_date), COUNT(*) FROM stock_data.dwm_sector_stock_dragon_score_di;

-- 4) InnoDB / binlog 相关（需 PROCESS 权限，失败可忽略）
SHOW VARIABLES WHERE Variable_name IN (
    'datadir',
    'innodb_file_per_table',
    'log_bin',
    'binlog_expire_logs_seconds',
    'expire_logs_days',
    'max_binlog_size'
);

SHOW BINARY LOGS;
