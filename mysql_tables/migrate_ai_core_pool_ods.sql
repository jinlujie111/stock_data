-- ============================================================================
-- 需求4 AI核心池：ods_stock_company_di + ods_fina_mainbz_di + db_sync_task
-- 用法（服务器）:
--   mysql -u root -p stock_data < mysql_tables/migrate_ai_core_pool_ods.sql
--   mysql -u root -p data_config < mysql_tables/migrate_ai_core_pool_ods.sql
-- 或整文件一次执行（含 USE 切换）:
--   mysql -u root -p < mysql_tables/migrate_ai_core_pool_ods.sql
-- ============================================================================

USE stock_data;

CREATE TABLE IF NOT EXISTS ods_stock_company_di (
    id              BIGINT PRIMARY KEY AUTO_INCREMENT,
    ts_code         VARCHAR(16)    NOT NULL COMMENT 'TS代码',
    exchange        VARCHAR(8)     NULL COMMENT '交易所 SSE/SZSE/BSE',
    chairman        VARCHAR(64)    NULL COMMENT '法人代表/董事长',
    manager         VARCHAR(64)    NULL COMMENT '总经理',
    secretary       VARCHAR(64)    NULL COMMENT '董秘',
    reg_capital     DECIMAL(20, 4) NULL COMMENT '注册资本(万元)',
    setup_date      DATE           NULL COMMENT '成立日期',
    province        VARCHAR(32)    NULL COMMENT '省份',
    city            VARCHAR(32)    NULL COMMENT '城市',
    introduction    TEXT           NULL COMMENT '公司简介',
    website         VARCHAR(256)   NULL COMMENT '公司网站',
    employees       INT            NULL COMMENT '员工人数',
    main_business   TEXT           NULL COMMENT '主营业务',
    business_scope  TEXT           NULL COMMENT '经营范围',
    created_at      DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_stock_company (ts_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='上市公司基本信息(Tushare stock_company)';

CREATE TABLE IF NOT EXISTS ods_fina_mainbz_di (
    id          BIGINT PRIMARY KEY AUTO_INCREMENT,
    ts_code     VARCHAR(16)    NOT NULL COMMENT 'TS代码',
    end_date    DATE           NOT NULL COMMENT '报告期',
    bz_type     CHAR(1)        NOT NULL DEFAULT 'P' COMMENT 'P产品 D地区 I行业',
    bz_item     VARCHAR(256)   NULL COMMENT '主营业务项目',
    bz_code     VARCHAR(16)    NULL COMMENT '主营业务来源类型代码',
    bz_sales    DECIMAL(24, 4) NULL COMMENT '主营业务收入(元)',
    bz_profit   DECIMAL(24, 4) NULL COMMENT '主营业务利润(元)',
    bz_cost     DECIMAL(24, 4) NULL COMMENT '主营业务成本(元)',
    curr_type   VARCHAR(8)     NULL COMMENT '货币代码',
    update_flag VARCHAR(8)     NULL COMMENT '是否更新',
    created_at  DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at  DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_fina_mainbz (ts_code, end_date, bz_type, bz_item(128))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='主营业务构成(Tushare fina_mainbz_vip,按产品)';

USE data_config;

-- 若旧库无 schedule_type 列则补上（幂等）
SET @col_exists := (
    SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = 'data_config' AND TABLE_NAME = 'db_sync_task' AND COLUMN_NAME = 'schedule_type'
);
SET @ddl := IF(
    @col_exists = 0,
    'ALTER TABLE db_sync_task ADD COLUMN schedule_type VARCHAR(16) NOT NULL DEFAULT ''daily'' COMMENT ''daily/monthly'' AFTER sync_mode',
    'SELECT 1'
);
PREPARE stmt FROM @ddl;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

INSERT INTO db_sync_task (
    proxy_source, source_table, target_database, target_table, target_table_describe,
    sync_mode, schedule_type, fetch_config, transform_config, status, remark
)
SELECT
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
FROM DUAL
WHERE NOT EXISTS (
    SELECT 1 FROM db_sync_task
    WHERE source_table = 'stock_company' AND target_table = 'ods_stock_company_di'
);

INSERT INTO db_sync_task (
    proxy_source, source_table, target_database, target_table, target_table_describe,
    sync_mode, schedule_type, fetch_config, transform_config, status, remark
)
SELECT
    'tushare', 'fina_mainbz_vip', 'stock_data', 'ods_fina_mainbz_di', '主营业务构成(按产品)', 'snapshot', 'daily',
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
    1, '主营业务构成VIP(Tushare fina_mainbz_vip,type=P)；snapshot=近2个报告期全市场，full=按季period回溯(需约5000积分)'
FROM DUAL
WHERE NOT EXISTS (
    SELECT 1 FROM db_sync_task
    WHERE source_table = 'fina_mainbz_vip' AND target_table = 'ods_fina_mainbz_di'
);

SELECT id, source_table, target_table, sync_mode, schedule_type, status
FROM db_sync_task
WHERE source_table IN ('stock_company', 'fina_mainbz_vip')
ORDER BY id;
