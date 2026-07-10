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

-- db_llm_token：大模型 API（OpenAI 兼容），供需求4 AI 核心池等场景
CREATE TABLE IF NOT EXISTS db_llm_token (
    id            BIGINT PRIMARY KEY AUTO_INCREMENT,
    provider      VARCHAR(32)  NOT NULL COMMENT '厂商标识 openai/deepseek/qwen/doubao/custom',
    model_name    VARCHAR(64)  NOT NULL COMMENT 'API model 参数，如 gpt-4o-mini',
    api_key       VARCHAR(512) NOT NULL COMMENT 'API Key / Token',
    api_url       VARCHAR(256) NOT NULL COMMENT 'OpenAI 兼容根地址，如 https://api.openai.com/v1',
    status        TINYINT      NOT NULL DEFAULT 1 COMMENT '1=有效 0=停用',
    is_default    TINYINT      NOT NULL DEFAULT 0 COMMENT '1=未指定 model 时的默认',
    priority      INT          NOT NULL DEFAULT 100 COMMENT '越小越优先',
    remark        VARCHAR(256) NULL,
    start_date    DATETIME     NULL,
    end_date      DATETIME     NULL,
    created_at    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_llm_provider_model (provider, model_name),
    KEY idx_llm_status_default (status, is_default, priority)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='大模型 API Token（需求4 等）';

-- 示例行（status=0，填入真实 api_key 后改 status=1；同一时刻建议仅一个 is_default=1）
INSERT INTO db_llm_token (
    provider, model_name, api_key, api_url, status, is_default, priority, remark, start_date, end_date
) VALUES
(
    'openai', 'gpt-4o-mini', 'REPLACE_WITH_YOUR_KEY',
    'https://api.openai.com/v1', 0, 1, 10,
    'OpenAI 官方；启用: UPDATE db_llm_token SET api_key=..., status=1 WHERE provider=''openai''',
    '1999-01-01', '2999-12-31'
),
(
    'deepseek', 'deepseek-chat', 'REPLACE_WITH_YOUR_KEY',
    'https://api.deepseek.com/v1', 0, 0, 20,
    'DeepSeek OpenAI 兼容接口',
    '1999-01-01', '2999-12-31'
),
(
    'qwen', 'qwen-plus', 'REPLACE_WITH_YOUR_KEY',
    'https://dashscope.aliyuncs.com/compatible-mode/v1', 0, 0, 30,
    '通义千问 compatible-mode',
    '1999-01-01', '2999-12-31'
);

-- db_sync_task
CREATE TABLE IF NOT EXISTS db_sync_task (
    id                    BIGINT PRIMARY KEY AUTO_INCREMENT,
    proxy_source          VARCHAR(32)  NOT NULL COMMENT 'akshare / tushare',
    source_table          VARCHAR(64)  NOT NULL COMMENT '接口方法名',
    target_database       VARCHAR(64)  NOT NULL DEFAULT 'stock_data',
    target_table          VARCHAR(128) NOT NULL,
    target_table_describe VARCHAR(128) NOT NULL,
    sync_mode             VARCHAR(16)  NOT NULL DEFAULT 'snapshot' COMMENT 'full/incremental/snapshot',
    schedule_type         VARCHAR(16)  NOT NULL DEFAULT 'daily'  COMMENT 'daily/monthly，daily每天执行，monthly每月1号执行',
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
        )
    ),
    1, '东财行业/概念/地域板块资金流向日快照(Tushare moneyflow_ind_dc)'
);

-- Tushare dc_index → ods_dc_index_di（按日 snapshot，东财板块指数）
INSERT INTO db_sync_task (
    proxy_source, source_table, target_database, target_table, target_table_describe,
    sync_mode, fetch_config, transform_config, status, remark
) VALUES (
    'tushare', 'dc_index', 'stock_data', 'ods_dc_index_di', '东财板块指数', 'snapshot',
    JSON_OBJECT(
        'token_type', 'tushare',
        'params', JSON_OBJECT('trade_date', '$trade_date'),
        'calls', JSON_ARRAY(
            JSON_OBJECT('params', JSON_OBJECT('idx_type', '行业板块')),
            JSON_OBJECT('params', JSON_OBJECT('idx_type', '概念板块')),
            JSON_OBJECT('params', JSON_OBJECT('idx_type', '地域板块'))
        ),
        'inject_date_range', FALSE
    ),
    JSON_OBJECT(
        'rename', JSON_OBJECT('name', 'dc_name', 'leading', 'dc_leading'),
        'date_columns', JSON_OBJECT('trade_date', '%Y%m%d'),
        'dedupe', JSON_ARRAY('trade_date', 'ts_code'),
        'dropna', JSON_ARRAY('trade_date', 'ts_code'),
        'keep_columns', JSON_ARRAY(
            'trade_date', 'ts_code', 'dc_name', 'dc_leading', 'leading_code',
            'pct_change', 'leading_pct', 'total_mv', 'turnover_rate',
            'up_num', 'down_num', 'idx_type', 'level'
        )
    ),
    1, '东财板块指数日快照(Tushare dc_index, 行业+概念+地域；单次最多5000行/类型，需约6000积分)'
);

-- Tushare dc_daily → ods_dc_daily_di（按日 snapshot，东财板块日线行情）
INSERT INTO db_sync_task (
    proxy_source, source_table, target_database, target_table, target_table_describe,
    sync_mode, fetch_config, transform_config, status, remark
) VALUES (
    'tushare', 'dc_daily', 'stock_data', 'ods_dc_daily_di', '东财板块日线行情', 'snapshot',
    JSON_OBJECT(
        'token_type', 'tushare',
        'params', JSON_OBJECT('trade_date', '$trade_date'),
        'calls', JSON_ARRAY(
            JSON_OBJECT('params', JSON_OBJECT('idx_type', '行业板块')),
            JSON_OBJECT('params', JSON_OBJECT('idx_type', '概念板块')),
            JSON_OBJECT('params', JSON_OBJECT('idx_type', '地域板块'))
        ),
        'inject_date_range', FALSE
    ),
    JSON_OBJECT(
        'date_columns', JSON_OBJECT('trade_date', '%Y%m%d'),
        'dedupe', JSON_ARRAY('trade_date', 'ts_code'),
        'dropna', JSON_ARRAY('trade_date', 'ts_code'),
        'keep_columns', JSON_ARRAY(
            'ts_code', 'trade_date', 'open', 'high', 'low', 'close',
            'change', 'pct_change', 'vol', 'amount', 'swing', 'turnover_rate'
        )
    ),
    1, '东财板块日线日快照(Tushare dc_daily, 行业+概念+地域；单次最多2000行/类型，需约6000积分)'
);

