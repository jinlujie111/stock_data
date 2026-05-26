-- ============================================================================
-- data_config 库：数据源凭证 + 同步任务配置
-- 用法：source dw/utils/func.sh && init_data_config_schema
-- 同步：source dw/utils/func.sh && run_data_sync [YYYYMMDD] [--task-code xxx]
-- 定时触发：系统 crontab 调用 dw-utils/func.sh run_data_sync，见 调度执行流程.md
-- ============================================================================

CREATE DATABASE IF NOT EXISTS data_config DEFAULT CHARSET utf8mb4;
USE data_config;

-- ---------------------------------------------------------------------------
-- 数据源 Token（tushare / 其他 API 密钥）
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS db_token (
    id            BIGINT PRIMARY KEY AUTO_INCREMENT,
    token_type    VARCHAR(32)  NOT NULL COMMENT '数据来源：tushare / akshare 等',
    token_id      VARCHAR(256) NOT NULL COMMENT 'token 或密钥',
    api_url       VARCHAR(256) NULL COMMENT 'Tushare 代理 API 根地址，如 http://a.sszhixia.cn/',
    status        TINYINT      NOT NULL DEFAULT 1 COMMENT '1=有效 0=无效',
    remark        VARCHAR(256) NULL,
    created_at    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    start_date    DATETIME     NULL COMMENT 'token 生效开始',
    end_date      DATETIME     NULL COMMENT 'token 失效时间',
    UNIQUE KEY uk_token_type (token_type, status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='数据源 Token 配置表';

INSERT INTO db_token (token_type, token_id, api_url, status, remark, start_date, end_date)
VALUES (
    'tushare',
    '0ced3a73b7055fc7e38a2a7665db0fa371b51518e838dfce9fba5ae5',
    NULL,
    0,
    '历史 Tushare Pro',
    '1999-01-01',
    '2999-12-31'
);

INSERT INTO db_token (token_type, token_id, api_url, status, remark, start_date, end_date)
VALUES (
    'tushare',
    'kOxsKJfSHCAsIrePsxWkfUdGIbMhfLWyTEfPSdueqnzMsqGigIeIaprTDglfSstX',
    'http://a.sszhixia.cn/',
    1,
    '当前 Tushare Pro（代理）',
    '1999-01-01',
    '2026-11-22'
);

-- ---------------------------------------------------------------------------
-- 同步任务配置主表（一条记录 = 一个「数据源 → MySQL 表」任务）
-- proxy_source + source_table 与 dw-sync/task_registry.py 注册项对应
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS db_sync_task (
    id                BIGINT       PRIMARY KEY AUTO_INCREMENT,
    proxy_source      VARCHAR(32)  NOT NULL COMMENT '数据源渠道：akshare / tushare / internal / mootdx/',
    source_table      VARCHAR(32)  NOT NULL COMMENT '接口代码',
    target_database   VARCHAR(64)  NOT NULL DEFAULT 'stock_data' COMMENT '目标库',
    target_table      VARCHAR(128) NOT NULL COMMENT '目标物理表',
    target_table_describe      VARCHAR(128) NOT NULL COMMENT '目标物理表描述',
    sync_mode         VARCHAR(16)  NOT NULL DEFAULT 'snapshot' COMMENT 'snapshot=日快照 full=全量 incremental=增量 derivative=衍生计算',
    status            TINYINT      NOT NULL DEFAULT 1 COMMENT '1=启用 0=停用',
    remark            VARCHAR(512) NULL,
    created_at        DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at        DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='数据源→MySQL 同步任务配置表';

-- ---------------------------------------------------------------------------
-- 初始任务清单（当前仅启用 trading_day_di、stock_fund_flow_di）
-- ---------------------------------------------------------------------------
INSERT INTO db_sync_task
    (proxy_source,source_table,target_database,target_table,target_table_describe,sync_mode,status,remark)
VALUES
    ('akshare','tool_trade_date_hist_sina','stock_data','ods_trading_day','交易日','full',1,'全量更新交易日数据')

INSERT INTO db_sync_task
    (proxy_source,source_table,target_database,target_table,target_table_describe,sync_mode,status,remark)
VALUES
    ('tushare','trade_cal','stock_data','ods_trading_day_di','交易日','incremental',1,'默认更新今天数据');

-- 已有库升级（按需执行）：
-- ALTER TABLE db_token ADD COLUMN api_url VARCHAR(256) NULL COMMENT 'Tushare 代理 API' AFTER token_id;
-- UPDATE db_token SET api_url='http://a.sszhixia.cn/' WHERE token_type='tushare' AND status=1;

