-- =============================================================================
-- 停用并清空高占用、现网不用的表（2026-07-15）
--
-- 目标表:
--   ods_cyq_chips_di
--   ods_fina_mainbz_di
--   ods_ths_daily_di（并停同花顺相关同步，避免日批 THS DWM 空转灌数）
--   dwm_industry_stock_ai_score_di
--   dws_dc_industry_quant_mainline_di
--   dws_dc_industry_quant_mainline_signal_di
--
-- 用法（生产）:
--   mysql -u root -p < mysql_tables/migrations/20260715_disable_unused_heavy_tables.sql
--
-- 注意:
--   TRUNCATE 在空间极紧时可能仍无法缩 .ibd；若 mb 不变，对该表改用 DROP + CREATE
--   （DDL 见 mysql_tables/stock_data.sql）
-- =============================================================================

-- 1) 停同步（data_config.db_sync_task）
UPDATE data_config.db_sync_task
SET status = 0,
    remark = CONCAT(IFNULL(remark, ''), ' 【已停用 2026-07-15 腾盘/现网未用】')
WHERE status = 1
  AND (
        source_table IN (
            'cyq_chips',
            'fina_mainbz',
            'fina_mainbz_vip',
            'ths_daily',
            'ths_index',
            'ths_member',
            'ths_hot'
        )
        OR target_table IN (
            'ods_cyq_chips_di',
            'ods_fina_mainbz_di',
            'ods_ths_daily_di',
            'ods_ths_index_di',
            'ods_ths_member_di',
            'ods_ths_hot_di'
        )
    );

SELECT 'disabled_sync_tasks' AS step, ROW_COUNT() AS affected;

-- 2) 清空业务库表（立即停止占逻辑行；空间回收视 InnoDB/磁盘余量）
TRUNCATE TABLE stock_data.ods_cyq_chips_di;
TRUNCATE TABLE stock_data.ods_fina_mainbz_di;
TRUNCATE TABLE stock_data.ods_ths_daily_di;
TRUNCATE TABLE stock_data.dwm_industry_stock_ai_score_di;

-- quant 主线衍生表：若库中不存在会报错，可注释对应行
TRUNCATE TABLE stock_data.dws_dc_industry_quant_mainline_di;
TRUNCATE TABLE stock_data.dws_dc_industry_quant_mainline_signal_di;

-- 可选：同花顺其它 ODS（已停同步）一并清空
-- TRUNCATE TABLE stock_data.ods_ths_index_di;
-- TRUNCATE TABLE stock_data.ods_ths_member_di;
-- TRUNCATE TABLE stock_data.ods_ths_hot_di;

SELECT
    table_name,
    ROUND((data_length + index_length) / 1024 / 1024, 1) AS mb,
    table_rows
FROM information_schema.tables
WHERE table_schema = 'stock_data'
  AND table_name IN (
        'ods_cyq_chips_di',
        'ods_fina_mainbz_di',
        'ods_ths_daily_di',
        'dwm_industry_stock_ai_score_di',
        'dws_dc_industry_quant_mainline_di',
        'dws_dc_industry_quant_mainline_signal_di'
  )
ORDER BY mb DESC;