-- Tushare dc_member → ods_dc_member_di（按日 snapshot，按板块循环拉全量成分）
INSERT INTO db_sync_task (
    proxy_source, source_table, target_database, target_table, target_table_describe,
    sync_mode, fetch_config, transform_config, status, remark
) VALUES (
    'tushare', 'dc_member', 'stock_data', 'ods_dc_member_di', '东财板块成分', 'snapshot',
    JSON_OBJECT(
        'token_type', 'tushare',
        'board_table', 'ods_industry_fund_flow_di',
        'content_types', JSON_ARRAY('行业', '概念', '地域'),
        'sleep_seconds', 0.2
    ),
    JSON_OBJECT(
        'date_columns', JSON_OBJECT('trade_date', '%Y%m%d'),
        'dedupe', JSON_ARRAY('trade_date', 'ts_code', 'con_code'),
        'dropna', JSON_ARRAY('trade_date', 'ts_code', 'con_code'),
        'keep_columns', JSON_ARRAY('trade_date', 'ts_code', 'con_code', 'name')
    ),
    1, '东财板块成分日快照：按 moneyflow_ind_dc 板块列表循环 dc_member(ts_code)，避免单次5000行截断'
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
                'params', JSON_OBJECT(
                    'src', 'SW2014',
                    'fields', 'index_code,industry_name,parent_code,level,industry_code,is_pub,src'
                )
            ),
            JSON_OBJECT(
                'params', JSON_OBJECT(
                    'src', 'SW2021',
                    'fields', 'index_code,industry_name,parent_code,level,industry_code,is_pub,src'
                )
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

-- Tushare daily → ods_stock_detail_di（按日 snapshot，A股日线行情）
INSERT INTO db_sync_task (
    proxy_source, source_table, target_database, target_table, target_table_describe,
    sync_mode, fetch_config, transform_config, status, remark
) VALUES (
    'tushare', 'daily', 'stock_data', 'ods_stock_detail_di', 'A股日线行情', 'snapshot',
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
            'open', 'high', 'low', 'close', 'pre_close',
            'change', 'pct_chg', 'vol', 'amount'
        )
    ),
    1, 'A股日线行情日快照(Tushare daily)'
);

-- Tushare daily_basic → ods_daily_basic_di（按日 snapshot，市盈率/市值/换手率等）
INSERT INTO db_sync_task (
    proxy_source, source_table, target_database, target_table, target_table_describe,
    sync_mode, fetch_config, transform_config, status, remark
) VALUES (
    'tushare', 'daily_basic', 'stock_data', 'ods_daily_basic_di', 'A股每日指标', 'snapshot',
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
            'ts_code', 'trade_date', 'close',
            'turnover_rate', 'turnover_rate_f', 'volume_ratio',
            'pe', 'pe_ttm', 'pb', 'ps', 'ps_ttm',
            'dv_ratio', 'dv_ttm',
            'total_share', 'float_share', 'free_share',
            'total_mv', 'circ_mv'
        )
    ),
    1, 'A股每日指标日快照(Tushare daily_basic；含总市值/流通市值/换手率，供需求4 V1权重等)'
);

-- Tushare cyq_chips → ods_cyq_chips_di（按日 snapshot，按个股循环拉取筹码分布）
INSERT INTO db_sync_task (
    proxy_source, source_table, target_database, target_table, target_table_describe,
    sync_mode, fetch_config, transform_config, status, remark
) VALUES (
    'tushare', 'cyq_chips', 'stock_data', 'ods_cyq_chips_di', '每日筹码分布', 'snapshot',
    JSON_OBJECT(
        'token_type', 'tushare',
        'params', JSON_OBJECT('trade_date', '$trade_date'),
        'stock_table', 'ods_stock_detail_di',
        'stock_database', 'stock_data',
        'missing_only', TRUE,
        'sleep_seconds', 0.35,
        'batch_log_every', 200
    ),
    JSON_OBJECT(
        'date_columns', JSON_OBJECT('trade_date', '%Y%m%d'),
        'dedupe', JSON_ARRAY('trade_date', 'ts_code', 'price'),
        'dropna', JSON_ARRAY('trade_date', 'ts_code', 'price'),
        'keep_columns', JSON_ARRAY('ts_code', 'trade_date', 'price', 'percent'),
        'add_timestamps', TRUE
    ),
    1, 'A股每日筹码分布(Tushare cyq_chips，按 ods_stock_detail_di 当日个股循环；需较高积分)'
);

-- Tushare limit_list_d → ods_limit_list_di（按日 snapshot，含涨停U/跌停D/炸板Z）
INSERT INTO db_sync_task (
    proxy_source, source_table, target_database, target_table, target_table_describe,
    sync_mode, fetch_config, transform_config, status, remark
) VALUES (
    'tushare', 'limit_list_d', 'stock_data', 'ods_limit_list_di', '涨跌停炸板列表', 'snapshot',
    JSON_OBJECT(
        'token_type', 'tushare',
        'params', JSON_OBJECT('trade_date', '$trade_date'),
        'inject_date_range', FALSE
    ),
    JSON_OBJECT(
        'date_columns', JSON_OBJECT('trade_date', '%Y%m%d'),
        'dedupe', JSON_ARRAY('trade_date', 'ts_code', 'limit'),
        'dropna', JSON_ARRAY('trade_date', 'ts_code', 'limit'),
        'keep_columns', JSON_ARRAY(
            'trade_date', 'ts_code', 'industry', 'name', 'close', 'pct_chg', 'amount',
            'limit_amount', 'float_mv', 'total_mv', 'turnover_ratio', 'fd_amount',
            'first_time', 'last_time', 'open_times', 'up_stat', 'limit_times', 'limit'
        )
    ),
    1, '涨跌停炸板日快照(Tushare limit_list_d，U/D/Z)'
);

-- Tushare index_member_all → ods_index_member_all（full，申万行业成分分级）
INSERT INTO db_sync_task (
    proxy_source, source_table, target_database, target_table, target_table_describe,
    sync_mode, fetch_config, transform_config, status, remark
) VALUES (
    'tushare', 'index_member_all', 'stock_data', 'ods_index_member_all', '申万行业成分分级', 'full',
    JSON_OBJECT(
        'token_type', 'tushare',
        'params', JSON_OBJECT('is_new', 'Y'),
        'page_size', 2000,
        'max_pages', 4,
        'sleep_seconds', 0.3,
        'inject_date_range', FALSE
    ),
    JSON_OBJECT(
        'date_columns', JSON_OBJECT('in_date', '%Y%m%d', 'out_date', '%Y%m%d'),
        'dedupe', JSON_ARRAY('ts_code', 'l3_code', 'in_date'),
        'dropna', JSON_ARRAY('ts_code', 'l3_code'),
        'keep_columns', JSON_ARRAY(
            'l1_code', 'l1_name', 'l2_code', 'l2_name', 'l3_code', 'l3_name',
            'ts_code', 'name', 'in_date', 'out_date', 'is_new'
        )
    ),
    1, '全量更新申万行业成分(Tushare index_member_all, is_new=Y；offset 分页最多4页×2000行)'
);

