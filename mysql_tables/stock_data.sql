-- ============================================================================
-- 交易日维度表 trading_day_di
-- 设计说明：
--   存储历史和未来的交易日信息，用于数据处理时判断日期是否为交易日。
-- ============================================================================

CREATE TABLE IF NOT EXISTS ods_trading_day (
    trade_date DATE COMMENT '交易日日期'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='交易日维度表';

CREATE TABLE IF NOT EXISTS ods_trading_day_di (
    exchange      VARCHAR(10) COMMENT '交易所 SSE上交所 SZSE深交所',
    trade_date    VARCHAR(10)   COMMENT '日历日期',
    is_open       VARCHAR(1) COMMENT '是否交易 0休市 1交易',
    pretrade_date VARCHAR(10) COMMENT '上一个交易日'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='交易日维度增量日期';

CREATE TABLE IF NOT EXISTS ods_stock_fund_flow_di (
    id                BIGINT PRIMARY KEY AUTO_INCREMENT,
    ts_code           VARCHAR(16)  NOT NULL COMMENT 'TS代码',
    trade_date        DATE         NOT NULL COMMENT '交易日期',
    buy_sm_vol        INT          NULL COMMENT '小单买入量(手)',
    buy_sm_amount     DECIMAL(20, 4) NULL COMMENT '小单买入金额(万元)',
    sell_sm_vol       INT          NULL COMMENT '小单卖出量(手)',
    sell_sm_amount    DECIMAL(20, 4) NULL COMMENT '小单卖出金额(万元)',
    buy_md_vol        INT          NULL COMMENT '中单买入量(手)',
    buy_md_amount     DECIMAL(20, 4) NULL COMMENT '中单买入金额(万元)',
    sell_md_vol       INT          NULL COMMENT '中单卖出量(手)',
    sell_md_amount    DECIMAL(20, 4) NULL COMMENT '中单卖出金额(万元)',
    buy_lg_vol        INT          NULL COMMENT '大单买入量(手)',
    buy_lg_amount     DECIMAL(20, 4) NULL COMMENT '大单买入金额(万元)',
    sell_lg_vol       INT          NULL COMMENT '大单卖出量(手)',
    sell_lg_amount    DECIMAL(20, 4) NULL COMMENT '大单卖出金额(万元)',
    buy_elg_vol       INT          NULL COMMENT '特大单买入量(手)',
    buy_elg_amount    DECIMAL(20, 4) NULL COMMENT '特大单买入金额(万元)',
    sell_elg_vol      INT          NULL COMMENT '特大单卖出量(手)',
    sell_elg_amount   DECIMAL(20, 4) NULL COMMENT '特大单卖出金额(万元)',
    net_mf_vol        INT          NULL COMMENT '净流入量(手)',
    net_mf_amount     DECIMAL(20, 4) NULL COMMENT '净流入额(万元)',
    UNIQUE KEY uk_stock_mf (trade_date, ts_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='个股资金流向(Tushare moneyflow)';


CREATE TABLE IF NOT EXISTS ods_industry_fund_flow_di (
    id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '自增主键',
    trade_date DATE NOT NULL COMMENT '数据日期',
    period_type VARCHAR(32) NOT NULL COMMENT '周期类型: 即时/3日排行/5日排行/10日排行/20日排行',
    ranking_no INT NULL COMMENT '行业排名',
    industry_code VARCHAR(32) NULL COMMENT '行业代码',
    industry_name VARCHAR(128) NOT NULL COMMENT '行业名称',
    industry_index_value DECIMAL(20, 6) NULL COMMENT '行业指数值(即时口径可用)',
    industry_change_pct DECIMAL(20, 6) NULL COMMENT '行业涨跌幅(%)',
    main_net_inflow DECIMAL(20, 6) NULL COMMENT '主力净流入(亿元)',
    super_large_net_inflow DECIMAL(20, 6) NULL COMMENT '超大单净流入(亿元)',
    large_net_inflow DECIMAL(20, 6) NULL COMMENT '大单净流入(亿元)',
    company_count INT NULL COMMENT '公司家数(即时口径可用)',
    top_stock_name VARCHAR(128) NULL COMMENT '领涨股名称',
    top_stock_change_pct DECIMAL(20, 6) NULL COMMENT '领涨股涨跌幅(%)',
    current_price DECIMAL(20, 6) NULL COMMENT '当前价(即时口径可用)',
    industry_turnover DECIMAL(20, 6) NULL COMMENT '行业成交额(亿元)：从 ths_industry_di 表的 amount 字段获取，单位为亿元（源数据为万元）',
    raw_json JSON NOT NULL COMMENT '原始数据JSON',
    created_at DATETIME NOT NULL COMMENT '创建时间',
    updated_at DATETIME NOT NULL COMMENT '更新时间',
    UNIQUE KEY uniq_industry_fund_flow (trade_date, period_type, industry_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='行业资金流日报';


CREATE TABLE IF NOT EXISTS industry_indicator_valuation (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    source VARCHAR(64) NOT NULL COMMENT '数据来源标识',
    category_symbol VARCHAR(64) NOT NULL COMMENT '分类维度，如 SW_L1/SW_L2/SW_L3',
    trade_date DATE NOT NULL COMMENT '入库业务日期(快照按抓取日)',
    industry_name VARCHAR(128) NULL COMMENT '行业名称',
    industry_code VARCHAR(64) NULL COMMENT '行业代码(与资金流等表统一，如 801010，不含 .SI)',
    pe_value DECIMAL(20, 6) NULL COMMENT 'TTM滚动市盈率(主展示)',
    pe_static DECIMAL(20, 6) NULL COMMENT '静态市盈率',
    pb_value DECIMAL(20, 6) NULL COMMENT '市净率',
    ps_value DECIMAL(20, 6) NULL COMMENT '市销率(预留，当前源无则空)',
    dividend_yield DECIMAL(20, 6) NULL COMMENT '静态股息率',
    rank_desc VARCHAR(64) NULL COMMENT '层级说明，如 申万三级',
    raw_json JSON NOT NULL,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    UNIQUE KEY uniq_industry_pe (source, category_symbol, trade_date, industry_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='行业估值快照(申万等)';

CREATE TABLE IF NOT EXISTS industry_fund_flow_di (
    id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '自增主键',
    trade_date DATE NOT NULL COMMENT '数据日期',
    period_type VARCHAR(32) NOT NULL COMMENT '周期类型: 即时',
    ranking_no INT NULL COMMENT '行业排名',
    industry_code VARCHAR(32) NULL COMMENT '行业代码',
    industry_name VARCHAR(128) NOT NULL COMMENT '行业名称',
    industry_index_value DECIMAL(20, 6) NULL COMMENT '行业指数值(即时口径可用)',
    industry_change_pct DECIMAL(20, 6) NULL COMMENT '行业涨跌幅(%)',
    main_net_inflow DECIMAL(20, 6) NULL COMMENT '主力净流入(亿元)',
    super_large_net_inflow DECIMAL(20, 6) NULL COMMENT '超大单净流入(亿元)',
    large_net_inflow DECIMAL(20, 6) NULL COMMENT '大单净流入(亿元)',
    company_count INT NULL COMMENT '公司家数(即时口径可用)',
    top_stock_name VARCHAR(128) NULL COMMENT '领涨股名称',
    top_stock_change_pct DECIMAL(20, 6) NULL COMMENT '领涨股涨跌幅(%)',
    current_price DECIMAL(20, 6) NULL COMMENT '当前价(即时口径可用)',
    industry_turnover DECIMAL(20, 6) NULL COMMENT '行业成交额(亿元)：从 ths_industry_di 表的 amount 字段获取，单位为亿元（源数据为万元）',
    raw_json JSON NOT NULL COMMENT '原始数据JSON',
    created_at DATETIME NOT NULL COMMENT '创建时间',
    updated_at DATETIME NOT NULL COMMENT '更新时间',
    UNIQUE KEY uniq_industry_fund_flow (trade_date, period_type, industry_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='行业资金流日报';

-- ============================================================================
-- 【市场日度快照】market_daily_di — 小程序/API 仪表盘：总成交额、涨跌家数、风险提示
-- 写入：wechat 后端定时任务 market_snapshot_job；或手工 INSERT
-- ============================================================================
CREATE TABLE IF NOT EXISTS market_daily_di (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    trade_date DATE NOT NULL,
    total_turnover_yi DECIMAL(20, 4) NULL COMMENT 'A股总成交额(亿元，口径可配置)',
    sh_up INT NULL,
    sh_down INT NULL,
    sz_up INT NULL,
    sz_down INT NULL,
    up_count INT NULL COMMENT '上涨家数合计',
    down_count INT NULL COMMENT '下跌家数合计',
    risk_note VARCHAR(512) NULL COMMENT '风险提示文案',
    raw_json JSON NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_mkt_date (trade_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='市场日度快照';

-- ============================================================================
-- 【行业评分与次日潜伏】industry_score_di — 评分引擎写入，供 /rank/latent 等接口
-- ============================================================================
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

-- ============================================================================
-- 【行业股票池】stock_pool_di — 行业详情龙头股列表（可选；无数据时接口用资金流领涨股占位）
-- ============================================================================
CREATE TABLE IF NOT EXISTS stock_pool_di (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    trade_date DATE NOT NULL,
    industry_name VARCHAR(128) NOT NULL,
    stock_code VARCHAR(16) NOT NULL COMMENT '6位代码',
    stock_name VARCHAR(64) NULL,
    role_type VARCHAR(32) NOT NULL DEFAULT 'leader' COMMENT 'leader/weight/sample',
    weight DECIMAL(10, 6) NULL COMMENT '权重或排序分',
    change_pct DECIMAL(20, 6) NULL,
    main_net_inflow DECIMAL(20, 6) NULL COMMENT '亿元',
    raw_json JSON NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_pool (trade_date, industry_name, stock_code, role_type),
    KEY idx_pool_ind (trade_date, industry_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='行业股票池/龙头';

