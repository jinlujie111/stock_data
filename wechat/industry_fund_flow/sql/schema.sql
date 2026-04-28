-- =============================================================================
-- A股主力资金监控系统 - MySQL 8.0 建表脚本
-- 与现有数仓 industry_fund_flow_di 兼容；可独立执行于 stock_data 库
-- =============================================================================

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

-- ---------------------------------------------------------------------------
-- 用户（微信 openid 登录，绑定 VIP）
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS users (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    openid VARCHAR(64) NOT NULL COMMENT '微信openid',
    unionid VARCHAR(64) NULL COMMENT '微信unionid',
    session_key VARCHAR(128) NULL COMMENT '会话密钥（可选不落库生产可清空）',
    nickname VARCHAR(64) NULL COMMENT '昵称',
    avatar_url VARCHAR(512) NULL COMMENT '头像',
    phone VARCHAR(20) NULL COMMENT '手机号',
    is_vip TINYINT NOT NULL DEFAULT 0 COMMENT '1=有效会员',
    vip_expire_at DATETIME NULL COMMENT '会员到期时间',
    status TINYINT NOT NULL DEFAULT 1 COMMENT '1正常0禁用',
    last_login_at DATETIME NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_users_openid (openid),
    KEY idx_users_vip (is_vip, vip_expire_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='用户表';

-- ---------------------------------------------------------------------------
-- 会员订单 / 订阅
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS vip_orders (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    user_id BIGINT NOT NULL,
    out_trade_no VARCHAR(64) NOT NULL COMMENT '商户订单号',
    plan_code VARCHAR(32) NOT NULL COMMENT 'monthly/yearly',
    amount_fen INT NOT NULL DEFAULT 0 COMMENT '支付金额分',
    pay_status TINYINT NOT NULL DEFAULT 0 COMMENT '0待付1已付2关闭',
    pay_time DATETIME NULL,
    expire_at DATETIME NULL COMMENT '本单权益结束时间',
    raw_payload JSON NULL COMMENT '微信回调原文',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_vip_out_trade (out_trade_no),
    KEY idx_vip_user (user_id, pay_status),
    CONSTRAINT fk_vip_user FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='会员订单';

-- ---------------------------------------------------------------------------
-- 市场日度快照（两市涨跌家数、总成交额等，由定时任务或数仓写入）
-- ---------------------------------------------------------------------------
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

-- ---------------------------------------------------------------------------
-- 行业指数日K（可接 Tushare / AkShare 后写入；MVP 可用行业涨跌幅+指数点位近似）
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS industry_index_di (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    trade_date DATE NOT NULL,
    industry_code VARCHAR(32) NULL,
    industry_name VARCHAR(128) NOT NULL,
    index_close DECIMAL(20, 6) NULL COMMENT '收盘行业指数/代理点位',
    change_pct DECIMAL(20, 6) NULL COMMENT '涨跌幅%',
    turnover_yi DECIMAL(20, 6) NULL COMMENT '成交额亿元',
    volume_proxy DECIMAL(20, 6) NULL COMMENT '成交量代理',
    source VARCHAR(32) NOT NULL DEFAULT 'derived' COMMENT 'tushare/akshare/derived',
    raw_json JSON NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_idx_flow (trade_date, industry_name, source)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='行业指数/走势日表';

-- ---------------------------------------------------------------------------
-- 股票池（行业龙头股 / 成分代表）
-- ---------------------------------------------------------------------------
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

-- ---------------------------------------------------------------------------
-- 行业综合评分与次日潜伏榜（核心）
-- ---------------------------------------------------------------------------
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

-- ---------------------------------------------------------------------------
-- 推送订阅（微信订阅消息模板与用户开关）
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS user_subscriptions (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    user_id BIGINT NOT NULL,
    tpl_id VARCHAR(128) NOT NULL COMMENT '订阅消息模板ID',
    enabled TINYINT NOT NULL DEFAULT 1,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_sub (user_id, tpl_id),
    CONSTRAINT fk_sub_user FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='用户消息订阅';

-- ---------------------------------------------------------------------------
-- 系统日志
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS system_logs (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    level VARCHAR(16) NOT NULL DEFAULT 'INFO',
    module VARCHAR(64) NULL,
    message VARCHAR(1024) NOT NULL,
    context_json JSON NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    KEY idx_log_time (created_at),
    KEY idx_log_module (module)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='系统日志';

-- ---------------------------------------------------------------------------
-- 已有表 industry_fund_flow_di：若不存在可从数仓同步此 DDL（与主工程一致）
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS industry_fund_flow_di (
    id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '自增主键',
    trade_date DATE NOT NULL COMMENT '数据日期',
    period_type VARCHAR(32) NOT NULL COMMENT '周期类型',
    ranking_no INT NULL COMMENT '行业排名',
    industry_code VARCHAR(32) NULL COMMENT '行业代码',
    industry_name VARCHAR(128) NOT NULL COMMENT '行业名称',
    industry_index_value DECIMAL(20, 6) NULL COMMENT '行业指数值',
    industry_change_pct DECIMAL(20, 6) NULL COMMENT '行业涨跌幅(%)',
    main_net_inflow DECIMAL(20, 6) NULL COMMENT '主力净流入(亿元)',
    super_large_net_inflow DECIMAL(20, 6) NULL,
    large_net_inflow DECIMAL(20, 6) NULL,
    company_count INT NULL,
    top_stock_name VARCHAR(128) NULL,
    top_stock_change_pct DECIMAL(20, 6) NULL,
    current_price DECIMAL(20, 6) NULL,
    industry_turnover DECIMAL(20, 6) NULL COMMENT '行业成交额(亿元)',
    raw_json JSON NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uniq_industry_fund_flow (trade_date, period_type, industry_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='行业资金流日报';

SET FOREIGN_KEY_CHECKS = 1;
