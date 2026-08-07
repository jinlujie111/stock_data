-- =============================================================================
-- ODS：stk_high_shock / stk_alert（2026-08-07）
--
-- 用法：
--   mysql -u root -p < mysql_tables/migrations/20260807_ods_stk_high_shock_alert.sql
-- 试跑：
--   source dw-utils/func.sh
--   run_data_sync YYYYMMDD --source-table stk_high_shock
--   run_data_sync YYYYMMDD --source-table stk_alert
-- =============================================================================

CREATE TABLE IF NOT EXISTS stock_data.ods_stk_high_shock_di (
    id            BIGINT PRIMARY KEY AUTO_INCREMENT,
    trade_date    DATE           NOT NULL COMMENT '公告/交易日期',
    ts_code       VARCHAR(16)    NOT NULL COMMENT 'TS代码',
    name          VARCHAR(64)    NULL COMMENT '股票名称',
    trade_market  VARCHAR(32)    NULL COMMENT '交易所',
    reason        VARCHAR(512)   NULL COMMENT '异常说明',
    period        VARCHAR(128)   NULL COMMENT '异常期间',
    UNIQUE KEY uk_stk_high_shock (trade_date, ts_code, reason(128)),
    KEY idx_stk_high_shock_ts (ts_code, trade_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='个股严重异常波动(Tushare stk_high_shock)';

CREATE TABLE IF NOT EXISTS stock_data.ods_stk_alert_di (
    id            BIGINT PRIMARY KEY AUTO_INCREMENT,
    trade_date    DATE           NOT NULL COMMENT '同步业务日(按日拉取)',
    ts_code       VARCHAR(16)    NOT NULL COMMENT 'TS代码',
    name          VARCHAR(64)    NULL COMMENT '股票名称',
    start_date    DATE           NULL COMMENT '重点提示起始日期',
    end_date      DATE           NULL COMMENT '重点提示参考截至日期',
    alert_type    VARCHAR(64)    NULL COMMENT '提示类型(接口字段type)',
    UNIQUE KEY uk_stk_alert (trade_date, ts_code, start_date, end_date, alert_type),
    KEY idx_stk_alert_ts (ts_code, start_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='交易所重点提示证券(Tushare stk_alert)';

-- 幂等登记同步任务
INSERT INTO data_config.db_sync_task (
    proxy_source, source_table, target_database, target_table, target_table_describe,
    sync_mode, fetch_config, transform_config, status, remark
)
SELECT
    'tushare', 'stk_high_shock', 'stock_data', 'ods_stk_high_shock_di', '个股严重异常波动', 'snapshot',
    JSON_OBJECT(
        'token_type', 'tushare',
        'params', JSON_OBJECT('trade_date', '$trade_date'),
        'inject_date_range', FALSE
    ),
    JSON_OBJECT(
        'date_columns', JSON_OBJECT('trade_date', NULL),
        'snapshot_delete_column', 'trade_date',
        'dedupe', JSON_ARRAY('trade_date', 'ts_code', 'reason'),
        'dropna', JSON_ARRAY('trade_date', 'ts_code'),
        'keep_columns', JSON_ARRAY(
            'trade_date', 'ts_code', 'name', 'trade_market', 'reason', 'period'
        )
    ),
    1, '个股严重异常波动日快照(Tushare stk_high_shock；约6000积分)'
FROM DUAL
WHERE NOT EXISTS (
    SELECT 1 FROM data_config.db_sync_task
    WHERE proxy_source = 'tushare' AND source_table = 'stk_high_shock'
);

INSERT INTO data_config.db_sync_task (
    proxy_source, source_table, target_database, target_table, target_table_describe,
    sync_mode, fetch_config, transform_config, status, remark
)
SELECT
    'tushare', 'stk_alert', 'stock_data', 'ods_stk_alert_di', '交易所重点提示证券', 'snapshot',
    JSON_OBJECT(
        'token_type', 'tushare',
        'params', JSON_OBJECT('trade_date', '$trade_date'),
        'inject_date_range', FALSE
    ),
    JSON_OBJECT(
        'rename', JSON_OBJECT('type', 'alert_type'),
        'inject_trade_date_column', 'trade_date',
        'date_columns', JSON_OBJECT('start_date', NULL, 'end_date', NULL),
        'snapshot_delete_column', 'trade_date',
        'dedupe', JSON_ARRAY('trade_date', 'ts_code', 'start_date', 'end_date', 'alert_type'),
        'dropna', JSON_ARRAY('trade_date', 'ts_code'),
        'keep_columns', JSON_ARRAY(
            'trade_date', 'ts_code', 'name', 'start_date', 'end_date', 'alert_type'
        )
    ),
    1, '交易所重点提示证券日快照(Tushare stk_alert；约6000积分；trade_date=同步日)'
FROM DUAL
WHERE NOT EXISTS (
    SELECT 1 FROM data_config.db_sync_task
    WHERE proxy_source = 'tushare' AND source_table = 'stk_alert'
);

UPDATE data_config.db_sync_task
SET status = 1,
    remark = CASE
        WHEN remark LIKE '%stk_high_shock%' OR remark LIKE '%stk_alert%' OR remark LIKE '%严重异常%' OR remark LIKE '%重点提示%'
            THEN remark
        ELSE remark
    END
WHERE source_table IN ('stk_high_shock', 'stk_alert');

SELECT
    id,
    source_table,
    target_table,
    status,
    LEFT(remark, 100) AS remark_prefix
FROM data_config.db_sync_task
WHERE source_table IN ('stk_high_shock', 'stk_alert')
ORDER BY source_table;
