-- ============================================================================
-- xxl-job 调度：stock_data 数据源同步（trading_day + stock_fund_flow）
-- 用法：source utils/func.sh && init_xxl_job_stock_sync
-- ============================================================================

USE xxl_job;

INSERT INTO xxl_job_group (app_name, title, address_type, address_list, update_time)
SELECT 'stock-data-sync', 'stock_data 数据同步', 0, NULL, NOW()
FROM DUAL
WHERE NOT EXISTS (
    SELECT 1 FROM xxl_job_group WHERE app_name = 'stock-data-sync'
);

SET @job_group_id := (
    SELECT id FROM xxl_job_group WHERE app_name = 'stock-data-sync' LIMIT 1
);

DELETE FROM xxl_job_info
WHERE job_group = @job_group_id
  AND job_desc LIKE '[stock_sync]%';

-- 每日 08:00 交易日历
INSERT INTO xxl_job_info (
    job_group, job_desc, add_time, update_time, author,
    schedule_type, schedule_conf, misfire_strategy,
    executor_route_strategy, executor_handler, executor_param,
    executor_block_strategy, executor_timeout, executor_fail_retry_count,
    glue_type, glue_source, glue_remark, glue_updatetime,
    trigger_status
) VALUES (
    @job_group_id,
    '[stock_sync] 交易日维度 trading_day',
    NOW(), NOW(), 'stock_data',
    'CRON', '0 0 8 * * ?', 'DO_NOTHING',
    'FIRST', '', '',
    'SERIAL_EXECUTION', 3600, 1,
    'GLUE(Shell)',
    '#!/bin/bash
set -euo pipefail
ROOT="${STOCK_DATA_ROOT:?请配置 STOCK_DATA_ROOT}"
TD="$(date +%Y%m%d)"
exec bash "${ROOT}/sync/sync_runner.sh" "${TD}" --task-code trading_day
',
    'sync_runner.sh --task-code trading_day',
    NOW(),
    1
);

-- 工作日 19:00 个股资金流（即时）
INSERT INTO xxl_job_info (
    job_group, job_desc, add_time, update_time, author,
    schedule_type, schedule_conf, misfire_strategy,
    executor_route_strategy, executor_handler, executor_param,
    executor_block_strategy, executor_timeout, executor_fail_retry_count,
    glue_type, glue_source, glue_remark, glue_updatetime,
    trigger_status
) VALUES (
    @job_group_id,
    '[stock_sync] 个股资金流 stock_fund_flow',
    NOW(), NOW(), 'stock_data',
    'CRON', '0 0 19 ? * MON-FRI', 'DO_NOTHING',
    'FIRST', '', '',
    'SERIAL_EXECUTION', 3600, 1,
    'GLUE(Shell)',
    '#!/bin/bash
set -euo pipefail
ROOT="${STOCK_DATA_ROOT:?请配置 STOCK_DATA_ROOT}"
TD="$(date +%Y%m%d)"
exec bash "${ROOT}/sync/sync_runner.sh" "${TD}" --task-code stock_fund_flow
',
    'sync_runner.sh --task-code stock_fund_flow',
    NOW(),
    1
);
