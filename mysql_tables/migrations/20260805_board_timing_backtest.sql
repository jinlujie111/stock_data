-- =============================================================================
-- 板块择时回测 + 信号归档（2026-08-05）
--
-- 成交约定：信号日收盘确认 → T+1 开盘成交（entry/exit = next open）
-- 用法:
--   mysql -u root -p < mysql_tables/migrations/20260805_board_timing_backtest.sql
-- =============================================================================

USE stock_data;

-- 热表过期前归档，供长周期回测
CREATE TABLE IF NOT EXISTS dwm_board_timing_signal_arch (
    id                  BIGINT PRIMARY KEY AUTO_INCREMENT,
    trade_date          DATE           NOT NULL COMMENT '交易日期',
    industry_code       VARCHAR(32)    NOT NULL COMMENT '板块代码(东财)',
    industry_name       VARCHAR(128)   NULL COMMENT '板块名称',
    content_type        VARCHAR(16)    NULL COMMENT '行业/概念/地域',
    close               DECIMAL(20, 6) NULL,
    ma20                DECIMAL(20, 6) NULL,
    ma60                DECIMAL(20, 6) NULL,
    score               DECIMAL(10, 2) NULL,
    score_trend         DECIMAL(10, 2) NULL,
    score_fund          DECIMAL(10, 2) NULL,
    score_vp            DECIMAL(10, 2) NULL,
    score_sentiment     DECIMAL(10, 2) NULL,
    signal_type         VARCHAR(8)     NOT NULL DEFAULT 'none',
    signal_reason       VARCHAR(512)   NULL,
    position_state      VARCHAR(16)    NULL,
    mom20               DECIMAL(20, 6) NULL,
    flow5               DECIMAL(20, 4) NULL,
    net_inflow_days     INT            NULL,
    amount_ratio20      DECIMAL(20, 6) NULL,
    up_ratio            DECIMAL(20, 6) NULL,
    limit_up_ratio      DECIMAL(20, 6) NULL,
    sentiment_overheat  TINYINT        NOT NULL DEFAULT 0,
    last_buy_close      DECIMAL(20, 6) NULL,
    rank_score          INT            NULL,
    created_at          DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at          DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_board_timing_arch (trade_date, industry_code),
    KEY idx_board_timing_arch_sig (trade_date, signal_type),
    KEY idx_board_timing_arch_board (industry_code, trade_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='板块择时信号归档(热表purge前写入)';

CREATE TABLE IF NOT EXISTS dwm_board_timing_bt_run (
    id              BIGINT PRIMARY KEY AUTO_INCREMENT,
    run_code        VARCHAR(64)    NOT NULL COMMENT '运行编码(可重复覆盖日批默认)',
    name            VARCHAR(128)   NULL COMMENT '回测名称',
    start_date      DATE           NOT NULL,
    end_date        DATE           NOT NULL,
    content_types   VARCHAR(64)    NOT NULL DEFAULT '行业,概念',
    exec_model      VARCHAR(32)    NOT NULL DEFAULT 't1_open' COMMENT 't1_open=信号日确认T+1开盘成交',
    cost_bps        DECIMAL(10, 4) NOT NULL DEFAULT 0 COMMENT '单边成本(基点)',
    params_json     MEDIUMTEXT     NULL COMMENT 'TimingConfig快照JSON',
    status          VARCHAR(16)    NOT NULL DEFAULT 'pending' COMMENT 'pending/running/done/failed',
    trade_count     INT            NULL,
    board_count     INT            NULL,
    win_rate        DECIMAL(12, 6) NULL COMMENT '已平仓胜率',
    avg_return      DECIMAL(12, 6) NULL COMMENT '已平仓平均收益(小数)',
    total_return    DECIMAL(12, 6) NULL COMMENT '全板块等权复利近似',
    max_drawdown    DECIMAL(12, 6) NULL COMMENT '等权组合最大回撤',
    avg_hold_days   DECIMAL(12, 4) NULL,
    profit_factor  DECIMAL(12, 6) NULL,
    error_msg       VARCHAR(512)   NULL,
    created_at      DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finished_at     DATETIME       NULL,
    UNIQUE KEY uk_bt_run_code_range (run_code, start_date, end_date),
    KEY idx_bt_run_end (end_date, status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='板块择时回测运行';

CREATE TABLE IF NOT EXISTS dwm_board_timing_bt_trade (
    id                BIGINT PRIMARY KEY AUTO_INCREMENT,
    run_id            BIGINT         NOT NULL,
    industry_code     VARCHAR(32)    NOT NULL,
    industry_name     VARCHAR(128)   NULL,
    content_type      VARCHAR(16)    NULL,
    buy_signal_date   DATE           NOT NULL COMMENT '买入信号日(收盘确认)',
    entry_date        DATE           NOT NULL COMMENT '成交买入日(T+1开盘)',
    entry_price       DECIMAL(20, 6) NOT NULL,
    sell_signal_date  DATE           NULL COMMENT '卖出信号日;空=未平仓',
    exit_date         DATE           NULL COMMENT '成交卖出日或盯市日',
    exit_price        DECIMAL(20, 6) NULL,
    return_pct        DECIMAL(12, 6) NULL COMMENT '扣成本后收益(小数)',
    hold_days         INT            NULL COMMENT '持仓交易日数',
    exit_reason       VARCHAR(512)   NULL,
    is_open           TINYINT        NOT NULL DEFAULT 0 COMMENT '1=窗口末未平仓盯市',
    created_at        DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP,
    KEY idx_bt_trade_run (run_id, industry_code),
    KEY idx_bt_trade_board (industry_code, entry_date),
    KEY idx_bt_trade_run_ret (run_id, return_pct)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='板块择时回测逐笔(T+1开盘)';

CREATE TABLE IF NOT EXISTS dwm_board_timing_bt_metrics (
    id              BIGINT PRIMARY KEY AUTO_INCREMENT,
    run_id          BIGINT         NOT NULL,
    industry_code   VARCHAR(32)    NOT NULL,
    industry_name   VARCHAR(128)   NULL,
    content_type    VARCHAR(16)    NULL,
    trade_count     INT            NOT NULL DEFAULT 0,
    closed_count    INT            NOT NULL DEFAULT 0,
    win_count       INT            NOT NULL DEFAULT 0,
    win_rate        DECIMAL(12, 6) NULL,
    avg_return      DECIMAL(12, 6) NULL,
    total_return    DECIMAL(12, 6) NULL COMMENT '该板块逐笔复利',
    max_drawdown    DECIMAL(12, 6) NULL,
    avg_hold_days   DECIMAL(12, 4) NULL,
    profit_factor  DECIMAL(12, 6) NULL,
    last_return     DECIMAL(12, 6) NULL COMMENT '最近一笔收益',
    updated_at      DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_bt_metrics (run_id, industry_code),
    KEY idx_bt_metrics_rank (run_id, total_return),
    KEY idx_bt_metrics_win (run_id, win_rate)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='板块择时回测按板块汇总';

SELECT 'board_timing_backtest_tables_ok' AS step;
