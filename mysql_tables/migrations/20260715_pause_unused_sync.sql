-- =============================================================================
-- 暂停现网未使用的 ODS 同步（2026-07-15）
--
-- 范围（幂等，可重复执行；含 disable_unused_heavy 未跑完的任务）:
--   高占用: cyq_chips / fina_mainbz* / ths_*
--   P1 未接入: hk_hold / margin* / top_* / stk_holder*
--   申万链路: sw_daily / index_member_all
--   月批财报: income/cashflow/balancesheet/forecast/express / stock_company
--
-- 用法（生产）:
--   mysql -u root -p < mysql_tables/migrations/20260715_pause_unused_sync.sql
-- =============================================================================

UPDATE data_config.db_sync_task
SET status = 0,
    remark = CONCAT(IFNULL(remark, ''), ' 【已停用 2026-07-15 现网未用】')
WHERE status = 1
  AND (
        source_table IN (
            'cyq_chips',
            'fina_mainbz',
            'fina_mainbz_vip',
            'ths_daily',
            'ths_index',
            'ths_member',
            'ths_hot',
            'hk_hold',
            'margin',
            'margin_detail',
            'top_list',
            'top_inst',
            'stk_holdertrade',
            'stk_holdernumber',
            'sw_daily',
            'index_member_all',
            'stock_company',
            'income_vip',
            'cashflow_vip',
            'balancesheet_vip',
            'forecast_vip',
            'express_vip'
        )
        OR target_table IN (
            'ods_cyq_chips_di',
            'ods_fina_mainbz_di',
            'ods_ths_daily_di',
            'ods_ths_index_di',
            'ods_ths_member_di',
            'ods_ths_hot_di',
            'ods_hk_hold_di',
            'ods_margin_di',
            'ods_margin_detail_di',
            'ods_top_list_di',
            'ods_top_inst_di',
            'ods_stk_holdertrade_di',
            'ods_stk_holdernumber_di',
            'ods_industry_daily_di',
            'ods_index_member_all',
            'ods_stock_company_di',
            'ods_income_di',
            'ods_cashflow_di',
            'ods_balancesheet_di',
            'ods_forecast_di',
            'ods_express_di'
        )
    );

SELECT 'paused_unused_sync_tasks' AS step, ROW_COUNT() AS affected;

SELECT
    id,
    source_table,
    target_table,
    schedule_type,
    status,
    LEFT(remark, 80) AS remark_prefix
FROM data_config.db_sync_task
WHERE source_table IN (
    'hk_hold', 'margin', 'margin_detail', 'top_list', 'top_inst',
    'stk_holdertrade', 'stk_holdernumber', 'sw_daily', 'index_member_all',
    'stock_company', 'income_vip', 'cashflow_vip', 'balancesheet_vip',
    'forecast_vip', 'express_vip',
    'cyq_chips', 'fina_mainbz', 'fina_mainbz_vip',
    'ths_daily', 'ths_index', 'ths_member', 'ths_hot'
)
ORDER BY source_table;

-- 可选：腾盘时 TRUNCATE（磁盘紧张时优先 DROP+CREATE，见 stock_data.sql）
drop table  stock_data.ods_hk_hold_di;
drop table  stock_data.ods_margin_di;
drop table  stock_data.ods_margin_detail_di;
drop table  stock_data.ods_top_list_di;
drop table  stock_data.ods_top_inst_di;
drop table  stock_data.ods_stk_holdertrade_di;
drop table  stock_data.ods_stk_holdernumber_di;
drop table  stock_data.ods_industry_daily_di;
drop table  stock_data.ods_index_member_all;
drop table  stock_data.ods_stock_company_di;
drop table  stock_data.ods_income_di;
drop table  stock_data.ods_cashflow_di;
drop table  stock_data.ods_balancesheet_di;
drop table  stock_data.ods_forecast_di;
drop table  stock_data.ods_express_di;
-- 申万衍生（停批后可清）:
drop table stock_data.dwm_sw_industry_diffusion_di;
drop table stock_data.dwm_sw_industry_prosperity_di;
drop table stock_data.dws_sw_industry_mainline_score_di;
drop table stock_data.dws_sw_industry_mainline_monitor_di;
