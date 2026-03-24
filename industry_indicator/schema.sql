CREATE TABLE IF NOT EXISTS industry_indicator_valuation (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    source VARCHAR(64) NOT NULL,
    category_symbol VARCHAR(64) NOT NULL,
    trade_date DATE NOT NULL,
    industry_name VARCHAR(128) NULL,
    industry_code VARCHAR(64) NULL,
    pe_value DECIMAL(20, 6) NULL,
    rank_desc VARCHAR(64) NULL,
    raw_json JSON NOT NULL,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    UNIQUE KEY uniq_industry_pe (source, category_symbol, trade_date, industry_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