-- Tushare fina_indicator_vip → ods_fina_indicator（全市场一季/一日；需约5000积分）
INSERT INTO db_sync_task (
    proxy_source, source_table, target_database, target_table, target_table_describe,
    sync_mode, fetch_config, transform_config, status, remark
) VALUES (
    'tushare', 'fina_indicator_vip', 'stock_data', 'ods_fina_indicator', '上市公司财务指标', 'snapshot',
    JSON_OBJECT(
        'token_type', 'tushare',
        'params', JSON_OBJECT('ann_date', '$trade_date'),
        'full_start', '20180101',
        'sleep_seconds', 0.5,
        'inject_date_range', FALSE
    ),
    JSON_OBJECT(
        'date_columns', JSON_OBJECT('ann_date', '%Y%m%d', 'end_date', '%Y%m%d'),
        'dedupe', JSON_ARRAY('ts_code', 'end_date', 'ann_date'),
        'dropna', JSON_ARRAY('ts_code', 'end_date', 'ann_date'),
        'keep_columns', JSON_ARRAY(
            'ts_code', 'ann_date', 'end_date',
            'eps', 'dt_eps', 'bps', 'roe', 'roe_waa', 'roe_dt', 'roa',
            'grossprofit_margin', 'netprofit_margin', 'debt_to_assets', 'profit_dedt',
            'tr_yoy', 'or_yoy', 'netprofit_yoy', 'dt_netprofit_yoy',
            'op_yoy', 'ebt_yoy', 'equity_yoy', 'q_profit_yoy', 'q_sales_yoy', 'ocf_yoy'
        )
    ),
    1, '财务指标VIP(Tushare fina_indicator_vip)；snapshot=ann_date全市场，full=按季period回溯'
);

-- Tushare stock_company → ods_stock_company_di（full，按交易所 SSE/SZSE/BSE 全量）
INSERT INTO db_sync_task (
    proxy_source, source_table, target_database, target_table, target_table_describe,
    sync_mode, schedule_type, fetch_config, transform_config, status, remark
) VALUES (
    'tushare', 'stock_company', 'stock_data', 'ods_stock_company_di', '上市公司基本信息', 'full', 'monthly',
    JSON_OBJECT(
        'token_type', 'tushare',
        'exchange_list', JSON_ARRAY('SSE', 'SZSE', 'BSE'),
        'params', JSON_OBJECT(
            'fields', 'ts_code,exchange,chairman,manager,secretary,reg_capital,setup_date,province,city,introduction,website,employees,main_business,business_scope'
        ),
        'inject_date_range', FALSE,
        'sleep_seconds', 0.3
    ),
    JSON_OBJECT(
        'date_columns', JSON_OBJECT('setup_date', '%Y%m%d'),
        'dedupe', JSON_ARRAY('ts_code'),
        'dropna', JSON_ARRAY('ts_code'),
        'keep_columns', JSON_ARRAY(
            'ts_code', 'exchange', 'chairman', 'manager', 'secretary', 'reg_capital',
            'setup_date', 'province', 'city', 'introduction', 'website', 'employees',
            'main_business', 'business_scope'
        )
    ),
    1, '上市公司简介/主营/经营范围(Tushare stock_company)；每月1号全量刷新，供需求4 AI核心池'
);

-- Tushare fina_mainbz_vip → ods_fina_mainbz_di（按产品 type=P；snapshot=近2季，full=季末回溯；monthly 由月批 --force 执行）
INSERT INTO db_sync_task (
    proxy_source, source_table, target_database, target_table, target_table_describe,
    sync_mode, schedule_type, fetch_config, transform_config, status, remark
) VALUES (
    'tushare', 'fina_mainbz_vip', 'stock_data', 'ods_fina_mainbz_di', '主营业务构成(按产品)', 'snapshot', 'monthly',
    JSON_OBJECT(
        'token_type', 'tushare',
        'params', JSON_OBJECT(
            'type', 'P',
            'fields', 'ts_code,end_date,bz_item,bz_code,bz_sales,bz_profit,bz_cost,curr_type,update_flag'
        ),
        'full_start', '20180101',
        'snapshot_periods', 2,
        'sleep_seconds', 0.5,
        'inject_date_range', FALSE
    ),
    JSON_OBJECT(
        'date_columns', JSON_OBJECT('end_date', '%Y%m%d'),
        'constants', JSON_OBJECT('bz_type', 'P'),
        'dedupe', JSON_ARRAY('ts_code', 'end_date', 'bz_type', 'bz_item'),
        'dropna', JSON_ARRAY('ts_code', 'end_date'),
        'keep_columns', JSON_ARRAY(
            'ts_code', 'end_date', 'bz_type', 'bz_item', 'bz_code',
            'bz_sales', 'bz_profit', 'bz_cost', 'curr_type', 'update_flag'
        )
    ),
    1, '主营业务构成VIP(Tushare fina_mainbz_vip,type=P)；snapshot=近2季全市场；monthly+月批 --force（单次约1万行上限，需配合 fina_mainbz 按股补全）'
);

-- Tushare fina_mainbz → ods_fina_mainbz_di（按股循环，补 VIP 截断缺失；missing_only 默认 true）
INSERT INTO db_sync_task (
    proxy_source, source_table, target_database, target_table, target_table_describe,
    sync_mode, schedule_type, fetch_config, transform_config, status, remark
) VALUES (
    'tushare', 'fina_mainbz', 'stock_data', 'ods_fina_mainbz_di', '主营业务构成(按股补全)', 'incremental', 'monthly',
    JSON_OBJECT(
        'token_type', 'tushare',
        'stock_table', 'ods_stock_company_di',
        'stock_database', 'stock_data',
        'missing_only', TRUE,
        'snapshot_periods', 2,
        'params', JSON_OBJECT(
            'type', 'P',
            'fields', 'ts_code,end_date,bz_item,bz_code,bz_sales,bz_profit,bz_cost,curr_type,update_flag'
        ),
        'sleep_seconds', 0.35,
        'batch_log_every', 200,
        'inject_date_range', FALSE
    ),
    JSON_OBJECT(
        'date_columns', JSON_OBJECT('end_date', '%Y%m%d'),
        'constants', JSON_OBJECT('bz_type', 'P'),
        'dedupe', JSON_ARRAY('ts_code', 'end_date', 'bz_type', 'bz_item'),
        'dropna', JSON_ARRAY('ts_code', 'end_date'),
        'keep_columns', JSON_ARRAY(
            'ts_code', 'end_date', 'bz_type', 'bz_item', 'bz_code',
            'bz_sales', 'bz_profit', 'bz_cost', 'curr_type', 'update_flag'
        )
    ),
    1, '主营业务构成按股补全(Tushare fina_mainbz)；补近2季无记录股票，约2000积分'
);

-- Tushare report_rc → ods_report_rc_di（按日 snapshot，卖方盈利预测）
INSERT INTO db_sync_task (
    proxy_source, source_table, target_database, target_table, target_table_describe,
    sync_mode, fetch_config, transform_config, status, remark
) VALUES (
    'tushare', 'report_rc', 'stock_data', 'ods_report_rc_di', '卖方盈利预测', 'snapshot',
    JSON_OBJECT(
        'token_type', 'tushare',
        'params', JSON_OBJECT('report_date', '$trade_date'),
        'inject_date_range', FALSE
    ),
    JSON_OBJECT(
        'date_columns', JSON_OBJECT('report_date', '%Y%m%d'),
        'snapshot_delete_column', 'report_date',
        'dedupe', JSON_ARRAY('ts_code', 'report_date', 'org_name', 'quarter'),
        'dropna', JSON_ARRAY('ts_code', 'report_date'),
        'keep_columns', JSON_ARRAY(
            'ts_code', 'name', 'report_date', 'report_title', 'report_type', 'classify',
            'org_name', 'author_name', 'quarter',
            'op_rt', 'op_pr', 'tp', 'np', 'eps', 'pe', 'rd', 'roe', 'ev_ebitda',
            'rating', 'max_price', 'min_price', 'imp_dg'
        )
    ),
    1, '卖方研报盈利预测日快照(Tushare report_rc，report_date=$trade_date，约8000积分)'
);

