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
    industry_turnover DECIMAL(20, 6) NULL COMMENT '行业成交额(亿元)：从 ths_industry_di 表的 amount 字段获取，单位为亿元（源数据为万元）',
    raw_json JSON NOT NULL COMMENT '原始数据JSON',
    created_at DATETIME NOT NULL COMMENT '创建时间',
    updated_at DATETIME NOT NULL COMMENT '更新时间',
    UNIQUE KEY uniq_industry_fund_flow (trade_date, period_type, industry_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='行业资金流日报';

CREATE TABLE IF NOT EXISTS stock_fund_flow_di (
    id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '自增主键',
    trade_date DATE NOT NULL COMMENT '数据日期(入库业务日)',
    period_type VARCHAR(32) NOT NULL COMMENT '周期: 即时/3日排行/5日排行/10日排行/20日排行',
    ranking_no INT NULL COMMENT '排名(同花顺序号)',
    stock_code VARCHAR(16) NOT NULL COMMENT '股票代码(6位)',
    stock_name VARCHAR(64) NOT NULL COMMENT '股票简称',
    latest_price DECIMAL(20, 6) NULL COMMENT '最新价',
    change_pct DECIMAL(20, 6) NULL COMMENT '涨跌幅或阶段涨跌幅(%)',
    turnover_rate DECIMAL(20, 6) NULL COMMENT '换手率或连续换手率(%)',
    inflow_amt DECIMAL(20, 6) NULL COMMENT '流入资金(亿元)，即时口径',
    outflow_amt DECIMAL(20, 6) NULL COMMENT '流出资金(亿元)，即时口径',
    net_amt DECIMAL(20, 6) NULL COMMENT '净额或资金流入净额(亿元)',
    turnover_amt DECIMAL(20, 6) NULL COMMENT '成交额(亿元)，仅即时口径有',
    raw_json JSON NOT NULL COMMENT '原始行JSON',
    created_at DATETIME NOT NULL COMMENT '创建时间',
    updated_at DATETIME NOT NULL COMMENT '更新时间',
    UNIQUE KEY uniq_stock_fund_flow (trade_date, period_type, stock_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='个股资金流向日报(同花顺)';

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

-- ============================================================================
-- 【行业订单量 order_volume_proxy】计算方法（表 industry_order_volume_di）
-- 脚本：industry_order_volume_etl.py
--
-- 名称说明：公开数据无法直接得到「订单件数」。本表 order_volume_proxy 为货币化代理指标。
--
-- 计算步骤：
--   1) 行业口径：AkShare 申万三级 sw_index_third_info / sw_index_third_cons。
--   2) 成分股范围：默认按「市值」降序取前 N 只（CLI --max-stocks，默认 60；0 表示全部成分，请求极慢）。
--   3) 对每只成分股拉取同花顺资产负债表 stock_financial_debt_ths(按报告期)，取列「合同负债」
--      在最新报告期（报告期排序后最后一行）的余额，解析为浮点数（源站多为亿元，带「亿」字时尽力解析）。
--   4) 将步骤 3 中成功解析的余额做求和：order_volume_proxy = SUM(合同负债_latest)。
--   5) stocks_sampled 为实际参与循环的成分股数；stocks_with_contract_liab 为成功取到合同负债的股数。
--
-- 业务含义：依据会计准则，「合同负债」主要核算已收客户对价、尚未履行履约义务的金额，实务中常作为
--   在手订单、订单蓄水规模的近似；本指标为行业层面加总代理，非物理「订单数量」，亦非全部 A 股行业
--   均适用（如部分金融企业报表无该科目，合计可能偏小）。
--
-- calculation_method 固定为 contract_liab_latest_sum，便于与其它定义区分。
-- ============================================================================

