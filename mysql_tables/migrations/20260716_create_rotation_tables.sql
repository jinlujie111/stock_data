-- =============================================================================
-- 板块轮动表落在 stock_data（非 data_industry）2026-07-16
--
-- 用法:
--   mysql -u root -p < mysql_tables/migrations/20260716_create_rotation_tables.sql
--
-- 若曾误建在 data_industry，本脚本会先清理 data_industry 中的同名表。
-- =============================================================================

-- 清理误建在 data_industry 的表（若存在）
DROP TABLE IF EXISTS data_industry.rotation_backtest_nav;
DROP TABLE IF EXISTS data_industry.rotation_backtest_trade;
DROP TABLE IF EXISTS data_industry.rotation_backtest_run;
DROP TABLE IF EXISTS data_industry.rotation_signal_di;
DROP TABLE IF EXISTS data_industry.rotation_strategy;

USE stock_data;

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

SELECT 'rotation_tables_in_stock_data' AS step,
       (SELECT COUNT(*) FROM stock_data.rotation_strategy) AS strategy_cnt;