-- Tushare index_daily → ods_index_daily_di（按日 snapshot，多指数 RS 基准）
INSERT INTO db_sync_task (
    proxy_source, source_table, target_database, target_table, target_table_describe,
    sync_mode, fetch_config, transform_config, status, remark
) VALUES (
    'tushare', 'index_daily', 'stock_data', 'ods_index_daily_di', '指数日线行情', 'snapshot',
    JSON_OBJECT(
        'token_type', 'tushare',
        'params', JSON_OBJECT('trade_date', '$trade_date'),
        'calls', JSON_ARRAY(
            JSON_OBJECT('params', JSON_OBJECT('ts_code', '000300.SH')),
            JSON_OBJECT('params', JSON_OBJECT('ts_code', '000001.SH')),
            JSON_OBJECT('params', JSON_OBJECT('ts_code', '399001.SZ'))
        ),
        'inject_date_range', FALSE
    ),
    JSON_OBJECT(
        'date_columns', JSON_OBJECT('trade_date', '%Y%m%d'),
        'dedupe', JSON_ARRAY('trade_date', 'ts_code'),
        'dropna', JSON_ARRAY('trade_date', 'ts_code'),
        'keep_columns', JSON_ARRAY(
            'ts_code', 'trade_date', 'open', 'high', 'low', 'close', 'pre_close',
            'change', 'pct_chg', 'vol', 'amount'
        )
    ),
    1, '指数日线日快照(Tushare index_daily；沪深300/上证/深证成指，trade_date=$trade_date)'
);

-- Tushare etf_share_size → ods_etf_share_size_di（按日 snapshot，沪深 ETF 份额/规模）
INSERT INTO db_sync_task (
    proxy_source, source_table, target_database, target_table, target_table_describe,
    sync_mode, fetch_config, transform_config, status, remark
) VALUES (
    'tushare', 'etf_share_size', 'stock_data', 'ods_etf_share_size_di', 'ETF份额规模', 'snapshot',
    JSON_OBJECT(
        'token_type', 'tushare',
        'params', JSON_OBJECT('trade_date', '$trade_date'),
        'exchange_list', JSON_ARRAY('SSE', 'SZSE'),
        'inject_date_range', FALSE
    ),
    JSON_OBJECT(
        'date_columns', JSON_OBJECT('trade_date', '%Y%m%d'),
        'dedupe', JSON_ARRAY('trade_date', 'ts_code'),
        'dropna', JSON_ARRAY('trade_date', 'ts_code'),
        'keep_columns', JSON_ARRAY(
            'trade_date', 'ts_code', 'etf_name', 'total_share', 'total_size',
            'nav', 'close', 'exchange'
        )
    ),
    1, 'ETF份额规模日快照(Tushare etf_share_size，按交易所SSE+SZSE，约8000积分，建议19点后)'
);

-- Tushare etf_basic → ods_etf_basic_di（full，上市 ETF 基础信息与跟踪指数）
INSERT INTO db_sync_task (
    proxy_source, source_table, target_database, target_table, target_table_describe,
    sync_mode, fetch_config, transform_config, status, remark
) VALUES (
    'tushare', 'etf_basic', 'stock_data', 'ods_etf_basic_di', 'ETF基础信息', 'full',
    JSON_OBJECT(
        'token_type', 'tushare',
        'params', JSON_OBJECT('list_status', 'L'),
        'inject_date_range', FALSE
    ),
    JSON_OBJECT(
        'date_columns', JSON_OBJECT('setup_date', '%Y%m%d', 'list_date', '%Y%m%d'),
        'dedupe', JSON_ARRAY('ts_code'),
        'dropna', JSON_ARRAY('ts_code'),
        'keep_columns', JSON_ARRAY(
            'ts_code', 'csname', 'extname', 'cname', 'index_code', 'index_name',
            'setup_date', 'list_date', 'list_status', 'exchange', 'mgr_name',
            'custod_name', 'mgt_fee', 'etf_type'
        )
    ),
    1, '全量更新上市ETF基础信息(Tushare etf_basic，list_status=L)'
);

-- Tushare ths_index → ods_ths_index_di（full，同花顺板块指数列表）
INSERT INTO db_sync_task (
    proxy_source, source_table, target_database, target_table, target_table_describe,
    sync_mode, fetch_config, transform_config, status, remark
) VALUES (
    'tushare', 'ths_index', 'stock_data', 'ods_ths_index_di', '同花顺板块指数', 'full',
    JSON_OBJECT(
        'token_type', 'tushare',
        'params', JSON_OBJECT('exchange', 'A'),
        'inject_date_range', FALSE
    ),
    JSON_OBJECT(
        'rename', JSON_OBJECT('type', 'index_type'),
        'date_columns', JSON_OBJECT('list_date', '%Y%m%d'),
        'dedupe', JSON_ARRAY('ts_code'),
        'dropna', JSON_ARRAY('ts_code'),
        'keep_columns', JSON_ARRAY(
            'ts_code', 'name', 'count', 'exchange', 'list_date', 'index_type'
        )
    ),
    1, '全量更新同花顺板块指数(Tushare ths_index, exchange=A；需约6000积分)'
);

-- Tushare ths_daily → ods_ths_daily_di（按日 snapshot，同花顺板块指数日线）
INSERT INTO db_sync_task (
    proxy_source, source_table, target_database, target_table, target_table_describe,
    sync_mode, fetch_config, transform_config, status, remark
) VALUES (
    'tushare', 'ths_daily', 'stock_data', 'ods_ths_daily_di', '同花顺板块指数日线', 'snapshot',
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
            'ts_code', 'trade_date', 'open', 'high', 'low', 'close', 'pre_close',
            'avg_price', 'change', 'pct_change', 'vol', 'turnover_rate', 'total_mv', 'float_mv'
        )
    ),
    1, '同花顺板块指数日线日快照(Tushare ths_daily, trade_date全市场；单次最多3000行，需约6000积分)'
);

-- Tushare ths_member → ods_ths_member_di（full，按 ods_ths_index_di 循环拉成分）
INSERT INTO db_sync_task (
    proxy_source, source_table, target_database, target_table, target_table_describe,
    sync_mode, fetch_config, transform_config, status, remark
) VALUES (
    'tushare', 'ths_member', 'stock_data', 'ods_ths_member_di', '同花顺板块成分', 'full',
    JSON_OBJECT(
        'token_type', 'tushare',
        'index_table', 'ods_ths_index_di',
        'index_database', 'stock_data',
        'index_exchange', 'A',
        'sleep_seconds', 0.35,
        'inject_date_range', FALSE
    ),
    JSON_OBJECT(
        'rename', JSON_OBJECT('con_name', 'name'),
        'date_columns', JSON_OBJECT('in_date', '%Y%m%d', 'out_date', '%Y%m%d'),
        'dedupe', JSON_ARRAY('ts_code', 'con_code'),
        'dropna', JSON_ARRAY('ts_code', 'con_code'),
        'keep_columns', JSON_ARRAY(
            'ts_code', 'con_code', 'name', 'weight', 'in_date', 'out_date', 'is_new'
        )
    ),
    1, '全量更新同花顺板块成分(Tushare ths_member；依赖 ods_ths_index_di，按 ts_code 循环；需约6000积分)'
);

