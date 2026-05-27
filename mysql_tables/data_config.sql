-- ============================================================================
-- data_config：Token + db_sync_task（fetch_config/transform_config 驱动同步）
-- 用法：source dw-utils/func.sh && init_data_config_schema
-- ============================================================================

CREATE DATABASE IF NOT EXISTS data_config DEFAULT CHARSET utf8mb4;
USE data_config;

-- db_token
CREATE TABLE IF NOT EXISTS db_token (
    id            BIGINT PRIMARY KEY AUTO_INCREMENT,
    token_type    VARCHAR(32)  NOT NULL COMMENT 'tushare / akshare',
    token_id      VARCHAR(256) NOT NULL COMMENT 'token',
    api_url       VARCHAR(256) NULL COMMENT 'Tushare 代理根地址',
    status        TINYINT      NOT NULL DEFAULT 1 COMMENT '1=有效 0=无效',
    remark        VARCHAR(256) NULL,
    created_at    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    start_date    DATETIME     NULL,
    end_date      DATETIME     NULL,
    UNIQUE KEY uk_token_type (token_type, status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='数据源 Token';

INSERT INTO db_token (token_type, token_id, api_url, status, remark, start_date, end_date) VALUES
('tushare', '0ced3a73b7055fc7e38a2a7665db0fa371b51518e838dfce9fba5ae5', NULL, 0, '历史 Tushare Pro', '1999-01-01', '2999-12-31'),
('tushare', 'kOxsKJfSHCAsIrePsxWkfUdGIbMhfLWyTEfPSdueqnzMsqGigIeIaprTDglfSstX', 'http://a.sszhixia.cn/', 1, '当前 Tushare Pro（代理）', '1999-01-01', '2026-11-22');

-- db_sync_task
CREATE TABLE IF NOT EXISTS db_sync_task (
    id                    BIGINT PRIMARY KEY AUTO_INCREMENT,
    proxy_source          VARCHAR(32)  NOT NULL COMMENT 'akshare / tushare',
    source_table          VARCHAR(64)  NOT NULL COMMENT '接口方法名',
    target_database       VARCHAR(64)  NOT NULL DEFAULT 'stock_data',
    target_table          VARCHAR(128) NOT NULL,
    target_table_describe VARCHAR(128) NOT NULL,
    sync_mode             VARCHAR(16)  NOT NULL DEFAULT 'snapshot' COMMENT 'full/incremental/snapshot',
    fetch_config          JSON         NULL COMMENT '拉数参数',
    transform_config      JSON         NULL COMMENT '字段映射',
    status                TINYINT      NOT NULL DEFAULT 1,
    remark                VARCHAR(512) NULL,
    created_at            DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at            DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='同步任务配置';

-- AkShare → ods_trading_day
INSERT INTO db_sync_task (
    proxy_source, source_table, target_database, target_table, target_table_describe,
    sync_mode, fetch_config, transform_config, status, remark
) VALUES (
    'akshare', 'tool_trade_date_hist_sina', 'stock_data', 'ods_trading_day', '交易日', 'full',
    JSON_OBJECT('params', JSON_OBJECT()),
    JSON_OBJECT(
        'keep_columns', JSON_ARRAY('trade_date'),
        'date_columns', JSON_OBJECT('trade_date', NULL),
        'dedupe', JSON_ARRAY('trade_date'),
        'dropna', JSON_ARRAY('trade_date')
    ),
    1, '全量更新交易日(AkShare)'
);

-- Tushare trade_cal → ods_trading_day_di
INSERT INTO db_sync_task (
    proxy_source, source_table, target_database, target_table, target_table_describe,
    sync_mode, fetch_config, transform_config, status, remark
) VALUES (
    'tushare', 'trade_cal', 'stock_data', 'ods_trading_day_di', '交易日', 'full',
    JSON_OBJECT(
        'token_type', 'tushare',
        'exchange_list', JSON_ARRAY('SSE', 'SZSE'),
        'date_range', JSON_OBJECT(
            'full', JSON_OBJECT('start_date', '20200101', 'end_date', '$today_plus_365'),
            'day', JSON_OBJECT('start_date', '$trade_date', 'end_date', '$trade_date')
        ),
        'inject_date_range', TRUE,
        'full_start', '20200101',
        'full_end_offset_days', 365
    ),
    JSON_OBJECT(
        'rename', JSON_OBJECT('cal_date', 'trade_date'),
        'date_columns', JSON_OBJECT('trade_date', '%Y%m%d', 'pretrade_date', '%Y%m%d'),
        'keep_columns', JSON_ARRAY('exchange', 'trade_date', 'is_open', 'pretrade_date'),
        'dedupe', JSON_ARRAY('exchange', 'trade_date'),
        'dropna', JSON_ARRAY('trade_date')
    ),
    1, '全量更新交易日(Tushare)'
);

-- Tushare moneyflow → ods_stock_fund_flow_di（按日 snapshot，字段与接口一致）
INSERT INTO db_sync_task (
    proxy_source, source_table, target_database, target_table, target_table_describe,
    sync_mode, fetch_config, transform_config, status, remark
) VALUES (
    'tushare', 'moneyflow', 'stock_data', 'ods_stock_fund_flow_di', '个股资金流向', 'snapshot',
    JSON_OBJECT(
        'token_type', 'tushare',
        'params', JSON_OBJECT('trade_date', '$trade_date'),
        'inject_date_range', FALSE
    ),
    JSON_OBJECT(
        'date_columns', JSON_OBJECT('trade_date', '%Y%m%d'),
        'dedupe', JSON_ARRAY('trade_date', 'ts_code'),
        'dropna', JSON_ARRAY('trade_date', 'ts_code'),
        'keep_columns', JSON_ARRAY(
            'ts_code', 'trade_date',
            'buy_sm_vol', 'buy_sm_amount', 'sell_sm_vol', 'sell_sm_amount',
            'buy_md_vol', 'buy_md_amount', 'sell_md_vol', 'sell_md_amount',
            'buy_lg_vol', 'buy_lg_amount', 'sell_lg_vol', 'sell_lg_amount',
            'buy_elg_vol', 'buy_elg_amount', 'sell_elg_vol', 'sell_elg_amount',
            'net_mf_vol', 'net_mf_amount'
        )
    ),
    1, 'A股个股资金流向日快照(Tushare moneyflow)'
);

-- Tushare moneyflow_ind_dc → ods_industry_fund_flow_di（按日 snapshot，接口字段映射入库）
INSERT INTO db_sync_task (
    proxy_source, source_table, target_database, target_table, target_table_describe,
    sync_mode, fetch_config, transform_config, status, remark
) VALUES (
    'tushare', 'moneyflow_ind_dc', 'stock_data', 'ods_industry_fund_flow_di', '东财板块资金流向', 'snapshot',
    JSON_OBJECT(
        'token_type', 'tushare',
        'params', JSON_OBJECT('trade_date', '$trade_date'),
        'inject_date_range', FALSE
    ),
    JSON_OBJECT(
        'rename', JSON_OBJECT('ts_code', 'industry_code', 'name', 'industry_name'),
        'date_columns', JSON_OBJECT('trade_date', '%Y%m%d'),
        'dedupe', JSON_ARRAY('trade_date', 'industry_code'),
        'dropna', JSON_ARRAY('trade_date', 'industry_code'),
        'keep_columns', JSON_ARRAY(
            'trade_date', 'content_type', 'industry_code', 'industry_name', 'pct_change', 'close',
            'net_amount', 'net_amount_rate',
            'buy_elg_amount', 'buy_elg_amount_rate',
            'buy_lg_amount', 'buy_lg_amount_rate',
            'buy_md_amount', 'buy_md_amount_rate',
            'buy_sm_amount', 'buy_sm_amount_rate',
            'buy_sm_amount_stock', 'rank'
        )
    ),
    1, '东财行业/概念/地域板块资金流向日快照(Tushare moneyflow_ind_dc)'
);

-- Tushare index_classify → ods_industry_classify（full，字段与接口一致）
INSERT INTO db_sync_task (
    proxy_source, source_table, target_database, target_table, target_table_describe,
    sync_mode, fetch_config, transform_config, status, remark
) VALUES (
    'tushare', 'index_classify', 'stock_data', 'ods_industry_classify', '申万行业分类', 'full',
    JSON_OBJECT(
        'token_type', 'tushare',
        'calls', JSON_ARRAY(
            JSON_OBJECT(
                'src', 'SW2014',
                'fields', 'index_code,industry_name,parent_code,level,industry_code,is_pub,src'
            ),
            JSON_OBJECT(
                'src', 'SW2021',
                'fields', 'index_code,industry_name,parent_code,level,industry_code,is_pub,src'
            )
        ),
        'inject_date_range', FALSE
    ),
    JSON_OBJECT(
        'dedupe', JSON_ARRAY('src', 'industry_code'),
        'dropna', JSON_ARRAY('src', 'industry_code'),
        'keep_columns', JSON_ARRAY(
            'index_code', 'industry_name', 'parent_code', 'level', 'industry_code', 'is_pub', 'src'
        )
    ),
    1, '全量更新申万行业分类(Tushare index_classify, SW2014+SW2021)'
);

-- Tushare sw_daily → ods_industry_daily_di（按日 snapshot，字段与接口一致）
INSERT INTO db_sync_task (
    proxy_source, source_table, target_database, target_table, target_table_describe,
    sync_mode, fetch_config, transform_config, status, remark
) VALUES (
    'tushare', 'sw_daily', 'stock_data', 'ods_industry_daily_di', '申万行业日线行情', 'snapshot',
    JSON_OBJECT(
        'token_type', 'tushare',
        'params', JSON_OBJECT('trade_date', '$trade_date'),
        'inject_date_range', FALSE
    ),
    JSON_OBJECT(
        'date_columns', JSON_OBJECT('trade_date', '%Y%m%d'),
        'dedupe', JSON_ARRAY('trade_date', 'ts_code'),
        'dropna', JSON_ARRAY('trade_date', 'ts_code'),
        'keep_columns', JSON_ARRAY(
            'ts_code', 'trade_date', 'name', 'open', 'low', 'high', 'close',
            'change', 'pct_change', 'vol', 'amount', 'pe', 'pb', 'float_mv', 'total_mv'
        )
    ),
    1, '申万行业日线行情日快照(Tushare sw_daily)'
);
