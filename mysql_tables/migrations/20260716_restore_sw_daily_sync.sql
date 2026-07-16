-- =============================================================================
-- 恢复申万行业日线同步（供板块轮动）2026-07-16
--
-- 前置：若 ods_industry_daily_di 曾被 DROP，会按 stock_data.sql 重建。
-- 用法：
--   mysql -u root -p < mysql_tables/migrations/20260716_restore_sw_daily_sync.sql
-- 回填（生产）:
--   source dw-utils/func.sh && run_data_sync --source-table sw_daily --force
-- =============================================================================

CREATE TABLE IF NOT EXISTS stock_data.ods_industry_daily_di (
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

UPDATE data_config.db_sync_task
SET status = 1,
    remark = CONCAT(
        IFNULL(NULLIF(TRIM(TRAILING ' 【已停用 2026-07-15 现网未用】' FROM remark), ''), IFNULL(remark, '')),
        ' 【已恢复 2026-07-16 板块轮动】'
    )
WHERE source_table = 'sw_daily'
   OR target_table = 'ods_industry_daily_di';

SELECT
    id,
    source_table,
    target_table,
    schedule_type,
    status,
    LEFT(remark, 100) AS remark_prefix
FROM data_config.db_sync_task
WHERE source_table = 'sw_daily' OR target_table = 'ods_industry_daily_di';