-- Tushare ths_hot → ods_ths_hot_di（按日 snapshot，同花顺App热榜）
INSERT INTO db_sync_task (
    proxy_source, source_table, target_database, target_table, target_table_describe,
    sync_mode, fetch_config, transform_config, status, remark
) VALUES (
    'tushare', 'ths_hot', 'stock_data', 'ods_ths_hot_di', '同花顺App热榜', 'snapshot',
    JSON_OBJECT(
        'token_type', 'tushare',
        'params', JSON_OBJECT('trade_date', '$trade_date', 'is_new', 'Y'),
        'market_list', JSON_ARRAY(
            '热股', 'ETF', '可转债', '行业板块', '概念板块',
            '期货', '港股', '热基', '美股'
        ),
        'sleep_seconds', 0.2,
        'inject_date_range', FALSE
    ),
    JSON_OBJECT(
        'rename', JSON_OBJECT('rank', 'ths_rank'),
        'date_columns', JSON_OBJECT('trade_date', '%Y%m%d'),
        'dedupe', JSON_ARRAY('trade_date', 'market', 'ts_code'),
        'dropna', JSON_ARRAY('trade_date', 'market', 'ts_code'),
        'snapshot_delete_column', 'trade_date',
        'keep_columns', JSON_ARRAY(
            'trade_date', 'market', 'data_type', 'ts_code', 'ts_name',
            'ths_rank', 'pct_change', 'current_price', 'concept',
            'rank_reason', 'hot', 'rank_time'
        )
    ),
    1, '同花顺App热榜日快照(Tushare ths_hot, is_new=Y收盘榜；按market循环；单次最多2000行/类型，需约6000积分，建议22:30后)'
);

-- Tushare dc_hot → ods_dc_hot_di（按日 snapshot，东财App热榜）
INSERT INTO db_sync_task (
    proxy_source, source_table, target_database, target_table, target_table_describe,
    sync_mode, fetch_config, transform_config, status, remark
) VALUES (
    'tushare', 'dc_hot', 'stock_data', 'ods_dc_hot_di', '东财App热榜', 'snapshot',
    JSON_OBJECT(
        'token_type', 'tushare',
        'params', JSON_OBJECT('trade_date', '$trade_date', 'is_new', 'Y'),
        'market_list', JSON_ARRAY('A股市场', 'ETF基金', '港股市场', '美股市场'),
        'hot_type_list', JSON_ARRAY('人气榜', '飙升榜'),
        'sleep_seconds', 0.2,
        'inject_date_range', FALSE
    ),
    JSON_OBJECT(
        'rename', JSON_OBJECT('rank', 'dc_rank'),
        'date_columns', JSON_OBJECT('trade_date', '%Y%m%d'),
        'dedupe', JSON_ARRAY('trade_date', 'market', 'hot_type', 'ts_code'),
        'dropna', JSON_ARRAY('trade_date', 'market', 'hot_type', 'ts_code'),
        'snapshot_delete_column', 'trade_date',
        'keep_columns', JSON_ARRAY(
            'trade_date', 'market', 'hot_type', 'data_type', 'ts_code', 'ts_name',
            'dc_rank', 'pct_change', 'current_price', 'rank_time'
        )
    ),
    1, '东财App热榜日快照(Tushare dc_hot, is_new=Y收盘榜；market×hot_type循环；单次最多2000行/组合，需约8000积分，建议22:30后)'
);

-- Tushare stock_basic → ods_stock_basic_di（full，按交易所全量刷新上市股票）
INSERT INTO db_sync_task (
    proxy_source, source_table, target_database, target_table, target_table_describe,
    sync_mode, fetch_config, transform_config, status, remark
) VALUES (
    'tushare', 'stock_basic', 'stock_data', 'ods_stock_basic_di', 'A股基础信息', 'full',
    JSON_OBJECT(
        'token_type', 'tushare',
        'exchange_list', JSON_ARRAY('SSE', 'SZSE', 'BSE'),
        'params', JSON_OBJECT('list_status', 'L'),
        'inject_date_range', FALSE,
        'sleep_seconds', 0.2
    ),
    JSON_OBJECT(
        'date_columns', JSON_OBJECT('list_date', '%Y%m%d', 'delist_date', '%Y%m%d'),
        'dedupe', JSON_ARRAY('ts_code'),
        'dropna', JSON_ARRAY('ts_code'),
        'keep_columns', JSON_ARRAY(
            'ts_code', 'symbol', 'name', 'area', 'industry', 'fullname', 'enname', 'cnspell',
            'market', 'exchange', 'curr_type', 'list_status', 'list_date', 'delist_date', 'is_hs'
        )
    ),
    1, '全量更新A股基础信息(Tushare stock_basic, list_status=L, SSE+SZSE+BSE；供股票搜索/VPA)'
);

-- Tushare top_list → ods_top_list_di（按日 snapshot，龙虎榜每日明细）
INSERT INTO db_sync_task (
    proxy_source, source_table, target_database, target_table, target_table_describe,
    sync_mode, fetch_config, transform_config, status, remark
) VALUES (
    'tushare', 'top_list', 'stock_data', 'ods_top_list_di', '龙虎榜每日明细', 'snapshot',
    JSON_OBJECT(
        'token_type', 'tushare',
        'params', JSON_OBJECT('trade_date', '$trade_date'),
        'inject_date_range', FALSE
    ),
    JSON_OBJECT(
        'date_columns', JSON_OBJECT('trade_date', '%Y%m%d'),
        'snapshot_delete_column', 'trade_date',
        'dedupe', JSON_ARRAY('trade_date', 'ts_code', 'reason'),
        'dropna', JSON_ARRAY('trade_date', 'ts_code'),
        'keep_columns', JSON_ARRAY(
            'trade_date', 'ts_code', 'name', 'close', 'pct_change', 'turnover_rate',
            'amount', 'l_sell', 'l_buy', 'l_amount', 'net_amount', 'net_rate',
            'amount_rate', 'float_values', 'reason'
        )
    ),
    1, '龙虎榜日快照(Tushare top_list, trade_date=$trade_date；单次最多1万行，约2000积分，建议20点后)'
);

