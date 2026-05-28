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

CREATE TABLE IF NOT EXISTS ods_stock_detail_di (
    id          BIGINT PRIMARY KEY AUTO_INCREMENT,
    ts_code     VARCHAR(16)    NOT NULL COMMENT 'TS代码',
    trade_date  DATE           NOT NULL COMMENT '交易日期',
    open        DECIMAL(20, 6) NULL COMMENT '开盘价',
    high        DECIMAL(20, 6) NULL COMMENT '最高价',
    low         DECIMAL(20, 6) NULL COMMENT '最低价',
    close       DECIMAL(20, 6) NULL COMMENT '收盘价',
    pre_close   DECIMAL(20, 6) NULL COMMENT '昨收价(除权)',
    `change`    DECIMAL(20, 6) NULL COMMENT '涨跌额',
    pct_chg     DECIMAL(20, 6) NULL COMMENT '涨跌幅(%)',
    vol         DECIMAL(20, 6) NULL COMMENT '成交量(手)',
    amount      DECIMAL(20, 6) NULL COMMENT '成交额(千元)',
    UNIQUE KEY uk_stock_detail (trade_date, ts_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='A股日线行情(Tushare daily)';

CREATE TABLE IF NOT EXISTS ods_industry_fund_flow_di (
    id                    BIGINT PRIMARY KEY AUTO_INCREMENT,
    trade_date            DATE           NOT NULL COMMENT '交易日期',
    content_type          VARCHAR(32)    NULL COMMENT '资金类型(行业、概念、地域)',
    industry_code         VARCHAR(32)    NOT NULL COMMENT '行业板块代码',
    industry_name         VARCHAR(128)   NULL COMMENT '行业板块名称',
    pct_change            DECIMAL(20, 6) NULL COMMENT '板块涨跌幅(%)',
    close                 DECIMAL(20, 6) NULL COMMENT '板块最新指数',
    net_amount            DECIMAL(20, 4) NULL COMMENT '今日主力净流入净额(元)',
    net_amount_rate       DECIMAL(20, 6) NULL COMMENT '今日主力净流入净占比(%)',
    buy_elg_amount        DECIMAL(20, 4) NULL COMMENT '今日超大单净流入净额(元)',
    buy_elg_amount_rate   DECIMAL(20, 6) NULL COMMENT '今日超大单净流入净占比(%)',
    buy_lg_amount         DECIMAL(20, 4) NULL COMMENT '今日大单净流入净额(元)',
    buy_lg_amount_rate    DECIMAL(20, 6) NULL COMMENT '今日大单净流入净占比(%)',
    buy_md_amount         DECIMAL(20, 4) NULL COMMENT '今日中单净流入净额(元)',
    buy_md_amount_rate    DECIMAL(20, 6) NULL COMMENT '今日中单净流入净占比(%)',
    buy_sm_amount         DECIMAL(20, 4) NULL COMMENT '今日小单净流入净额(元)',
    buy_sm_amount_rate    DECIMAL(20, 6) NULL COMMENT '今日小单净流入净占比(%)',
    buy_sm_amount_stock   VARCHAR(128)   NULL COMMENT '今日主力净流入最大股',
    `rank`                INT            NULL COMMENT '序号',
    UNIQUE KEY uk_industry_mf_dc (trade_date, industry_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='东财板块资金流向(Tushare moneyflow_ind_dc)';

CREATE TABLE IF NOT EXISTS ods_industry_classify (
    index_code     VARCHAR(32)  NULL COMMENT '指数代码',  ??????
    industry_name  VARCHAR(128) NULL COMMENT '行业名称',
    parent_code    VARCHAR(32)  NULL COMMENT '父级代码',
    level          VARCHAR(8)   NULL COMMENT '行业层级(L1/L2/L3)',
    industry_code  VARCHAR(32)  NOT NULL COMMENT '行业代码',
    is_pub         VARCHAR(8)   NULL COMMENT '是否发布了指数',
    src            VARCHAR(16)  NOT NULL COMMENT '行业分类(SW2014/SW2021)',
    UNIQUE KEY uk_industry_classify (src, industry_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='申万行业分类(Tushare index_classify)';

CREATE TABLE IF NOT EXISTS ods_industry_daily_di (
    ts_code      VARCHAR(32)    NOT NULL COMMENT '指数代码',
    trade_date   DATE           NOT NULL COMMENT '交易日期',
    name         VARCHAR(128)   NULL COMMENT '指数名称',
    open         DECIMAL(20, 6) NULL COMMENT '开盘点位',
    low          DECIMAL(20, 6) NULL COMMENT '最低点位',
    high         DECIMAL(20, 6) NULL COMMENT '最高点位',
    close        DECIMAL(20, 6) NULL COMMENT '收盘点位',
    `change`     DECIMAL(20, 6) NULL COMMENT '涨跌点位',
    pct_change   DECIMAL(20, 6) NULL COMMENT '涨跌幅',
    vol          DECIMAL(20, 6) NULL COMMENT '成交量(万股)',
    amount       DECIMAL(20, 6) NULL COMMENT '成交额(万元)',
    pe           DECIMAL(20, 6) NULL COMMENT '市盈率',
    pb           DECIMAL(20, 6) NULL COMMENT '市净率',
    float_mv     DECIMAL(20, 6) NULL COMMENT '流通市值(万元)',
    total_mv     DECIMAL(20, 6) NULL COMMENT '总市值(万元)',
    UNIQUE KEY uk_industry_daily (trade_date, ts_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='申万行业日线行情(Tushare sw_daily)';

