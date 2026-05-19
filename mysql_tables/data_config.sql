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
    id                BIGINT PRIMARY KEY AUTO_INCREMENT,
    task_code         VARCHAR(64)  NOT NULL COMMENT '任务编码，全局唯一',
    task_name         VARCHAR(128) NOT NULL COMMENT '任务名称',
    source_channel    VARCHAR(32)  NOT NULL COMMENT '数据源渠道：akshare / tushare / internal',
    target_database   VARCHAR(64)  NOT NULL DEFAULT 'stock_data' COMMENT '目标库',
    target_table      VARCHAR(128) NOT NULL COMMENT '目标物理表',
    sync_mode         VARCHAR(16)  NOT NULL DEFAULT 'snapshot'
        COMMENT 'snapshot=日快照 full=全量 incremental=增量 derivative=衍生计算',
    script_key        VARCHAR(64)  NOT NULL COMMENT 'Python 注册键，见 sync/task_registry.py',
    script_args       JSON         NULL COMMENT '传给脚本的默认参数 JSON',
    depends_on        VARCHAR(512) NULL COMMENT '前置任务 task_code，逗号分隔',
    sort_order        INT          NOT NULL DEFAULT 100 COMMENT '执行顺序，越小越先',
    status            TINYINT      NOT NULL DEFAULT 1 COMMENT '1=启用 0=停用',
    owner             VARCHAR(64)  NULL,
    remark            VARCHAR(512) NULL,
    last_sync_time    DATETIME     NULL,
    last_sync_status  VARCHAR(16)  NULL COMMENT 'success / failed / running',
    last_error_msg    TEXT         NULL,
    created_at        DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at        DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_task_code (task_code),
    KEY idx_status_sort (status, sort_order)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='数据源→MySQL 同步任务配置表';

-- ---------------------------------------------------------------------------
-- 同步执行日志（按批次 run_id 追溯）
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS db_sync_log (
    id           BIGINT PRIMARY KEY AUTO_INCREMENT,
    run_id       VARCHAR(32)  NOT NULL COMMENT '批次号 YYYYMMDD_HHMMSS_随机',
    task_code    VARCHAR(64)  NOT NULL,
    trade_date   DATE         NULL COMMENT '业务日期（若任务支持）',
    status       VARCHAR(16)  NOT NULL COMMENT 'success / failed / skipped',
    rows_affected INT         NULL,
    started_at   DATETIME     NOT NULL,
    finished_at  DATETIME     NULL,
    error_msg    TEXT         NULL,
    KEY idx_run (run_id),
    KEY idx_task_time (task_code, started_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='同步任务执行日志';

-- ---------------------------------------------------------------------------
-- 初始任务清单（当前仅启用 trading_day_di、stock_fund_flow_di）
-- ---------------------------------------------------------------------------
INSERT INTO db_sync_task
    (task_code, task_name, source_channel, target_database, target_table,
     sync_mode, script_key, script_args, depends_on, sort_order, status, remark)
VALUES
    ('trading_day', '交易日维度', 'internal', 'stock_data', 'trading_day_di',
     'full', 'trading_day', '{"start_year":2020,"end_year":2026}',
     NULL, 10, 1, '无外部 API，生成交易日历'),

    ('stock_fund_flow', '个股资金流', 'akshare', 'stock_data', 'stock_fund_flow_di',
     'snapshot', 'stock_fund_flow',
     '{"periods":["即时"]}',
     'trading_day', 20, 1, NULL)
ON DUPLICATE KEY UPDATE
    task_name       = VALUES(task_name),
    source_channel  = VALUES(source_channel),
    target_database = VALUES(target_database),
    target_table    = VALUES(target_table),
    sync_mode       = VALUES(sync_mode),
    script_key      = VALUES(script_key),
    script_args     = VALUES(script_args),
    depends_on      = VALUES(depends_on),
    sort_order      = VALUES(sort_order),
    remark          = VALUES(remark);

-- ---------------------------------------------------------------------------
-- 迁移：移除 db_sync_task 中已废弃的调度字段（改由 xxl-job 管理）
-- ---------------------------------------------------------------------------
SET @col_exists := (
    SELECT COUNT(*)
    FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'db_sync_task'
      AND COLUMN_NAME = 'cron_hint'
);
SET @drop_sql := IF(
    @col_exists > 0,
    'ALTER TABLE db_sync_task DROP COLUMN cron_hint',
    'SELECT 1'
);
PREPARE _stmt FROM @drop_sql;
EXECUTE _stmt;
DEALLOCATE PREPARE _stmt;
