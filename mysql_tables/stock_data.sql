-- ============================================================================
-- 交易日数据
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

-- ============================================================================
-- 股票数据
-- ============================================================================

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


CREATE TABLE IF NOT EXISTS ods_limit_list_di (
    id              BIGINT PRIMARY KEY AUTO_INCREMENT,
    trade_date      DATE           NOT NULL COMMENT '交易日期',
    ts_code         VARCHAR(16)    NOT NULL COMMENT 'TS代码',
    industry        VARCHAR(128)   NULL COMMENT '所属行业',
    name            VARCHAR(64)    NULL COMMENT '股票名称',
    close           DECIMAL(20, 6) NULL COMMENT '收盘价',
    pct_chg         DECIMAL(20, 6) NULL COMMENT '涨跌幅(%)',
    amount          DECIMAL(20, 4) NULL COMMENT '成交额',
    limit_amount    DECIMAL(20, 4) NULL COMMENT '板上成交金额',
    float_mv        DECIMAL(20, 4) NULL COMMENT '流通市值',
    total_mv        DECIMAL(20, 4) NULL COMMENT '总市值',
    turnover_ratio  DECIMAL(20, 6) NULL COMMENT '换手率',
    fd_amount       DECIMAL(20, 4) NULL COMMENT '封单金额',
    first_time      VARCHAR(16)    NULL COMMENT '首次封板时间',
    last_time       VARCHAR(16)    NULL COMMENT '最后封板时间',
    open_times      INT            NULL COMMENT '炸板次数(跌停为开板次数)',
    up_stat         VARCHAR(32)    NULL COMMENT '涨停统计(N/T)',
    limit_times     INT            NULL COMMENT '连板数',
    `limit`         VARCHAR(4)     NOT NULL COMMENT 'U涨停 D跌停 Z炸板',
    UNIQUE KEY uk_limit_list (trade_date, ts_code, `limit`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='涨跌停炸板列表(Tushare limit_list_d)';

-- ============================================================================
-- 股票财务数据
-- ============================================================================

CREATE TABLE IF NOT EXISTS ods_fina_indicator (
    id                 BIGINT PRIMARY KEY AUTO_INCREMENT,
    ts_code            VARCHAR(16)    NOT NULL COMMENT 'TS代码',
    ann_date           DATE           NOT NULL COMMENT '公告日期',
    end_date           DATE           NOT NULL COMMENT '报告期',
    eps                DECIMAL(20, 6) NULL COMMENT '基本每股收益',
    dt_eps             DECIMAL(20, 6) NULL COMMENT '稀释每股收益',
    bps                DECIMAL(20, 6) NULL COMMENT '每股净资产',
    roe                DECIMAL(20, 6) NULL COMMENT '净资产收益率',
    roe_waa            DECIMAL(20, 6) NULL COMMENT '加权平均净资产收益率',
    roe_dt             DECIMAL(20, 6) NULL COMMENT '净资产收益率(扣非)',
    roa                DECIMAL(20, 6) NULL COMMENT '总资产报酬率',
    grossprofit_margin DECIMAL(20, 6) NULL COMMENT '销售毛利率',
    netprofit_margin   DECIMAL(20, 6) NULL COMMENT '销售净利率',
    debt_to_assets     DECIMAL(20, 6) NULL COMMENT '资产负债率',
    profit_dedt        DECIMAL(20, 4) NULL COMMENT '扣非净利润',
    tr_yoy             DECIMAL(20, 6) NULL COMMENT '营业总收入同比增长率(%)',
    or_yoy             DECIMAL(20, 6) NULL COMMENT '营业收入同比增长率(%)',
    netprofit_yoy      DECIMAL(20, 6) NULL COMMENT '归母净利润同比增长率(%)',
    dt_netprofit_yoy   DECIMAL(20, 6) NULL COMMENT '归母扣非净利润同比增长率(%)',
    op_yoy             DECIMAL(20, 6) NULL COMMENT '营业利润同比增长率(%)',
    ebt_yoy            DECIMAL(20, 6) NULL COMMENT '利润总额同比增长率(%)',
    equity_yoy         DECIMAL(20, 6) NULL COMMENT '净资产同比增长率',
    q_profit_yoy       DECIMAL(20, 6) NULL COMMENT '净利润同比增长率(单季度)(%)',
    q_sales_yoy        DECIMAL(20, 6) NULL COMMENT '营业收入同比增长率(单季度)(%)',
    ocf_yoy            DECIMAL(20, 6) NULL COMMENT '经营现金流同比增长率(%)',
    UNIQUE KEY uk_fina_indicator (ts_code, end_date, ann_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='上市公司财务指标(Tushare fina_indicator_vip)';

-- ============================================================================
-- 股票的预测信息
-- ============================================================================

CREATE TABLE IF NOT EXISTS ods_report_rc_di (
    id            BIGINT PRIMARY KEY AUTO_INCREMENT,
    ts_code       VARCHAR(16)    NOT NULL COMMENT 'TS代码',
    name          VARCHAR(64)    NULL COMMENT '股票名称',
    report_date   DATE           NOT NULL COMMENT '研报日期',
    report_title  VARCHAR(512)   NULL COMMENT '报告标题',
    report_type   VARCHAR(64)    NULL COMMENT '报告类型',
    classify      VARCHAR(64)    NULL COMMENT '报告分类',
    org_name      VARCHAR(128)   NULL COMMENT '机构名称',
    author_name   VARCHAR(128)   NULL COMMENT '作者',
    quarter       VARCHAR(16)    NULL COMMENT '预测报告期',
    op_rt         DECIMAL(20, 4) NULL COMMENT '预测营业收入(万元)',
    op_pr         DECIMAL(20, 4) NULL COMMENT '预测营业利润(万元)',
    tp            DECIMAL(20, 4) NULL COMMENT '预测利润总额(万元)',
    np            DECIMAL(20, 4) NULL COMMENT '预测净利润(万元)',
    eps           DECIMAL(20, 6) NULL COMMENT '预测每股收益(元)',
    pe            DECIMAL(20, 6) NULL COMMENT '预测市盈率',
    rd            DECIMAL(20, 6) NULL COMMENT '预测股息率',
    roe           DECIMAL(20, 6) NULL COMMENT '预测净资产收益率',
    ev_ebitda     DECIMAL(20, 6) NULL COMMENT '预测EV/EBITDA',
    rating        VARCHAR(32)    NULL COMMENT '卖方评级',
    max_price     DECIMAL(20, 6) NULL COMMENT '预测最高目标价',
    min_price     DECIMAL(20, 6) NULL COMMENT '预测最低目标价',
    imp_dg        VARCHAR(32)    NULL COMMENT '机构关注度',
    UNIQUE KEY uk_report_rc (ts_code, report_date, org_name, quarter)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='卖方盈利预测(Tushare report_rc)';

-- ============================================================================
-- 东财板块数据
-- ============================================================================

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

CREATE TABLE IF NOT EXISTS ods_dc_index_di (
    id              BIGINT PRIMARY KEY AUTO_INCREMENT,
    trade_date      DATE           NOT NULL COMMENT '交易日期',
    ts_code         VARCHAR(32)    NOT NULL COMMENT '板块代码(东财)',
    dc_name         VARCHAR(128)   NULL COMMENT '板块名称',
    dc_leading      VARCHAR(64)    NULL COMMENT '领涨股票名称',
    leading_code    VARCHAR(16)    NULL COMMENT '领涨股票代码',
    pct_change      DECIMAL(20, 6) NULL COMMENT '涨跌幅(%)',
    leading_pct     DECIMAL(20, 6) NULL COMMENT '领涨股票涨跌幅(%)',
    total_mv        DECIMAL(20, 4) NULL COMMENT '总市值(万元)',
    turnover_rate   DECIMAL(20, 6) NULL COMMENT '换手率(%)',
    up_num          INT            NULL COMMENT '上涨家数',
    down_num        INT            NULL COMMENT '下跌家数',
    idx_type        VARCHAR(32)    NULL COMMENT '板块类型(行业板块/概念板块/地域板块)',
    level           VARCHAR(16)    NULL COMMENT '行业层级',
    UNIQUE KEY uk_dc_index (trade_date, ts_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='东财板块指数日快照(Tushare dc_index)';

CREATE TABLE IF NOT EXISTS ods_dc_daily_di (
    id              BIGINT PRIMARY KEY AUTO_INCREMENT,
    ts_code         VARCHAR(32)    NOT NULL COMMENT '板块代码(东财)',
    trade_date      DATE           NOT NULL COMMENT '交易日期',
    open            DECIMAL(20, 6) NULL COMMENT '开盘点位',
    high            DECIMAL(20, 6) NULL COMMENT '最高点位',
    low             DECIMAL(20, 6) NULL COMMENT '最低点位',
    close           DECIMAL(20, 6) NULL COMMENT '收盘点位',
    `change`        DECIMAL(20, 6) NULL COMMENT '涨跌点位',
    pct_change      DECIMAL(20, 6) NULL COMMENT '涨跌幅(%)',
    vol             DECIMAL(20, 4) NULL COMMENT '成交量(股)',
    amount          DECIMAL(20, 4) NULL COMMENT '成交额(元)',
    swing           DECIMAL(20, 6) NULL COMMENT '振幅(%)',
    turnover_rate   DECIMAL(20, 6) NULL COMMENT '换手率(%)',
    UNIQUE KEY uk_dc_daily (trade_date, ts_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='东财板块日线行情(Tushare dc_daily)';

CREATE TABLE IF NOT EXISTS ods_dc_member_di (
    id          BIGINT PRIMARY KEY AUTO_INCREMENT,
    trade_date  DATE         NOT NULL COMMENT '交易日期',
    ts_code     VARCHAR(32)  NOT NULL COMMENT '板块/概念代码(东财)',
    con_code    VARCHAR(16)  NOT NULL COMMENT '成分股票代码',
    name        VARCHAR(64)  NULL COMMENT '成分股票名称',
    UNIQUE KEY uk_dc_member (trade_date, ts_code, con_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='东财板块成分(Tushare dc_member)';

CREATE TABLE IF NOT EXISTS ods_dc_hot_di (
    id              BIGINT PRIMARY KEY AUTO_INCREMENT,
    trade_date      DATE           NOT NULL COMMENT '交易日期',
    market          VARCHAR(32)    NOT NULL COMMENT '市场类型(A股市场/ETF基金/港股市场/美股市场)',
    hot_type        VARCHAR(16)    NOT NULL COMMENT '热点类型(人气榜/飙升榜)',
    data_type       VARCHAR(32)    NULL COMMENT '数据类型',
    ts_code         VARCHAR(16)    NOT NULL COMMENT '代码',
    ts_name         VARCHAR(128)   NULL COMMENT '名称',
    dc_rank         INT            NULL COMMENT '排行',
    pct_change      DECIMAL(20, 6) NULL COMMENT '涨跌幅(%)',
    current_price   DECIMAL(20, 6) NULL COMMENT '当前价',
    rank_time       VARCHAR(32)    NULL COMMENT '排行榜获取时间',
    UNIQUE KEY uk_dc_hot (trade_date, market, hot_type, ts_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='东财App热榜(Tushare dc_hot)';

-- ============================================================================
-- 同花顺板块数据
-- ============================================================================

CREATE TABLE IF NOT EXISTS ods_ths_index_di (
    id          BIGINT PRIMARY KEY AUTO_INCREMENT,
    ts_code     VARCHAR(16)  NOT NULL COMMENT '指数代码',
    name        VARCHAR(128) NULL COMMENT '指数名称',
    count       INT          NULL COMMENT '成分个数',
    exchange    VARCHAR(8)   NULL COMMENT '市场类型(A/HK/US)',
    list_date   DATE         NULL COMMENT '上市日期',
    index_type  VARCHAR(8)   NULL COMMENT '指数类型(N概念/I行业/R地域/S特色/ST风格/TH主题/BB宽基)',
    UNIQUE KEY uk_ths_index (ts_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='同花顺板块指数(Tushare ths_index)';

CREATE TABLE IF NOT EXISTS ods_ths_daily_di (
    id              BIGINT PRIMARY KEY AUTO_INCREMENT,
    ts_code         VARCHAR(16)    NOT NULL COMMENT '板块指数代码',
    trade_date      DATE           NOT NULL COMMENT '交易日期',
    open            DECIMAL(20, 6) NULL COMMENT '开盘点位',
    high            DECIMAL(20, 6) NULL COMMENT '最高点位',
    low             DECIMAL(20, 6) NULL COMMENT '最低点位',
    close           DECIMAL(20, 6) NULL COMMENT '收盘点位',
    pre_close       DECIMAL(20, 6) NULL COMMENT '昨收点位',
    avg_price       DECIMAL(20, 6) NULL COMMENT '平均价',
    `change`        DECIMAL(20, 6) NULL COMMENT '涨跌点位',
    pct_change      DECIMAL(20, 6) NULL COMMENT '涨跌幅(%)',
    vol             DECIMAL(20, 6) NULL COMMENT '成交量(手)',
    turnover_rate   DECIMAL(20, 6) NULL COMMENT '换手率(%)',
    total_mv        DECIMAL(20, 4) NULL COMMENT '总市值(元)',
    float_mv        DECIMAL(20, 4) NULL COMMENT '流通市值(元)',
    UNIQUE KEY uk_ths_daily (trade_date, ts_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='同花顺板块指数日线(Tushare ths_daily)';

CREATE TABLE IF NOT EXISTS ods_ths_member_di (
    id          BIGINT PRIMARY KEY AUTO_INCREMENT,
    ts_code     VARCHAR(16)  NOT NULL COMMENT '板块指数代码',
    con_code    VARCHAR(16)  NOT NULL COMMENT '成分股票代码',
    name        VARCHAR(64)  NULL COMMENT '成分股票名称',
    weight      DECIMAL(20, 6) NULL COMMENT '权重(暂无)',
    in_date     DATE         NULL COMMENT '纳入日期(暂无)',
    out_date    DATE         NULL COMMENT '剔除日期(暂无)',
    is_new      VARCHAR(4)   NULL COMMENT '是否最新(Y/N)',
    UNIQUE KEY uk_ths_member (ts_code, con_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='同花顺板块成分(Tushare ths_member)';

CREATE TABLE IF NOT EXISTS ods_ths_hot_di (
    id              BIGINT PRIMARY KEY AUTO_INCREMENT,
    trade_date      DATE           NOT NULL COMMENT '交易日期',
    market          VARCHAR(32)    NOT NULL COMMENT '热榜类型(热股/行业板块/概念板块等)',
    data_type       VARCHAR(32)    NULL COMMENT '数据类型',
    ts_code         VARCHAR(16)    NOT NULL COMMENT '代码',
    ts_name         VARCHAR(128)   NULL COMMENT '名称',
    ths_rank        INT            NULL COMMENT '排行',
    pct_change      DECIMAL(20, 6) NULL COMMENT '涨跌幅(%)',
    current_price   DECIMAL(20, 6) NULL COMMENT '当前价格',
    concept         TEXT           NULL COMMENT '标签(JSON数组字符串)',
    rank_reason     TEXT           NULL COMMENT '上榜解读',
    hot             DECIMAL(20, 4) NULL COMMENT '热度值',
    rank_time       VARCHAR(32)    NULL COMMENT '排行榜获取时间',
    UNIQUE KEY uk_ths_hot (trade_date, market, ts_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='同花顺App热榜(Tushare ths_hot)';

-- ============================================================================
-- 申万行业指数信息
-- ============================================================================

CREATE TABLE IF NOT EXISTS ods_industry_classify (
    index_code     VARCHAR(32)  NULL COMMENT '指数代码',
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

CREATE TABLE IF NOT EXISTS ods_index_member_all (
    id         BIGINT PRIMARY KEY AUTO_INCREMENT,
    l1_code    VARCHAR(32)  NULL COMMENT '一级行业代码',
    l1_name    VARCHAR(64)  NULL COMMENT '一级行业名称',
    l2_code    VARCHAR(32)  NULL COMMENT '二级行业代码',
    l2_name    VARCHAR(64)  NULL COMMENT '二级行业名称',
    l3_code    VARCHAR(32)  NULL COMMENT '三级行业代码',
    l3_name    VARCHAR(64)  NULL COMMENT '三级行业名称',
    ts_code    VARCHAR(16)  NOT NULL COMMENT '成分股票代码',
    name       VARCHAR(64)  NULL COMMENT '成分股票名称',
    in_date    DATE         NULL COMMENT '纳入日期',
    out_date   DATE         NULL COMMENT '剔除日期',
    is_new     VARCHAR(4)   NULL COMMENT '是否最新(Y/N)',
    UNIQUE KEY uk_index_member_all (ts_code, l3_code, in_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='申万行业成分分级(Tushare index_member_all)';


-- ============================================================================
-- 大盘指数
-- ============================================================================


CREATE TABLE IF NOT EXISTS ods_index_daily_di (
    id          BIGINT PRIMARY KEY AUTO_INCREMENT,
    ts_code     VARCHAR(16)    NOT NULL COMMENT '指数代码,现在只有三个，大盘指数，沪深300、深圳指数',
    trade_date  DATE           NOT NULL COMMENT '交易日期',
    open        DECIMAL(20, 6) NULL COMMENT '开盘点位',
    high        DECIMAL(20, 6) NULL COMMENT '最高点位',
    low         DECIMAL(20, 6) NULL COMMENT '最低点位',
    close       DECIMAL(20, 6) NULL COMMENT '收盘点位',
    pre_close   DECIMAL(20, 6) NULL COMMENT '昨收点位',
    `change`    DECIMAL(20, 6) NULL COMMENT '涨跌点位',
    pct_chg     DECIMAL(20, 6) NULL COMMENT '涨跌幅(%)',
    vol         DECIMAL(20, 6) NULL COMMENT '成交量(手)',
    amount      DECIMAL(20, 6) NULL COMMENT '成交额(千元)',
    UNIQUE KEY uk_index_daily (trade_date, ts_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='指数日线行情(Tushare index_daily)';

-- ============================================================================
-- ETF数据
-- ============================================================================

CREATE TABLE IF NOT EXISTS ods_etf_share_size_di (
    id          BIGINT PRIMARY KEY AUTO_INCREMENT,
    trade_date  DATE           NOT NULL COMMENT '交易日期',
    ts_code     VARCHAR(16)    NOT NULL COMMENT 'ETF代码',
    etf_name    VARCHAR(128)   NULL COMMENT '基金名称',
    total_share DECIMAL(20, 4) NULL COMMENT '总份额(万份)',
    total_size  DECIMAL(20, 4) NULL COMMENT '总规模(万元)',
    nav         DECIMAL(20, 6) NULL COMMENT '基金份额净值(元)',
    close       DECIMAL(20, 6) NULL COMMENT '收盘价(元)',
    exchange    VARCHAR(8)     NULL COMMENT '交易所(SSE/SZSE/BSE)',
    UNIQUE KEY uk_etf_share_size (trade_date, ts_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='ETF份额规模(Tushare etf_share_size)';

CREATE TABLE IF NOT EXISTS ods_etf_basic_di (
    id           BIGINT PRIMARY KEY AUTO_INCREMENT,
    ts_code      VARCHAR(16)  NOT NULL COMMENT 'ETF交易代码',
    csname       VARCHAR(128) NULL COMMENT 'ETF中文简称',
    extname      VARCHAR(128) NULL COMMENT 'ETF扩位简称',
    cname        VARCHAR(256) NULL COMMENT '基金中文全称',
    index_code   VARCHAR(32)  NULL COMMENT '跟踪指数代码',
    index_name   VARCHAR(128) NULL COMMENT '跟踪指数名称',
    setup_date   DATE         NULL COMMENT '设立日期',
    list_date    DATE         NULL COMMENT '上市日期',
    list_status  VARCHAR(4)   NULL COMMENT '存续状态(L/D/P)',
    exchange     VARCHAR(8)   NULL COMMENT '交易所(SH/SZ)',
    mgr_name     VARCHAR(128) NULL COMMENT '基金管理人简称',
    custod_name  VARCHAR(128) NULL COMMENT '基金托管人名称',
    mgt_fee      DECIMAL(10, 6) NULL COMMENT '管理费率',
    etf_type     VARCHAR(32)  NULL COMMENT '投资通道类型',
    UNIQUE KEY uk_etf_basic (ts_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='ETF基础信息(Tushare etf_basic)';

-- -----------------------------------------------------------------------------
-- DWM：全市场广度（由 ODS 聚合，ETL: dw-dwm/pro_dwm_market_breadth_di.sh）
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS dwm_market_breadth_di (
    id              BIGINT PRIMARY KEY AUTO_INCREMENT,
    trade_date      DATE           NOT NULL COMMENT '交易日期',
    advance_cnt     INT            NOT NULL DEFAULT 0 COMMENT '上涨家数(pct_chg>0)',
    decline_cnt     INT            NOT NULL DEFAULT 0 COMMENT '下跌家数(pct_chg<0)',
    flat_cnt        INT            NOT NULL DEFAULT 0 COMMENT '平盘家数(pct_chg=0或NULL)',
    limit_up_cnt    INT            NOT NULL DEFAULT 0 COMMENT '涨停家数(limit=U)',
    limit_down_cnt  INT            NOT NULL DEFAULT 0 COMMENT '跌停家数(limit=D)',
    advance_ratio   DECIMAL(10, 6) NULL COMMENT '上涨占比=advance_cnt/total_cnt',
    total_cnt       INT            NOT NULL DEFAULT 0 COMMENT '参与统计家数(沪深A股)',
    created_at      DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_dwm_market_breadth (trade_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='全市场广度(DWM,来源ods_stock_detail_di+ods_limit_list_di)';

-- -----------------------------------------------------------------------------
-- DWM：东财板块资金强度（由 ODS 聚合，ETL: dw-dwm/pro_dwm_dc_industry_fund_flow_di.sh）
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS dwm_dc_industry_fund_flow_di (
    id                    BIGINT PRIMARY KEY AUTO_INCREMENT,
    trade_date            DATE           NOT NULL COMMENT '交易日期',
    content_type          VARCHAR(32)    NULL COMMENT '板块类型(行业/概念/地域)',
    industry_code         VARCHAR(32)    NOT NULL COMMENT '板块代码(东财)',
    industry_name         VARCHAR(128)   NULL COMMENT '板块名称',
    net_amount            DECIMAL(20, 4) NULL COMMENT '主力净流入净额(元)',
    net_amount_wan        DECIMAL(20, 4) NULL COMMENT '主力净流入净额(万元)',
    net_amount_rate       DECIMAL(20, 6) NULL COMMENT '主力净流入占比(%)',
    buy_elg_amount        DECIMAL(20, 4) NULL COMMENT '超大单净流入(元)',
    pct_change            DECIMAL(20, 6) NULL COMMENT '板块涨跌幅(%)',
    board_amount          DECIMAL(20, 4) NULL COMMENT '板块成交额(元,来源ods_dc_daily_di)',
    fund_inflow_strength  DECIMAL(20, 8) NULL COMMENT '资金流入强度=net_amount/board_amount',
    net_inflow_days       INT            NOT NULL DEFAULT 0 COMMENT '连续净流入天数(资金连续性)',
    net_amount_5d_avg     DECIMAL(20, 4) NULL COMMENT '近5交易日平均净流入(元,不含当日)',
    fund_accel            DECIMAL(20, 4) NULL COMMENT '资金加速度=net_amount-net_amount_5d_avg',
    elg_net_ratio         DECIMAL(20, 6) NULL COMMENT '超大单占主力净流入比',
    dc_rank               INT            NULL COMMENT '东财资金流排名',
    created_at            DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at            DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_dwm_dc_industry_fund_flow (trade_date, industry_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='东财板块资金强度(DWM,来源ods_industry_fund_flow_di+ods_dc_daily_di)';

-- -----------------------------------------------------------------------------
-- DWM：同花顺板块资金强度（由 ODS 成分股汇总估算，ETL: dw-dwm/pro_dwm_ths_industry_fund_flow_di.sh）
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS dwm_ths_industry_fund_flow_di (
    id                    BIGINT PRIMARY KEY AUTO_INCREMENT,
    trade_date            DATE           NOT NULL COMMENT '交易日期',
    content_type          VARCHAR(32)    NULL COMMENT '板块类型(行业/概念/地域等)',
    industry_code         VARCHAR(32)    NOT NULL COMMENT '板块代码(同花顺)',
    industry_name         VARCHAR(128)   NULL COMMENT '板块名称',
    net_amount            DECIMAL(20, 4) NULL COMMENT '主力净流入净额(元,成分股汇总估算)',
    net_amount_wan        DECIMAL(20, 4) NULL COMMENT '主力净流入净额(万元)',
    net_amount_rate       DECIMAL(20, 6) NULL COMMENT '主力净流入占比(%)=net_amount/board_amount*100',
    buy_elg_amount        DECIMAL(20, 4) NULL COMMENT '超大单净流入(元,成分股汇总估算)',
    pct_change            DECIMAL(20, 6) NULL COMMENT '板块涨跌幅(%)',
    board_amount          DECIMAL(20, 4) NULL COMMENT '板块成交额(元,成分股成交额汇总估算)',
    fund_inflow_strength  DECIMAL(20, 8) NULL COMMENT '资金流入强度=net_amount/board_amount',
    net_inflow_days       INT            NOT NULL DEFAULT 0 COMMENT '连续净流入天数(资金连续性)',
    net_amount_5d_avg     DECIMAL(20, 4) NULL COMMENT '近5交易日平均净流入(元,不含当日)',
    fund_accel            DECIMAL(20, 4) NULL COMMENT '资金加速度=net_amount-net_amount_5d_avg',
    elg_net_ratio         DECIMAL(20, 6) NULL COMMENT '超大单占主力净流入比',
    dc_rank               INT            NULL COMMENT '当日主力净流入排名(估算)',
    created_at            DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at            DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_dwm_ths_industry_fund_flow (trade_date, industry_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='同花顺板块资金强度(DWM,成分股资金流汇总估算)';

-- -----------------------------------------------------------------------------
-- DIM：行业-ETF 映射（ETL: dw-dim/pro_dim_industry_etf_map.sh）
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS dim_industry_etf_map (
    id              BIGINT PRIMARY KEY AUTO_INCREMENT,
    industry_code   VARCHAR(32)    NOT NULL COMMENT '申万行业代码',
    industry_name   VARCHAR(128)   NULL COMMENT '申万行业名称',
    industry_level  VARCHAR(8)     NULL COMMENT '行业层级 L1/L2/L3',
    index_code      VARCHAR(32)    NULL COMMENT 'ETF跟踪指数代码',
    index_name      VARCHAR(128)   NULL COMMENT 'ETF跟踪指数名称',
    etf_code        VARCHAR(16)    NOT NULL COMMENT 'ETF代码 ts_code',
    etf_name        VARCHAR(128)   NULL COMMENT 'ETF简称',
    exchange        VARCHAR(8)     NULL COMMENT '交易所 SH/SZ',
    weight          DECIMAL(5, 4)  NOT NULL DEFAULT 1.0000 COMMENT '映射权重',
    map_type        VARCHAR(16)    NOT NULL DEFAULT 'index_match' COMMENT 'index_match=自动 manual=人工',
    sw_src          VARCHAR(16)    NULL COMMENT '申万分类版本',
    effective_date  DATE           NOT NULL COMMENT '映射生效日',
    remark          VARCHAR(256)   NULL COMMENT '备注',
    is_active       TINYINT        NOT NULL DEFAULT 1 COMMENT '1有效 0停用',
    created_at      DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_dim_industry_etf (etf_code, industry_code, map_type),
    KEY idx_dim_industry_etf_industry (industry_code, is_active),
    KEY idx_dim_industry_etf_index (index_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='行业-ETF映射维表';
