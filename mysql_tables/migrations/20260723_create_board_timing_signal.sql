-- =============================================================================
-- 东财板块四因子择时信号表（2026-07-23）
--
-- 用法:
--   mysql -u root -p < mysql_tables/migrations/20260723_create_board_timing_signal.sql
-- =============================================================================

USE stock_data;

CREATE TABLE IF NOT EXISTS dwm_board_timing_signal_di (
    id                  BIGINT PRIMARY KEY AUTO_INCREMENT,
    trade_date          DATE           NOT NULL COMMENT '交易日期',
    industry_code       VARCHAR(32)    NOT NULL COMMENT '板块代码(东财)',
    industry_name       VARCHAR(128)   NULL COMMENT '板块名称',
    content_type        VARCHAR(16)    NULL COMMENT '行业/概念/地域',
    close               DECIMAL(20, 6) NULL COMMENT '收盘点位',
    ma20                DECIMAL(20, 6) NULL COMMENT '20日均线',
    ma60                DECIMAL(20, 6) NULL COMMENT '60日均线',
    score               DECIMAL(10, 2) NULL COMMENT '综合分0-100',
    score_trend         DECIMAL(10, 2) NULL COMMENT '趋势分',
    score_fund          DECIMAL(10, 2) NULL COMMENT '资金分',
    score_vp            DECIMAL(10, 2) NULL COMMENT '量价分',
    score_sentiment     DECIMAL(10, 2) NULL COMMENT '情绪分',
    signal_type         VARCHAR(8)     NOT NULL DEFAULT 'none' COMMENT 'buy/sell/none',
    signal_reason       VARCHAR(512)   NULL COMMENT '触发原因',
    position_state      VARCHAR(16)    NULL COMMENT 'long/flat/watch',
    mom20               DECIMAL(20, 6) NULL COMMENT '20日动量(小数)',
    flow5               DECIMAL(20, 4) NULL COMMENT '5日主力净流入累计(元)',
    net_inflow_days     INT            NULL COMMENT '连续净流入天数',
    amount_ratio20      DECIMAL(20, 6) NULL COMMENT '额/额MA20',
    up_ratio            DECIMAL(20, 6) NULL COMMENT '上涨家数占比',
    limit_up_ratio      DECIMAL(20, 6) NULL COMMENT '涨停扩散率',
    sentiment_overheat  TINYINT        NOT NULL DEFAULT 0 COMMENT '情绪过热熔断',
    last_buy_close      DECIMAL(20, 6) NULL COMMENT '最近买入参考价(止损用)',
    rank_score          INT            NULL COMMENT '综合分截面排名(升序百分位内1最好)',
    created_at          DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at          DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_board_timing (trade_date, industry_code),
    KEY idx_board_timing_signal (trade_date, signal_type, score),
    KEY idx_board_timing_board (industry_code, trade_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='东财板块四因子择时信号(趋势/资金/量价/情绪)';