-- Tushare moneyflow_hsgt → ods_moneyflow_hsgt_di（按日 snapshot，沪深港通通道资金流向）
INSERT INTO db_sync_task (
    proxy_source, source_table, target_database, target_table, target_table_describe,
    sync_mode, fetch_config, transform_config, status, remark
) VALUES (
    'tushare', 'moneyflow_hsgt', 'stock_data', 'ods_moneyflow_hsgt_di', '沪深港通资金流向', 'snapshot',
    JSON_OBJECT(
        'token_type', 'tushare',
        'params', JSON_OBJECT('trade_date', '$trade_date'),
        'inject_date_range', FALSE
    ),
    JSON_OBJECT(
        'date_columns', JSON_OBJECT('trade_date', '%Y%m%d'),
        'snapshot_delete_column', 'trade_date',
        'dedupe', JSON_ARRAY('trade_date'),
        'dropna', JSON_ARRAY('trade_date'),
        'keep_columns', JSON_ARRAY(
            'trade_date', 'ggt_ss', 'ggt_sz', 'hgt', 'sgt', 'north_money', 'south_money'
        )
    ),
    1, '沪深港通资金流向日快照(Tushare moneyflow_hsgt；含北向/南向汇总，约2000积分)'
);

-- Tushare hk_hold → ods_hk_hold_di（按日 snapshot，沪股通+深股通分两次拉取避免3800行截断）
INSERT INTO db_sync_task (
    proxy_source, source_table, target_database, target_table, target_table_describe,
    sync_mode, fetch_config, transform_config, status, remark
) VALUES (
    'tushare', 'hk_hold', 'stock_data', 'ods_hk_hold_di', '沪深港股通持股明细', 'snapshot',
    JSON_OBJECT(
        'token_type', 'tushare',
        'params', JSON_OBJECT('trade_date', '$trade_date'),
        'calls', JSON_ARRAY(
            JSON_OBJECT('params', JSON_OBJECT('exchange', 'SH')),
            JSON_OBJECT('params', JSON_OBJECT('exchange', 'SZ'))
        ),
        'sleep_seconds', 0.2,
        'inject_date_range', FALSE
    ),
    JSON_OBJECT(
        'date_columns', JSON_OBJECT('trade_date', '%Y%m%d'),
        'snapshot_delete_column', 'trade_date',
        'dedupe', JSON_ARRAY('trade_date', 'ts_code', 'exchange'),
        'dropna', JSON_ARRAY('trade_date', 'ts_code', 'exchange'),
        'keep_columns', JSON_ARRAY(
            'trade_date', 'code', 'ts_code', 'name', 'vol', 'ratio', 'exchange'
        )
    ),
    1, '沪深港股通持股日快照(Tushare hk_hold, SH+SZ北向；单次最多3800行/通道，约2000积分，T+1更新)'
);

-- 存量库迁移：fina_mainbz_vip 由 daily 改为 monthly（与日批 fina_mainbz 一并由 xxl_monthly_batch.sh 执行）
UPDATE db_sync_task
SET schedule_type = 'monthly',
    remark = '主营业务构成VIP(Tushare fina_mainbz_vip,type=P)；snapshot=近2季全市场；monthly+月批 --force（单次约1万行上限，需配合 fina_mainbz 按股补全）'
WHERE source_table = 'fina_mainbz_vip';

-- ============================================================================
-- P0：财务报表 / 业绩预告快报
-- ============================================================================

-- Tushare income_vip → ods_income_di（利润表；monthly 近2季）
INSERT INTO db_sync_task (
    proxy_source, source_table, target_database, target_table, target_table_describe,
    sync_mode, schedule_type, fetch_config, transform_config, status, remark
) VALUES (
    'tushare', 'income_vip', 'stock_data', 'ods_income_di', '利润表', 'snapshot', 'monthly',
    JSON_OBJECT(
        'token_type', 'tushare',
        'params', JSON_OBJECT(
            'fields', 'ts_code,ann_date,f_ann_date,end_date,report_type,comp_type,end_type,basic_eps,diluted_eps,total_revenue,revenue,oper_cost,sell_exp,admin_exp,fin_exp,rd_exp,operate_profit,total_profit,n_income,n_income_attr_p,minority_gain,ebit,ebitda,update_flag'
        ),
        'full_start', '20180101',
        'snapshot_periods', 2,
        'sleep_seconds', 0.5,
        'inject_date_range', FALSE
    ),
    JSON_OBJECT(
        'date_columns', JSON_OBJECT('ann_date', '%Y%m%d', 'f_ann_date', '%Y%m%d', 'end_date', '%Y%m%d'),
        'dedupe', JSON_ARRAY('ts_code', 'end_date', 'report_type', 'ann_date'),
        'dropna', JSON_ARRAY('ts_code', 'end_date'),
        'keep_columns', JSON_ARRAY(
            'ts_code', 'ann_date', 'f_ann_date', 'end_date', 'report_type', 'comp_type', 'end_type',
            'basic_eps', 'diluted_eps', 'total_revenue', 'revenue', 'oper_cost',
            'sell_exp', 'admin_exp', 'fin_exp', 'rd_exp',
            'operate_profit', 'total_profit', 'n_income', 'n_income_attr_p', 'minority_gain',
            'ebit', 'ebitda', 'update_flag'
        )
    ),
    1, '利润表VIP(Tushare income_vip)；snapshot=近2季全市场；约5000积分；月批 --force'
);

-- Tushare cashflow_vip → ods_cashflow_di（现金流量表；含 CapEx）
INSERT INTO db_sync_task (
    proxy_source, source_table, target_database, target_table, target_table_describe,
    sync_mode, schedule_type, fetch_config, transform_config, status, remark
) VALUES (
    'tushare', 'cashflow_vip', 'stock_data', 'ods_cashflow_di', '现金流量表', 'snapshot', 'monthly',
    JSON_OBJECT(
        'token_type', 'tushare',
        'params', JSON_OBJECT(
            'fields', 'ts_code,ann_date,f_ann_date,end_date,report_type,comp_type,end_type,net_profit,n_cashflow_act,n_cashflow_inv_act,n_cash_flows_fnc_act,c_pay_acq_const_fiolta,free_cashflow,n_incr_cash_cash_equ,c_cash_equ_end_period,update_flag'
        ),
        'full_start', '20180101',
        'snapshot_periods', 2,
        'sleep_seconds', 0.5,
        'inject_date_range', FALSE
    ),
    JSON_OBJECT(
        'date_columns', JSON_OBJECT('ann_date', '%Y%m%d', 'f_ann_date', '%Y%m%d', 'end_date', '%Y%m%d'),
        'dedupe', JSON_ARRAY('ts_code', 'end_date', 'report_type', 'ann_date'),
        'dropna', JSON_ARRAY('ts_code', 'end_date'),
        'keep_columns', JSON_ARRAY(
            'ts_code', 'ann_date', 'f_ann_date', 'end_date', 'report_type', 'comp_type', 'end_type',
            'net_profit', 'n_cashflow_act', 'n_cashflow_inv_act', 'n_cash_flows_fnc_act',
            'c_pay_acq_const_fiolta', 'free_cashflow', 'n_incr_cash_cash_equ',
            'c_cash_equ_end_period', 'update_flag'
        )
    ),
    1, '现金流量表VIP(Tushare cashflow_vip)；含CapEx；snapshot=近2季；约5000积分；月批 --force'
);