CREATE TABLE IF NOT EXISTS industry_order_volume_di (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    source VARCHAR(64) NOT NULL COMMENT '如 ths_contract_liab_sum_sw3',
    trade_date DATE NOT NULL COMMENT '快照日期',
    industry_code VARCHAR(32) NOT NULL COMMENT '申万三级无.SI',
    industry_name VARCHAR(128) NOT NULL COMMENT '申万三级名称',
    order_volume_proxy DECIMAL(24, 6) NULL COMMENT '订单量代理=成分合同负债合计,见上方注释',
    value_unit VARCHAR(16) NULL DEFAULT '亿元' COMMENT '单位,与源站一致',
    stocks_sampled INT NULL COMMENT '参与加总的成分股数',
    stocks_with_contract_liab INT NULL COMMENT '成功解析合同负债的股数',
    calculation_method VARCHAR(64) NOT NULL COMMENT 'contract_liab_latest_sum',
    raw_json JSON NOT NULL,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    UNIQUE KEY uniq_order_vol (source, trade_date, industry_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='行业订单量代理,计算逻辑见本文件注释块';

-- ============================================================================
-- 【行业合同负债同比增速】计算方法（表 industry_contract_liab_yoy_di）
-- 脚本：industry_contract_liab_yoy_etl.py
--
-- 与「订单量」关系：订单量代理（industry_order_volume_di）用合同负债绝对水平之和；本表用同一科目
--   的同比增速，刻画行业层面订单池/未履约义务相对上年同期的变化，仍属代理，非订单件数。
--
-- 单股合同负债同比增速（用于行业聚合前）：
--   同花顺 stock_financial_debt_ths(按报告期)，取「合同负债」列；按报告期升序，最近一期为当期余额 cur，
--   在「报告期日期不晚于当期日期减 1 年」的行中取最后一条为同比基期余额 prev；
--   单股增速(%) = (cur - prev) / abs(prev) * 100（prev 近零则该股不参与增速统计）。
--
-- 行业层面输出两种口径（可同时参考）：
--   1) cl_yoy_mean_pct：样本成分股各自同比增速的算术平均（与 industry_financial_indicator 中 backlog
--      样本均值思路一致，但本表独立落库）。
--   2) cl_yoy_aggregate_pct：对样本中同时有 cur、prev 的成分股，先求 sum(cur)、sum(prev)，再
--      整体增速 = (sum(cur) - sum(prev)) / abs(sum(prev)) * 100，表示「行业样本池合同负债总额」的同比。
--
-- 成分范围：申万三级 sw_index_third_cons，默认按市值降序前 N 只（--max-stocks，默认 60）。
-- stocks_with_yoy：成功算出单股同比增速的只数；用于 aggregate 的 n 见 raw_json.n_for_aggregate。
--
-- calculation_method 固定为 mean_yoy_and_aggregate_yoy_from_ths_debt。
-- ============================================================================

CREATE TABLE IF NOT EXISTS industry_contract_liab_yoy_di (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    source VARCHAR(64) NOT NULL COMMENT '如 ths_contract_liab_yoy_sw3',
    trade_date DATE NOT NULL COMMENT '快照日期',
    industry_code VARCHAR(32) NOT NULL COMMENT '申万三级无.SI',
    industry_name VARCHAR(128) NOT NULL COMMENT '申万三级名称',
    cl_yoy_mean_pct DECIMAL(20, 6) NULL COMMENT '成分股合同负债同比增速算术平均,见上方注释',
    cl_yoy_aggregate_pct DECIMAL(20, 6) NULL COMMENT '样本合同负债加总后的整体同比,见上方注释',
    value_unit VARCHAR(16) NULL DEFAULT '百分比' COMMENT '增速口径',
    stocks_sampled INT NULL COMMENT '参与循环的成分股数',
    stocks_with_yoy INT NULL COMMENT '成功得到单股同比增速的股数',
    calculation_method VARCHAR(128) NOT NULL COMMENT 'mean_yoy_and_aggregate_yoy_from_ths_debt',
    raw_json JSON NOT NULL,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    UNIQUE KEY uniq_cl_yoy (source, trade_date, industry_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='行业合同负债同比增速,计算逻辑见本文件注释块';

-- ============================================================================
-- 【行业协会出货增速】计算方法（表 industry_association_shipment_di）
-- 脚本：industry_association_shipment_etl.py
--
-- 行业含义：本表并非申万 A 股行业划分，而是中国汽车流通协会乘用车市场信息联席会（乘联会）在
--   「总量市场」下公布的乘用车月度口径；行业/市场范围分为「狭义乘用车」「广义乘用车」两类（与
--   AkShare car_market_total_cpca、数据源 http://data.cpcadata.com 一致）。
--
-- 「出货」代理：公开统计中无统一「出货量」科目。实务与乘联会常用「批发销量」刻画厂商对经销商的发货
--   水平，本表将 metric_type=wholesale（批发）对应的同比增速作为**出货增速**的首选解读；
--   同时落库 retail（零售）、export（出口）、import（进口）同比，便于对照。
--
-- 计算方法：
--   1) 请求 charttype=1 的 chartlist JSON，对每个 scope（狭义/广义）遍历 dataList 中每月一行。
--   2) 每月行含两个日历年列（如 2026年、2025年）及四维数组：顺序固定为 [批发, 零售, 出口, 进口]（万辆级）。
--   3) 同比增速 shipment_yoy_pct：优先取接口字段「同比」同序四维数组（与源站一致）；若同比缺失而
--      当年与上年同月绝对量均存在，则按 (当年-上年)/|上年|*100 推算。
--   4) stat_month：取较新年份列对应的公历年 + 行内「M月」组成该月首日；仅当同时存在两个日历年列
--      且可解析月份时落库（尚未公布当年数据的月份仅含单年列，本脚本跳过，避免无同比）。
--
-- calculation_method 固定为 cpca_api_yoy_total_market_four_metrics。
-- ============================================================================

