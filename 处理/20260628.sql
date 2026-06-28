
select trade_date,count(*)
from ods_dc_index_di
group by trade_date
order by trade_date


select *
from ods_dc_member_di
where trade_date = '2026-06-26'


source dw-utils/func.sh
run_data_sync 20260527 --source-table dc_index --force


run_data_sync --source-table fina_indicator_vip --force


select sync_mode
from db_sync_task
where source_table = 'fina_indicator_vip'

update db_sync_task
set sync_mode = 'full'
where source_table = 'fina_indicator_vip'

update db_sync_task
set sync_mode = 'snapshot'
where source_table = 'fina_indicator_vip'

update db_sync_task
set sync_mode = 'snapshot'
where source_table = 'fina_indicator_vip';

-- 2025 年报单季回补（period=20251231，只删 end_date=2025-12-31，不 TRUNCATE 全表）
-- source dw-utils/func.sh && backfill_fina_indicator_period 20251231
-- 或: bash dw-sync/backfill_fina_indicator_period.sh 20251231 --dry-run

source dw-utils/func.sh
backfill_fina_indicator_period 20251231

-- 验证
select end_date, count(distinct ts_code) as stock_cnt
from ods_fina_indicator
where end_date in ('2025-12-31','2025-09-30','2026-03-31')
group by end_date
order by end_date desc;