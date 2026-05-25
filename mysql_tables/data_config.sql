-- ============================================================================
-- data_config 库：数据源凭证 + 同步任务配置
-- 用法：source dw/utils/func.sh && init_data_config_schema
-- 同步：source dw/utils/func.sh && run_data_sync [YYYYMMDD] [--task-code xxx]
-- 调度：由 xxl-job 管理，见 mysql_tables/xxl_job_stock_sync.sql
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
    status        TINYINT      NOT NULL DEFAULT 1 COMMENT '1=有效 0=无效',
    remark        VARCHAR(256) NULL,
    created_at    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_token_type (token_type,status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='数据源 Token 配置表';

INSERT INTO db_token (token_type, token_id, status, remark)
VALUES ('tushare', '0ced3a73b7055fc7e38a2a7665db0fa371b51518e838dfce9fba5ae5', 1, '默认 Tushare Pro')
ON DUPLICATE KEY UPDATE
    token_id = VALUES(token_id),
    status   = VALUES(status),
    remark   = VALUES(remark);

-- ---------------------------------------------------------------------------
-- 同步任务配置主表（一条记录 = 一个「数据源 → MySQL 表」任务）
-- script_key 与 sync/task_registry.py 中注册项一一对应，禁止随意改名
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
    ('','trading_day', '交易日维度', 'internal', 'stock_data', 'trading_day_di',
     'full', 'trading_day', '{"start_year":2020,"end_year":2026}',
     NULL, 10, 1, '无外部 API，生成交易日历'),
    ('stock_fund_flow', '个股资金流', 'akshare', 'stock_data', 'stock_fund_flow_di',
     'snapshot', 'stock_fund_flow',
     '{"periods":["即时"]}',
     'trading_day', 20, 1, NULL)