-- Tushare balancesheet_vip → ods_balancesheet_di
INSERT INTO db_sync_task (
    proxy_source, source_table, target_database, target_table, target_table_describe,
    sync_mode, schedule_type, fetch_config, transform_config, status, remark
) VALUES (
    'tushare', 'balancesheet_vip', 'stock_data', 'ods_balancesheet_di', '资产负债表', 'snapshot', 'monthly',
    JSON_OBJECT(
        'token_type', 'tushare',
        'params', JSON_OBJECT(
            'fields', 'ts_code,ann_date,f_ann_date,end_date,report_type,comp_type,end_type,total_share,money_cap,accounts_receiv,inventories,total_cur_assets,fix_assets,cip,intan_assets,goodwill,total_assets,st_borr,lt_borr,total_cur_liab,total_liab,total_hldr_eqy_exc_min_int,total_hldr_eqy_inc_min_int,update_flag'
        ),
        'full_start', '20180101',
        'snapshot_periods', 2,
        'sleep_seconds', 0.5,
        'inject_date_range', FALSE
    ),
    JSON_OBJECT(
        'date_columns', JSON_OBJECT('ann_date', '%Y%m%d', 'f_ann_date', '%Y%m%d', 'end_date', '%Y%m%d'),
        'dedupe', JSON_ARRAY('ts_code', 'end_date', 'report_type', 'ann_date'),
        'dropna', JSON_ARRAY('ts_code', 'end_date'),
        'keep_columns', JSON_ARRAY(
            'ts_code', 'ann_date', 'f_ann_date', 'end_date', 'report_type', 'comp_type', 'end_type',
            'total_share', 'money_cap', 'accounts_receiv', 'inventories', 'total_cur_assets',
            'fix_assets', 'cip', 'intan_assets', 'goodwill', 'total_assets',
            'st_borr', 'lt_borr', 'total_cur_liab', 'total_liab',
            'total_hldr_eqy_exc_min_int', 'total_hldr_eqy_inc_min_int', 'update_flag'
        )
    ),
    1, '资产负债表VIP(Tushare balancesheet_vip)；snapshot=近2季；约5000积分；月批 --force'
);

-- Tushare forecast_vip → ods_forecast_di（业绩预告；type 字段映射为 forecast_type）
INSERT INTO db_sync_task (
    proxy_source, source_table, target_database, target_table, target_table_describe,
    sync_mode, schedule_type, fetch_config, transform_config, status, remark
) VALUES (
    'tushare', 'forecast_vip', 'stock_data', 'ods_forecast_di', '业绩预告', 'snapshot', 'monthly',
    JSON_OBJECT(
        'token_type', 'tushare',
        'params', JSON_OBJECT(
            'fields', 'ts_code,ann_date,end_date,type,p_change_min,p_change_max,net_profit_min,net_profit_max,last_parent_net,first_ann_date,summary,change_reason'
        ),
        'full_start', '20180101',
        'snapshot_periods', 2,
        'sleep_seconds', 0.5,
        'inject_date_range', FALSE
    ),
    JSON_OBJECT(
        'rename', JSON_OBJECT('type', 'forecast_type'),
        'date_columns', JSON_OBJECT('ann_date', '%Y%m%d', 'end_date', '%Y%m%d', 'first_ann_date', '%Y%m%d'),
        'dedupe', JSON_ARRAY('ts_code', 'ann_date', 'end_date', 'forecast_type'),
        'dropna', JSON_ARRAY('ts_code', 'ann_date', 'end_date'),
        'keep_columns', JSON_ARRAY(
            'ts_code', 'ann_date', 'end_date', 'forecast_type',
            'p_change_min', 'p_change_max', 'net_profit_min', 'net_profit_max',
            'last_parent_net', 'first_ann_date', 'summary', 'change_reason'
        )
    ),
    1, '业绩预告VIP(Tushare forecast_vip)；snapshot=近2季；约5000积分；月批 --force'
);

-- Tushare express_vip → ods_express_di（业绩快报）
INSERT INTO db_sync_task (
    proxy_source, source_table, target_database, target_table, target_table_describe,
    sync_mode, schedule_type, fetch_config, transform_config, status, remark
) VALUES (
    'tushare', 'express_vip', 'stock_data', 'ods_express_di', '业绩快报', 'snapshot', 'monthly',
    JSON_OBJECT(
        'token_type', 'tushare',
        'params', JSON_OBJECT(
            'fields', 'ts_code,ann_date,end_date,revenue,operate_profit,total_profit,n_income,total_assets,total_hldr_eqy_exc_min_int,diluted_eps,diluted_roe,yoy_net_profit,bps,yoy_sales,yoy_op,yoy_tp,yoy_dedu_np,perf_summary,is_audit,remark'
        ),
        'full_start', '20180101',
        'snapshot_periods', 2,
        'sleep_seconds', 0.5,
        'inject_date_range', FALSE
    ),
    JSON_OBJECT(
        'date_columns', JSON_OBJECT('ann_date', '%Y%m%d', 'end_date', '%Y%m%d'),
        'dedupe', JSON_ARRAY('ts_code', 'ann_date', 'end_date'),
        'dropna', JSON_ARRAY('ts_code', 'ann_date', 'end_date'),
        'keep_columns', JSON_ARRAY(
            'ts_code', 'ann_date', 'end_date',
            'revenue', 'operate_profit', 'total_profit', 'n_income', 'total_assets',
            'total_hldr_eqy_exc_min_int', 'diluted_eps', 'diluted_roe', 'yoy_net_profit',
            'bps', 'yoy_sales', 'yoy_op', 'yoy_tp', 'yoy_dedu_np',
            'perf_summary', 'is_audit', 'remark'
        )
    ),
    1, '业绩快报VIP(Tushare express_vip)；snapshot=近2季；约5000积分；月批 --force'
);

-- ============================================================================
-- P1：交易侧增强（日快照）
-- ============================================================================

-- Tushare top_inst → ods_top_inst_di（龙虎榜机构明细）
INSERT INTO db_sync_task (
    proxy_source, source_table, target_database, target_table, target_table_describe,
    sync_mode, fetch_config, transform_config, status, remark
) VALUES (
    'tushare', 'top_inst', 'stock_data', 'ods_top_inst_di', '龙虎榜机构明细', 'snapshot',
    JSON_OBJECT(
        'token_type', 'tushare',
        'params', JSON_OBJECT('trade_date', '$trade_date'),
        'inject_date_range', FALSE
    ),
    JSON_OBJECT(
        'date_columns', JSON_OBJECT('trade_date', '%Y%m%d'),
        'snapshot_delete_column', 'trade_date',
        'dedupe', JSON_ARRAY('trade_date', 'ts_code', 'exalter', 'side', 'reason'),
        'dropna', JSON_ARRAY('trade_date', 'ts_code'),
        'keep_columns', JSON_ARRAY(
            'trade_date', 'ts_code', 'exalter', 'side',
            'buy', 'buy_rate', 'sell', 'sell_rate', 'net_buy', 'reason'
        )
    ),
    1, '龙虎榜机构明细日快照(Tushare top_inst；约5000积分，建议20点后)'
);