CREATE TABLE IF NOT EXISTS industry_association_shipment_di (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    source VARCHAR(64) NOT NULL COMMENT '如 cpca_total_market_chartlist_1',
    trade_date DATE NOT NULL COMMENT '入库快照日',
    stat_month DATE NOT NULL COMMENT '乘联会统计月',
    market_scope VARCHAR(32) NOT NULL COMMENT 'narrow_passenger/broad_passenger',
    metric_type VARCHAR(32) NOT NULL COMMENT 'wholesale/retail/export/import',
    industry_code VARCHAR(64) NOT NULL COMMENT '如 CPCA_NARROW_PASSENGER_WHOLESALE',
    industry_name VARCHAR(128) NOT NULL COMMENT '展示名:乘联会-狭义乘用车-批发 等',
    shipment_yoy_pct DECIMAL(20, 6) NULL COMMENT '同比增速%%,见上方注释',
    volume_current DECIMAL(20, 6) NULL COMMENT '当期量(万辆)',
    volume_prev_year DECIMAL(20, 6) NULL COMMENT '去年同期量(万辆)',
    value_unit VARCHAR(16) NULL DEFAULT '万辆',
    calculation_method VARCHAR(128) NOT NULL COMMENT 'cpca_api_yoy_total_market_four_metrics',
    raw_json JSON NOT NULL,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    UNIQUE KEY uniq_assoc_ship (source, stat_month, market_scope, metric_type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='行业协会出货增速(乘联会),计算逻辑见本文件注释块';

-- ============================================================================
-- 【申万行业信息 + 成分股】sw_industry_info_di / sw_industry_constituent_di
-- 脚本：industry_sw_universe_etl.py
-- 环境变量：SW_INDUSTRY_INFO_TABLE、SW_INDUSTRY_CONSTITUENT_TABLE
--
-- 数据来源：AkShare 乐咕乐股 sw_index_first/second/third_info；成分股接口为 sw_index_third_cons。
--   虽函数名为 third，请求 URL 为 index-composition?industryCode=，对一级、二级行业代码同样可请求。
--
-- sw_industry_info_di：各级行业一行，含成份个数、估值快照等；raw_json 保留源表全字段。
-- sw_industry_constituent_di：某 trade_date 下，某级行业 × 每只成分股一行；同一股票在不同级行业
--   会重复出现（分别隶属 L1/L2/L3 父节点），属预期行为。
-- ============================================================================

CREATE TABLE IF NOT EXISTS sw_industry_info_di (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    source VARCHAR(64) NOT NULL COMMENT '如 legulegu_sw',
    trade_date DATE NOT NULL COMMENT '快照日',
    level TINYINT NOT NULL COMMENT '1一级/2二级/3三级',
    category_symbol VARCHAR(16) NOT NULL COMMENT 'SW_L1/SW_L2/SW_L3',
    industry_code VARCHAR(16) NOT NULL COMMENT '6位不含.SI',
    industry_code_si VARCHAR(20) NOT NULL COMMENT '如801010.SI',
    industry_name VARCHAR(128) NULL,
    parent_name VARCHAR(128) NULL COMMENT '上级行业名',
    constituent_count INT NULL,
    pe_static DECIMAL(20, 6) NULL,
    pe_ttm DECIMAL(20, 6) NULL,
    pb DECIMAL(20, 6) NULL,
    dividend_yield DECIMAL(20, 6) NULL,
    raw_json JSON NOT NULL,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    UNIQUE KEY uniq_sw_info (source, trade_date, level, industry_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='申万行业信息快照';

CREATE TABLE IF NOT EXISTS sw_industry_constituent_di (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    source VARCHAR(64) NOT NULL,
    trade_date DATE NOT NULL,
    level TINYINT NOT NULL,
    industry_code VARCHAR(16) NOT NULL COMMENT '所属行业6位',
    industry_name VARCHAR(128) NULL,
    stock_code VARCHAR(16) NOT NULL,
    stock_name VARCHAR(64) NULL,
    sort_no INT NULL,
    include_date VARCHAR(32) NULL,
    raw_json JSON NOT NULL,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    UNIQUE KEY uniq_sw_cons (source, trade_date, level, industry_code, stock_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='申万行业成分股';

-- ============================================================================
-- 【行业资金流衍生指标】计算方法（表 industry_fund_flow_derivative_di）
-- 实现脚本：industry_indicator/industry_fund_flow_derivative_etl.py
--
-- 1) 行业资金趋势强度（Trend Score）
--    公式：Trend = MA(主力净流入, 5) / MA(主力净流入, 20)
--    说明：5日移动平均与20日移动平均的比值，反映短期资金趋势相对于中期趋势的强度
--
-- 2) 资金连续流入天数（Persistence）
--    公式：连续N天主净流入 > 0
--    说明：统计行业连续出现主力资金净流入的天数
--
-- 3) 资金强度（Flow Intensity）
--    公式：主力净流入 / 行业成交额
--    说明：主力资金流入相对于行业总成交额的占比，反映资金流入的强度
--
-- 4) 背离指标（Divergence）
--    规则：
--    - 主力净流入、价格上涨 → 正常上涨
--    - 主力净流入、价格下跌 → 低吸机会
--    - 主力净流出、价格上涨 → 出货信号
--    - 主力净流出、价格下跌 → 下跌趋势
--
-- 5) 排名相关指标
--    - 连续Top3天数：行业连续进入资金净流入Top3的天数
--    - Top5占比：当日资金净流入Top5行业的总流入占所有行业总流入的比例
--    - 排名变化（ΔRank）：当日排名与前一交易日排名的变化
--
-- 6) 龙头资金集中度
--    公式：Top5市值股票资金流入 / 行业总流入
--    说明：反映行业资金是否主要集中在龙头股
--
-- 7) 龙头资金流入占比
--    说明：龙头股资金流入占行业总资金流入的比例
--
-- 8) 资金加速度
--    公式：ΔFlow = 今日流入 - 昨日流入
--    说明：资金流入的变化率，反映资金流入的速度变化
--
-- 9) 跨周期资金
--    说明：判断日/周/月是否同时出现资金流入
-- ============================================================================

