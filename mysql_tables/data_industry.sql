-- ============================================================================
-- data_industry：行业资金流网站等业务数据（与 stock_data 股票库分离）
-- 首次：root 执行 mysql_tables/data_industry_grants.sql 建库并授权
-- 建表：source dw-utils/func.sh && init_data_industry_schema
-- ============================================================================

USE data_industry;

CREATE TABLE IF NOT EXISTS app_user (
    id            BIGINT PRIMARY KEY AUTO_INCREMENT,
    username      VARCHAR(64)  NOT NULL COMMENT '登录名',
    email         VARCHAR(128) NULL COMMENT '邮箱',
    password_hash VARCHAR(255) NOT NULL COMMENT 'bcrypt 哈希',
    status        TINYINT      NOT NULL DEFAULT 1 COMMENT '1=正常 0=禁用',
    created_at    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_app_user_username (username),
    UNIQUE KEY uk_app_user_email (email)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='行业资金流网站用户';

CREATE TABLE IF NOT EXISTS app_user_board_favorite (
    id            BIGINT PRIMARY KEY AUTO_INCREMENT,
    user_id       BIGINT       NOT NULL COMMENT 'app_user.id',
    industry_code VARCHAR(32)  NOT NULL COMMENT '东财板块代码',
    industry_name VARCHAR(128) NULL COMMENT '板块名称',
    content_type  VARCHAR(16)  NULL COMMENT '行业/概念',
    created_at    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_user_board (user_id, industry_code),
    KEY idx_board_fav_user (user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='用户板块自选';

CREATE TABLE IF NOT EXISTS app_user_stock_favorite (
    id          BIGINT PRIMARY KEY AUTO_INCREMENT,
    user_id     BIGINT       NOT NULL COMMENT 'app_user.id',
    ts_code     VARCHAR(16)  NOT NULL COMMENT '股票TS代码',
    stock_name  VARCHAR(64)  NULL COMMENT '股票简称',
    created_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_user_stock (user_id, ts_code),
    KEY idx_stock_fav_user (user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='用户股票自选';

-- =============================================================================
-- 量化选板块（申万一级轮动）
-- =============================================================================
CREATE TABLE IF NOT EXISTS rotation_strategy (
    id            BIGINT PRIMARY KEY AUTO_INCREMENT,
    code          VARCHAR(64)  NOT NULL COMMENT '策略唯一编码',
    name          VARCHAR(128) NOT NULL COMMENT '策略名称',
    description   VARCHAR(512) NULL COMMENT '策略说明',
    config_json   MEDIUMTEXT   NOT NULL COMMENT '因子/调仓/状态机配置(JSON)',
    is_system     TINYINT      NOT NULL DEFAULT 0 COMMENT '1=系统内置',
    is_active     TINYINT      NOT NULL DEFAULT 1 COMMENT '1=启用(参与每日信号)',
    owner_user_id BIGINT       NULL COMMENT '创建者 app_user.id，NULL=系统',
    created_at    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_rotation_strategy_code (code),
    KEY idx_rotation_strategy_owner (owner_user_id),
    KEY idx_rotation_strategy_active (is_active)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='板块轮动策略定义';

CREATE TABLE IF NOT EXISTS rotation_signal_di (
    id             BIGINT PRIMARY KEY AUTO_INCREMENT,
    strategy_id    BIGINT       NOT NULL COMMENT 'rotation_strategy.id',
    trade_date     DATE         NOT NULL COMMENT '信号交易日',
    ts_code        VARCHAR(32)  NOT NULL COMMENT '申万行业指数代码',
    industry_name  VARCHAR(64)  NULL COMMENT '行业名称',
    action         VARCHAR(8)   NOT NULL COMMENT 'BUY/HOLD/SELL',
    rank_no        INT          NULL COMMENT '当日打分排名(1最优)',
    score          DECIMAL(10,4) NULL COMMENT '综合打分',
    close          DECIMAL(20,4) NULL COMMENT '当日收盘点位',
    factor_json    TEXT         NULL COMMENT '各因子明细+regime(JSON)',
    created_at     DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_rotation_signal (strategy_id, trade_date, ts_code),
    KEY idx_rotation_signal_date (strategy_id, trade_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='每日板块轮动信号';

CREATE TABLE IF NOT EXISTS rotation_backtest_run (
    id             BIGINT PRIMARY KEY AUTO_INCREMENT,
    strategy_id    BIGINT       NOT NULL COMMENT 'rotation_strategy.id',
    owner_user_id  BIGINT       NULL COMMENT '发起者 app_user.id',
    name           VARCHAR(128) NULL COMMENT '回测名称',
    start_date     DATE         NOT NULL,
    end_date       DATE         NOT NULL,
    init_capital   DECIMAL(20,2) NOT NULL DEFAULT 1000000.00,
    params_json    TEXT         NULL COMMENT '回测入参快照(JSON)',
    status         VARCHAR(16)  NOT NULL DEFAULT 'pending' COMMENT 'pending/running/done/failed',
    total_return   DECIMAL(12,4) NULL,
    annual_return  DECIMAL(12,4) NULL,
    max_drawdown   DECIMAL(12,4) NULL,
    sharpe         DECIMAL(12,4) NULL,
    win_rate       DECIMAL(12,4) NULL,
    trade_count    INT          NULL,
    bench_return   DECIMAL(12,4) NULL COMMENT '沪深300区间收益',
    error_msg      VARCHAR(512) NULL,
    created_at     DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finished_at    DATETIME     NULL,
    KEY idx_rot_bt_run_strategy (strategy_id),
    KEY idx_rot_bt_run_owner (owner_user_id, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='板块轮动回测运行记录';

CREATE TABLE IF NOT EXISTS rotation_backtest_trade (
    id           BIGINT PRIMARY KEY AUTO_INCREMENT,
    run_id       BIGINT       NOT NULL COMMENT 'rotation_backtest_run.id',
    ts_code      VARCHAR(32)  NOT NULL,
    stock_name   VARCHAR(64)  NULL COMMENT '行业名称',
    side         VARCHAR(8)   NOT NULL COMMENT 'BUY/SELL',
    trade_date   DATE         NOT NULL,
    price        DECIMAL(20,4) NOT NULL,
    shares       INT          NULL COMMENT '指数模拟可空',
    amount       DECIMAL(20,2) NULL,
    pnl          DECIMAL(20,2) NULL,
    return_pct   DECIMAL(12,4) NULL,
    hold_days    INT          NULL,
    reason       VARCHAR(32)  NULL,
    KEY idx_rot_bt_trade_run (run_id, trade_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='板块轮动回测逐笔交易';

CREATE TABLE IF NOT EXISTS rotation_backtest_nav (
    id             BIGINT PRIMARY KEY AUTO_INCREMENT,
    run_id         BIGINT       NOT NULL COMMENT 'rotation_backtest_run.id',
    trade_date     DATE         NOT NULL,
    nav            DECIMAL(20,6) NOT NULL,
    cash           DECIMAL(20,2) NULL,
    position_value DECIMAL(20,2) NULL,
    bench_nav      DECIMAL(20,6) NULL,
    drawdown       DECIMAL(12,6) NULL,
    UNIQUE KEY uk_rot_bt_nav (run_id, trade_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='板块轮动回测净值曲线';

INSERT IGNORE INTO rotation_strategy (code, name, description, config_json, is_system, is_active, owner_user_id)
VALUES
('sys_sw_auto_flow', '申万·状态机+资金流',
 '申万一级：mom20/60 + 东财行业资金流聚合 + 成交额活跃度；周频 Top5；动量/反转状态机自动切换',
 '{"universe":{"source":"sw2021_l1"},"factors":[{"name":"mom20","weight":0.35,"direction":1},{"name":"mom60","weight":0.25,"direction":1},{"name":"flow5","weight":0.25,"direction":1},{"name":"amt_ratio20","weight":0.15,"direction":1}],"select":{"top_n":5,"rebalance":"weekly"},"regime":{"mode":"auto","lookback":4,"confirm":2},"cost":{"buy":0.0003,"sell":0.0003}}',
 1, 1, NULL),
('sys_sw_reversal_flow', '申万·反转+资金流',
 '固定反转（买弱）叠加资金流入与活跃度，周频 Top5',
 '{"universe":{"source":"sw2021_l1"},"factors":[{"name":"mom20","weight":0.40,"direction":-1},{"name":"flow5","weight":0.35,"direction":1},{"name":"amt_ratio20","weight":0.25,"direction":1}],"select":{"top_n":5,"rebalance":"weekly"},"regime":{"mode":"reversal"},"cost":{"buy":0.0003,"sell":0.0003}}',
 1, 1, NULL);
