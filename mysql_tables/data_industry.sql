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

-- ============================================================================
-- 量化选股：策略 / 信号 / 买卖点 / 回测（写入库为 data_industry，
-- 因子来源 stock_data 只读。短线/长线共用一套配置驱动的打分引擎）
-- ============================================================================

CREATE TABLE IF NOT EXISTS quant_strategy (
    id            BIGINT PRIMARY KEY AUTO_INCREMENT,
    code          VARCHAR(64)  NOT NULL COMMENT '策略唯一编码',
    name          VARCHAR(128) NOT NULL COMMENT '策略名称',
    horizon       VARCHAR(16)  NOT NULL DEFAULT 'short' COMMENT 'short=短线 long=长线',
    description   VARCHAR(512) NULL COMMENT '策略说明',
    config_json   MEDIUMTEXT   NOT NULL COMMENT '因子/权重/选股/风控配置(JSON)',
    is_system     TINYINT      NOT NULL DEFAULT 0 COMMENT '1=系统内置模板',
    is_active     TINYINT      NOT NULL DEFAULT 1 COMMENT '1=启用(参与每日信号)',
    owner_user_id BIGINT       NULL COMMENT '创建者 app_user.id，NULL=系统',
    created_at    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_quant_strategy_code (code),
    KEY idx_quant_strategy_owner (owner_user_id),
    KEY idx_quant_strategy_active (is_active)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='量化策略定义';

CREATE TABLE IF NOT EXISTS quant_signal_di (
    id           BIGINT PRIMARY KEY AUTO_INCREMENT,
    strategy_id  BIGINT       NOT NULL COMMENT 'quant_strategy.id',
    trade_date   DATE         NOT NULL COMMENT '信号交易日',
    ts_code      VARCHAR(16)  NOT NULL COMMENT '股票TS代码',
    stock_name   VARCHAR(64)  NULL COMMENT '股票简称',
    action       VARCHAR(8)   NOT NULL COMMENT 'BUY=新进 HOLD=续持 SELL=剔除',
    rank_no      INT          NULL COMMENT '当日打分排名(1最优)',
    score        DECIMAL(10,4) NULL COMMENT '综合打分',
    close        DECIMAL(20,4) NULL COMMENT '当日收盘价',
    factor_json  TEXT         NULL COMMENT '各因子明细(JSON)',
    created_at   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_quant_signal (strategy_id, trade_date, ts_code),
    KEY idx_quant_signal_date (strategy_id, trade_date),
    KEY idx_quant_signal_code (ts_code, trade_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='每日量化选股信号';

CREATE TABLE IF NOT EXISTS quant_trade_log (
    id           BIGINT PRIMARY KEY AUTO_INCREMENT,
    user_id      BIGINT       NOT NULL COMMENT 'app_user.id',
    ts_code      VARCHAR(16)  NOT NULL COMMENT '股票TS代码',
    stock_name   VARCHAR(64)  NULL COMMENT '股票简称',
    side         VARCHAR(8)   NOT NULL COMMENT 'BUY=买入 SELL=卖出',
    trade_date   DATE         NOT NULL COMMENT '成交日期',
    price        DECIMAL(20,4) NOT NULL COMMENT '成交价',
    shares       INT          NULL COMMENT '股数(可空，仅记买卖点时)',
    amount       DECIMAL(20,2) NULL COMMENT '成交额',
    source       VARCHAR(16)  NOT NULL DEFAULT 'manual' COMMENT 'manual/strategy',
    strategy_id  BIGINT       NULL COMMENT '来源策略(可空)',
    note         VARCHAR(255) NULL COMMENT '备注',
    created_at   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    KEY idx_trade_log_user (user_id, trade_date),
    KEY idx_trade_log_code (user_id, ts_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='用户买卖点历史';

CREATE TABLE IF NOT EXISTS quant_backtest_run (
    id             BIGINT PRIMARY KEY AUTO_INCREMENT,
    strategy_id    BIGINT       NOT NULL COMMENT 'quant_strategy.id',
    owner_user_id  BIGINT       NULL COMMENT '发起者 app_user.id',
    name           VARCHAR(128) NULL COMMENT '回测名称',
    start_date     DATE         NOT NULL,
    end_date       DATE         NOT NULL,
    init_capital   DECIMAL(20,2) NOT NULL DEFAULT 1000000.00,
    params_json    TEXT         NULL COMMENT '回测入参快照(JSON)',
    status         VARCHAR(16)  NOT NULL DEFAULT 'pending' COMMENT 'pending/running/done/failed',
    total_return   DECIMAL(12,4) NULL COMMENT '区间总收益率',
    annual_return  DECIMAL(12,4) NULL COMMENT '年化收益率',
    max_drawdown   DECIMAL(12,4) NULL COMMENT '最大回撤',
    sharpe         DECIMAL(12,4) NULL COMMENT '夏普比率',
    win_rate       DECIMAL(12,4) NULL COMMENT '胜率(平仓交易)',
    trade_count    INT          NULL COMMENT '平仓交易笔数',
    bench_return   DECIMAL(12,4) NULL COMMENT '基准(沪深300)区间收益',
    error_msg      VARCHAR(512) NULL,
    created_at     DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finished_at    DATETIME     NULL,
    KEY idx_bt_run_strategy (strategy_id),
    KEY idx_bt_run_owner (owner_user_id, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='回测运行记录';

CREATE TABLE IF NOT EXISTS quant_backtest_trade (
    id           BIGINT PRIMARY KEY AUTO_INCREMENT,
    run_id       BIGINT       NOT NULL COMMENT 'quant_backtest_run.id',
    ts_code      VARCHAR(16)  NOT NULL,
    stock_name   VARCHAR(64)  NULL,
    side         VARCHAR(8)   NOT NULL COMMENT 'BUY/SELL',
    trade_date   DATE         NOT NULL,
    price        DECIMAL(20,4) NOT NULL,
    shares       INT          NULL,
    amount       DECIMAL(20,2) NULL,
    pnl          DECIMAL(20,2) NULL COMMENT '平仓盈亏(SELL行)',
    return_pct   DECIMAL(12,4) NULL COMMENT '本笔收益率(SELL行)',
    hold_days    INT          NULL COMMENT '持有交易日数',
    reason       VARCHAR(32)  NULL COMMENT 'rebalance/stop_loss/take_profit/max_hold/exit_rule/final',
    KEY idx_bt_trade_run (run_id, trade_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='回测逐笔交易';

CREATE TABLE IF NOT EXISTS quant_backtest_nav (
    id             BIGINT PRIMARY KEY AUTO_INCREMENT,
    run_id         BIGINT       NOT NULL COMMENT 'quant_backtest_run.id',
    trade_date     DATE         NOT NULL,
    nav            DECIMAL(20,6) NOT NULL COMMENT '组合净值(归一)',
    cash           DECIMAL(20,2) NULL,
    position_value DECIMAL(20,2) NULL,
    bench_nav      DECIMAL(20,6) NULL COMMENT '基准净值(归一)',
    drawdown       DECIMAL(12,6) NULL COMMENT '当日回撤',
    UNIQUE KEY uk_bt_nav (run_id, trade_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='回测净值曲线';

-- 系统内置策略模板（短线动量量价资金 / 长线质量价值趋势）
INSERT IGNORE INTO quant_strategy (code, name, horizon, description, config_json, is_system, is_active, owner_user_id)
VALUES
('sys_short_momentum', '短线·量价动量资金', 'short',
 '短周期：20日动量+量价形态+主力资金+突破，Top20 每日调仓，止损-8%/最长持有10日',
 '{"horizon":"short","universe":{"exclude_st":true,"min_amount":80000000,"min_list_days":60,"exclude_limit":true},"factors":[{"name":"mom20","weight":0.30,"direction":1},{"name":"vp_score","weight":0.25,"direction":1},{"name":"netflow5","weight":0.20,"direction":1},{"name":"breakout","weight":0.15,"direction":1},{"name":"turnover","weight":0.10,"direction":1}],"select":{"top_n":20,"rebalance":"daily"},"risk":{"stop_loss":-0.08,"take_profit":0.20,"max_hold_days":10,"exit_rule":"ma20_break"}}',
 1, 1, NULL),
('sys_long_quality', '长线·质量价值趋势', 'long',
 '长周期：ROE+净利增速+低估值+中长期趋势，Top30 每月调仓，止损-15%',
 '{"horizon":"long","universe":{"exclude_st":true,"min_amount":50000000,"min_list_days":120,"mv_min":5000000,"mv_max":null},"factors":[{"name":"roe","weight":0.25,"direction":1},{"name":"growth","weight":0.25,"direction":1},{"name":"pe_inv","weight":0.15,"direction":1},{"name":"pb_inv","weight":0.10,"direction":1},{"name":"mom120","weight":0.15,"direction":1},{"name":"above_ma60","weight":0.10,"direction":1}],"select":{"top_n":30,"rebalance":"monthly"},"risk":{"stop_loss":-0.15,"take_profit":null,"max_hold_days":null,"exit_rule":null}}',
 1, 1, NULL);