CREATE TABLE IF NOT EXISTS industry_fund_flow_derivative_di (
    id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '自增主键',
    source VARCHAR(64) NOT NULL COMMENT '数据来源',
    trade_date DATE NOT NULL COMMENT '数据日期',
    industry_code VARCHAR(32) NULL COMMENT '行业代码',
    industry_name VARCHAR(128) NOT NULL COMMENT '行业名称',
    trend_score DECIMAL(20, 6) NULL COMMENT '行业资金趋势强度: MA(主力净流入, 5) / MA(主力净流入, 20)',
    persistence_days INT NULL COMMENT '资金连续流入天数: 连续N天主净流入 > 0',
    flow_intensity DECIMAL(20, 6) NULL COMMENT '资金强度: 主力净流入 / 行业成交额',
    divergence VARCHAR(32) NULL COMMENT '背离指标: 正常上涨/低吸机会/出货信号/下跌趋势',
    consecutive_top3_days INT NULL COMMENT '连续Top3天数',
    top5_ratio DECIMAL(20, 6) NULL COMMENT 'Top5占比',
    rank_change INT NULL COMMENT '排名变化(ΔRank)',
    leading_fund_concentration DECIMAL(20, 6) NULL COMMENT '龙头资金集中度: Top5市值股票资金流入 / 行业总流入',
    leading_fund_ratio DECIMAL(20, 6) NULL COMMENT '龙头资金流入占比',
    fund_acceleration DECIMAL(20, 6) NULL COMMENT '资金加速度: 今日流入 - 昨日流入',
    cross_period_flow VARCHAR(32) NULL COMMENT '跨周期资金: 日/周/月同时流入',
    raw_json JSON NOT NULL COMMENT '原始数据JSON',
    created_at DATETIME NOT NULL COMMENT '创建时间',
    updated_at DATETIME NOT NULL COMMENT '更新时间',
    UNIQUE KEY uniq_industry_derivative (trade_date, industry_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='行业资金流衍生指标日报';


-- ============================================================================
-- A 股财务数据明细 stock_financial_report_di
-- 脚本：financial_sync/stock_financial_full_etl.py
-- 环境变量：STOCK_FINANCIAL_REPORT_TABLE（默认 stock_financial_report_di）
--
-- 设计说明：
--   按 (source, ts_code, report_date, data_kind) 唯一键存储每期一条 JSON，
--   兼容 Tushare 财务指标与东方财富 H10 多类报表字段差异，避免频繁改表结构。
--
-- source / data_kind 常见取值：
--   tushare_fina_indicator / fina_indicator  — Tushare pro.fina_indicator（需接口权限）
--   akshare_em_main / main_indicator         — 东方财富主要财务指标（按报告期）
--   akshare_em_balance / balance_sheet       — 资产负债表（可选，极慢）
--   akshare_em_profit / profit_sheet         — 利润表
--   akshare_em_cashflow / cash_flow          — 现金流量表
--
-- 报告期过滤：仅入库 report_date >= --start-date（默认 2020-01-01）。
-- ============================================================================

CREATE TABLE IF NOT EXISTS stock_financial_report_di (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    source VARCHAR(64) NOT NULL COMMENT '数据源标识,见本文件说明块',
    ts_code VARCHAR(16) NOT NULL COMMENT 'Tushare 风格代码如 600519.SH',
    stock_name VARCHAR(128) NULL,
    report_date DATE NOT NULL COMMENT '报告期截止日',
    data_kind VARCHAR(48) NOT NULL COMMENT 'fina_indicator/main_indicator/三大表等',
    raw_json JSON NOT NULL COMMENT '该期接口返回行序列化',
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    UNIQUE KEY uniq_sfr (source, ts_code, report_date, data_kind)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='A股财务多源明细';

-- ============================================================================
-- 交易日维度表 trading_day_di
-- 脚本：trading_day/trading_day_etl.py
--
-- 设计说明：
--   存储历史和未来的交易日信息，用于数据处理时判断日期是否为交易日。
--   包含日期、是否交易日、星期、月份、季度、年份等维度信息。
-- ============================================================================

CREATE TABLE IF NOT EXISTS trading_day_di (
    id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '自增主键',
    trade_date DATE NOT NULL COMMENT '日期',
    is_trading_day INT NOT NULL COMMENT '是否交易日: 1=是, 0=否',
    week INT NULL COMMENT '星期: 1=周一, 7=周日',
    month INT NULL COMMENT '月份',
    quarter INT NULL COMMENT '季度',
    year INT NULL COMMENT '年份',
    created_at DATETIME NOT NULL COMMENT '创建时间',
    updated_at DATETIME NOT NULL COMMENT '更新时间',
    UNIQUE KEY uniq_trade_date (trade_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='交易日维度表';

-- ============================================================================
-- 【同花顺行业数据】计算方法（表 ths_industry_di）
-- 实现脚本：industry_indicator/ths_industry_etl.py
--
-- 1) 行业代码（industry_code）
--    说明：如果同花顺API返回行业代码则使用，否则生成THS_开头的行业代码
--
-- 2) 行业名称（industry_name）
--    说明：同花顺API返回的行业名称
--
-- 3) 成交量（volume）
--    说明：同花顺API返回的行业成交量，单位为手
--
-- 4) 成交额（amount）
--    说明：同花顺API返回的行业成交额，单位为万元
--
-- 5) 涨跌幅（change_pct）
--    说明：同花顺API返回的行业涨跌幅，单位为%
-- ============================================================================

CREATE TABLE IF NOT EXISTS ths_industry_di (
    id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '自增主键',
    trade_date DATE NOT NULL COMMENT '数据日期',
    industry_code VARCHAR(32) NOT NULL COMMENT '行业代码',
    industry_name VARCHAR(128) NOT NULL COMMENT '行业名称',
    volume DECIMAL(20, 2) NULL COMMENT '成交量（手）',
    amount DECIMAL(20, 2) NULL COMMENT '成交额（万元）',
    change_pct DECIMAL(10, 4) NULL COMMENT '涨跌幅（%）',
    raw_json JSON NOT NULL COMMENT '原始数据JSON',
    created_at DATETIME NOT NULL COMMENT '创建时间',
    updated_at DATETIME NOT NULL COMMENT '更新时间',
    UNIQUE KEY uniq_ths_industry (trade_date, industry_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='同花顺行业数据日报';
