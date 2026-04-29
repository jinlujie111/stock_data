-- 单独补齐 industry_score_di（若已在 schema.sql 中建过可跳过）
CREATE TABLE IF NOT EXISTS industry_score_di (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    trade_date DATE NOT NULL,
    industry_name VARCHAR(128) NOT NULL,
    industry_code VARCHAR(32) NULL,
    score_rank_today DECIMAL(10, 6) NULL COMMENT '今日净流入排名得分0-100',
    score_sum5 DECIMAL(10, 6) NULL COMMENT '5日累计净流入得分',
    score_turnover_amp DECIMAL(10, 6) NULL COMMENT '成交额放大得分',
    score_chg_strength DECIMAL(10, 6) NULL COMMENT '板块涨幅强度得分',
    total_score DECIMAL(12, 6) NOT NULL COMMENT '加权总分',
    latent_rank INT NULL COMMENT '潜伏榜名次',
    risk_level VARCHAR(16) NULL COMMENT 'low/medium/high',
    detail_json JSON NULL COMMENT '中间指标JSON',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_score (trade_date, industry_name),
    KEY idx_score_trade_latent (trade_date, latent_rank),
    KEY idx_score_total (trade_date, total_score)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='行业评分与潜伏';
