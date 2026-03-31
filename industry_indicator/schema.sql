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
    raw_json JSON NOT NULL COMMENT '原始数据JSON',
    created_at DATETIME NOT NULL COMMENT '创建时间',
    updated_at DATETIME NOT NULL COMMENT '更新时间',
    UNIQUE KEY uniq_industry_fund_flow (trade_date, period_type, industry_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='行业资金流日报';

-- ============================================================================
-- 【行业衍生财务指标】计算逻辑（表 industry_financial_indicator_di）
-- 实现脚本：industry_indicator/industry_financial_indicator_etl.py
-- 默认模式 legu_sw3；可选 --mode tushare_citic（逻辑见脚本内说明）。
--
-- 1) 收入增速 revenue_yoy_pct（营业收入同比增速，单位：百分比数值，如 12.5 表示 12.5%）
--    数据源：AkShare sw_index_third_cons（乐咕-申万三级行业成分表）。
--    步骤：在成分表所有列名包含「营业收入同比」或「营业总收入同比」的列中，统计每列非空条数，
--    选取非空条数最多的那一列作为代表列；将该列各成分股单元格解析为数值（去掉百分号等）后，
--    对行业内全部成分股取简单算术平均。不做市值加权。若无可选列或全非空则为 NULL。
--
-- 2) 毛利率 gross_margin_pct（销售毛利率，单位：百分比数值）
--    数据源：AkShare 同花顺 stock_financial_abstract_ths(symbol, indicator=按报告期)。
--    步骤：在行业内将成分股按「市值」降序排列，取前 N 只（参数 --max-stocks-per-industry，默认 3）。
--    对每只股票拉取财务摘要表，按报告期排序后取最后一行（最近一期）；
--    列名优先匹配含「销售毛利率」的列，否则匹配含「毛利率」的列，解析为百分数；
--    对成功解析的样本股毛利率再取算术平均。请求间有 --cons-sleep 间隔。全失败则为 NULL。
--
-- 3) backlog 增速 backlog_yoy_pct（订单 backlog 的行业代理：合同负债同比增速，单位：百分比数值）
--    数据源：AkShare 同花顺 stock_financial_debt_ths(symbol, indicator=按报告期)。
--    步骤：样本股选取与排序规则与毛利率相同（市值前 N）。
--    在负债表中定位「报告期」列与「合同负债」列，按报告期升序排序；
--    取最近一期报告的合同负债为 cur（期末值），再取报告期日期不晚于「cur 的报告期减 1 年」
--    的所有记录中最后一条为 prev（同比基期）；
--    单股增速 = (cur - prev) / abs(prev) * 100；若 prev 绝对值过小（近零）则该股不产出值。
--    对各样本股得到的增速取算术平均。金融等行业负债表无「合同负债」列时该股跳过。
--
-- sample_stocks：参与毛利率与 backlog 计算的成分股数量（即上述 N，与成分总数可能不同）。
-- raw_json：记录所用列名、中间统计等，便于审计。
-- ============================================================================

CREATE TABLE IF NOT EXISTS industry_financial_indicator_di (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    source VARCHAR(64) NOT NULL COMMENT '数据来源 akshare_legu_sw3 / tushare_citic',
    report_period DATE NULL COMMENT '财报期(可选)',
    industry_name VARCHAR(128) NOT NULL COMMENT '行业名称',
    industry_code VARCHAR(32) NULL COMMENT '行业代码(申万三级等,无.SI后缀)',
    revenue_yoy_pct DECIMAL(20, 6) NULL COMMENT '收入增速(百分比口径):成分表最佳同比列全成分算术平均,见本文件逻辑说明块',
    gross_margin_pct DECIMAL(20, 6) NULL COMMENT '毛利率(百分比口径):市值前N股THS摘要最近期销售毛利率算术平均,见说明块',
    backlog_yoy_pct DECIMAL(20, 6) NULL COMMENT 'backlog代理(百分比口径):市值前N股合同负债同比增速算术平均,见说明块',
    sample_stocks INT NULL COMMENT '毛利率与backlog所用的市值前N成分股数(max-stocks-per-industry)',
    raw_json JSON NOT NULL,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    UNIQUE KEY uniq_ind_fin (source, industry_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='行业财务衍生指标(收入增速/毛利率/合同负债代理),计算逻辑见schema同文件注释块';

-- ============================================================================
-- 【行业财务数据快照】计算逻辑（表 industry_financial_data_di）
-- 实现脚本：industry_indicator/industry_financial_data_etl.py
--
-- avg_revenue_yoy：成分表中列名含「营业收入同比」或「营业总收入同比」的列中，取非空条数最多的一列，
--    对该列全体成分股解析为数值后取算术平均（全成分，非前N样本）。
-- avg_netprofit_yoy：列名含「归母净利润同比」或「净利润同比」的列中，同样按非空最多选列后全成分算术平均。
-- total_market_cap：成分「市值」列可解析为数值时求和。
-- avg_pe / avg_pe_ttm / avg_pb / avg_dividend_yield：对应列全成分算术平均（市盈率列排除列名含ttm的用于avg_pe）。
-- raw_json.column_means：其余数值列的行业均值汇总。
-- ============================================================================

CREATE TABLE IF NOT EXISTS industry_financial_data_di (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    source VARCHAR(64) NOT NULL COMMENT '数据来源',
    trade_date DATE NOT NULL COMMENT '快照业务日期',
    industry_code VARCHAR(32) NOT NULL COMMENT '申万三级等,无.SI',
    industry_name VARCHAR(128) NOT NULL COMMENT '行业名称',
    stock_count INT NULL COMMENT '成分股数量',
    total_market_cap DECIMAL(24, 4) NULL COMMENT '成分市值合计',
    avg_pe DECIMAL(20, 6) NULL COMMENT '市盈率(非TTM列)均值',
    avg_pe_ttm DECIMAL(20, 6) NULL COMMENT '市盈率TTM均值',
    avg_pb DECIMAL(20, 6) NULL COMMENT '市净率均值',
    avg_dividend_yield DECIMAL(20, 6) NULL COMMENT '股息率均值(%)',
    avg_revenue_yoy DECIMAL(20, 6) NULL COMMENT '营收同比(百分比口径):最佳同比列全成分算术平均,见本文件快照说明块',
    avg_netprofit_yoy DECIMAL(20, 6) NULL COMMENT '净利同比(百分比口径):最佳净利同比列全成分算术平均,见说明块',
    raw_json JSON NOT NULL COMMENT '列均值等扩展,见本文件快照说明块',
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    UNIQUE KEY uniq_ifd (source, trade_date, industry_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='行业财务数据快照(成分聚合),计算逻辑见schema同文件注释块';

