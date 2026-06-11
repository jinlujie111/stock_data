#!/bin/bash
# =============================================================================
# ODS 历史数据回补入口（默认 20250101 ~ 昨日）
#
# 用法（必须用 bash）:
#   bash dw-tmp/sync_ods_history.sh
#   bash dw-tmp/sync_ods_history.sh --dry-run
#   bash dw-tmp/sync_ods_history.sh --start 20250101 --end 20260609
#   bash dw-tmp/sync_ods_history.sh --tables ods_stock_detail_di,ods_limit_list_di
#   bash dw-tmp/sync_ods_history.sh --only-snapshot --continue-on-error
#   bash dw-tmp/sync_ods_history.sh --tables ods_dc_daily_di --sleep-task 2 --sleep-day 1
#
# 休眠/重试（秒；func.sh 默认 timeout=90 retries=3）：
#   --sleep-task  每次任务（表×交易日）完成后
#   --sleep-day   每个交易日全部 snapshot 完成后（额外）
#   --sleep-full  每张 full 表完成后（额外）
#   --sleep-fina  fina_indicator 每季 API 间隔
#   --retry       超时后整任务重试次数（默认 2，即最多 3 次）
#   --retry-sleep 整任务重试间隔基数（默认 10s，逐次递增）
# 环境变量：TUSHARE_HTTP_TIMEOUT TUSHARE_FETCH_RETRIES TUSHARE_FETCH_RETRY_SLEEP
#
# 说明：
#   - 全量 22 表逐日回补 API 量极大，建议按 --tables 分批或夜间跑
#   - ods_fina_indicator 走按季 period 逻辑（非逐日 ann_date）
#   - 热榜类（dc_hot/ths_hot）历史日可能无数据，可 --continue-on-error
# =============================================================================
if [ -z "${BASH_VERSION:-}" ]; then
  exec bash "$0" "$@"
fi

set -euo pipefail

SCRIPT_PATH="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DW_ROOT="$(cd "${SCRIPT_PATH}/.." && pwd)"
# shellcheck source=/dev/null
source "${DW_ROOT}/dw-utils/func.sh"

n_date="$(date +%Y%m%d)"
LOG_PATH="/root/log/stock_log/${n_date}"
mkdir -p "${LOG_PATH}"
exec 1>>"${LOG_PATH}/sync_ods_history_${n_date}.log"
exec 2>>"${LOG_PATH}/sync_ods_history_${n_date}.log"

echo "======== $(date '+%F %T') sync_ods_history ========"

export PYTHONPATH="${DW_ROOT}/dw-utils:${DW_ROOT}/dw-sync:${DW_ROOT}/dw-tmp:${PYTHONPATH:-}"
cd "${DW_ROOT}"

exec "${PYTHON_BIN}" "${SCRIPT_PATH}/sync_ods_history.py" "$@"
