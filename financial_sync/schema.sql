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