-- Tushare margin → ods_margin_di（融资融券汇总，按交易所）
INSERT INTO db_sync_task (
    proxy_source, source_table, target_database, target_table, target_table_describe,
    sync_mode, fetch_config, transform_config, status, remark
) VALUES (
    'tushare', 'margin', 'stock_data', 'ods_margin_di', '融资融券交易汇总', 'snapshot',
    JSON_OBJECT(
        'token_type', 'tushare',
        'params', JSON_OBJECT('trade_date', '$trade_date'),
        'inject_date_range', FALSE
    ),
    JSON_OBJECT(
        'date_columns', JSON_OBJECT('trade_date', '%Y%m%d'),
        'snapshot_delete_column', 'trade_date',
        'dedupe', JSON_ARRAY('trade_date', 'exchange_id'),
        'dropna', JSON_ARRAY('trade_date', 'exchange_id'),
        'keep_columns', JSON_ARRAY(
            'trade_date', 'exchange_id',
            'rzye', 'rzmre', 'rzche', 'rqye', 'rqmcl', 'rqyl', 'rzrqye'
        )
    ),
    1, '融资融券交易汇总日快照(Tushare margin；交易所合计，约2000积分)'
);

-- Tushare margin_detail → ods_margin_detail_di（融资融券个股明细）
INSERT INTO db_sync_task (
    proxy_source, source_table, target_database, target_table, target_table_describe,
    sync_mode, fetch_config, transform_config, status, remark
) VALUES (
    'tushare', 'margin_detail', 'stock_data', 'ods_margin_detail_di', '融资融券交易明细', 'snapshot',
    JSON_OBJECT(
        'token_type', 'tushare',
        'params', JSON_OBJECT('trade_date', '$trade_date'),
        'inject_date_range', FALSE
    ),
    JSON_OBJECT(
        'date_columns', JSON_OBJECT('trade_date', '%Y%m%d'),
        'snapshot_delete_column', 'trade_date',
        'dedupe', JSON_ARRAY('trade_date', 'ts_code'),
        'dropna', JSON_ARRAY('trade_date', 'ts_code'),
        'keep_columns', JSON_ARRAY(
            'trade_date', 'ts_code', 'name',
            'rzye', 'rqye', 'rzmre', 'rqyl', 'rzche', 'rqchl', 'rqmcl', 'rzrqye'
        )
    ),
    1, '融资融券个股明细日快照(Tushare margin_detail；单次最多6000行，约2000积分)'
);

-- Tushare stk_holdertrade → ods_stk_holdertrade_di（股东增减持，按公告日）
INSERT INTO db_sync_task (
    proxy_source, source_table, target_database, target_table, target_table_describe,
    sync_mode, fetch_config, transform_config, status, remark
) VALUES (
    'tushare', 'stk_holdertrade', 'stock_data', 'ods_stk_holdertrade_di', '股东增减持', 'snapshot',
    JSON_OBJECT(
        'token_type', 'tushare',
        'params', JSON_OBJECT('ann_date', '$trade_date'),
        'inject_date_range', FALSE
    ),
    JSON_OBJECT(
        'date_columns', JSON_OBJECT(
            'ann_date', '%Y%m%d', 'begin_date', '%Y%m%d', 'close_date', '%Y%m%d'
        ),
        'snapshot_delete_column', 'ann_date',
        'dedupe', JSON_ARRAY('ts_code', 'ann_date', 'holder_name', 'in_de'),
        'dropna', JSON_ARRAY('ts_code', 'ann_date', 'holder_name'),
        'keep_columns', JSON_ARRAY(
            'ts_code', 'ann_date', 'holder_name', 'holder_type', 'in_de',
            'change_vol', 'change_ratio', 'after_share', 'after_ratio',
            'avg_price', 'total_share', 'begin_date', 'close_date'
        )
    ),
    1, '股东增减持日快照(Tushare stk_holdertrade,ann_date=$trade_date；约2000积分)'
);

-- Tushare stk_holdernumber → ods_stk_holdernumber_di（股东人数，按公告日）
INSERT INTO db_sync_task (
    proxy_source, source_table, target_database, target_table, target_table_describe,
    sync_mode, fetch_config, transform_config, status, remark
) VALUES (
    'tushare', 'stk_holdernumber', 'stock_data', 'ods_stk_holdernumber_di', '股东人数', 'snapshot',
    JSON_OBJECT(
        'token_type', 'tushare',
        'params', JSON_OBJECT('ann_date', '$trade_date'),
        'inject_date_range', FALSE
    ),
    JSON_OBJECT(
        'date_columns', JSON_OBJECT('ann_date', '%Y%m%d', 'end_date', '%Y%m%d'),
        'snapshot_delete_column', 'ann_date',
        'dedupe', JSON_ARRAY('ts_code', 'ann_date', 'end_date'),
        'dropna', JSON_ARRAY('ts_code', 'ann_date', 'end_date'),
        'keep_columns', JSON_ARRAY('ts_code', 'ann_date', 'end_date', 'holder_num')
    ),
    1, '股东人数日快照(Tushare stk_holdernumber,ann_date=$trade_date；不定期披露，空日正常)'
);

-- Tushare adj_factor → ods_adj_factor_di（复权因子）
INSERT INTO db_sync_task (
    proxy_source, source_table, target_database, target_table, target_table_describe,
    sync_mode, fetch_config, transform_config, status, remark
) VALUES (
    'tushare', 'adj_factor', 'stock_data', 'ods_adj_factor_di', '复权因子', 'snapshot',
    JSON_OBJECT(
        'token_type', 'tushare',
        'params', JSON_OBJECT('trade_date', '$trade_date'),
        'inject_date_range', FALSE
    ),
    JSON_OBJECT(
        'date_columns', JSON_OBJECT('trade_date', '%Y%m%d'),
        'snapshot_delete_column', 'trade_date',
        'dedupe', JSON_ARRAY('ts_code', 'trade_date'),
        'dropna', JSON_ARRAY('ts_code', 'trade_date'),
        'keep_columns', JSON_ARRAY('ts_code', 'trade_date', 'adj_factor')
    ),
    1, '复权因子日快照(Tushare adj_factor；约2000积分，盘前更新)'
);

-- Tushare stk_limit → ods_stk_limit_di（每日涨跌停价格）
INSERT INTO db_sync_task (
    proxy_source, source_table, target_database, target_table, target_table_describe,
    sync_mode, fetch_config, transform_config, status, remark
) VALUES (
    'tushare', 'stk_limit', 'stock_data', 'ods_stk_limit_di', '每日涨跌停价格', 'snapshot',
    JSON_OBJECT(
        'token_type', 'tushare',
        'params', JSON_OBJECT('trade_date', '$trade_date'),
        'inject_date_range', FALSE
    ),
    JSON_OBJECT(
        'date_columns', JSON_OBJECT('trade_date', '%Y%m%d'),
        'snapshot_delete_column', 'trade_date',
        'dedupe', JSON_ARRAY('trade_date', 'ts_code'),
        'dropna', JSON_ARRAY('trade_date', 'ts_code'),
        'keep_columns', JSON_ARRAY('trade_date', 'ts_code', 'pre_close', 'up_limit', 'down_limit')
    ),
    1, '每日涨跌停价格日快照(Tushare stk_limit；约2000积分，盘前更新)'
);

-- 存量清理：取消 fund_portfolio 同步（不再维护 ods_fund_hold_di）
DELETE FROM db_sync_task WHERE source_table = 'fund_portfolio';
-- 若表已创建，可在 stock_data 库执行：DROP TABLE IF EXISTS ods_fund_hold_di;
