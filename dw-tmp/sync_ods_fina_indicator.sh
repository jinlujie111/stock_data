#!/bin/bash
# =============================================================================
# 回溯同步 ods_fina_indicator（Tushare fina_indicator_vip，按季 period）
# 默认自 20250101 起至今日，UPSERT 写入 stock_data.ods_fina_indicator
#
# 用法（必须用 bash）:
#   bash dw-tmp/sync_ods_fina_indicator.sh
#   bash dw-tmp/sync_ods_fina_indicator.sh --dry-run
#   bash dw-tmp/sync_ods_fina_indicator.sh --start 20250101 --end 20260630
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
exec 1>>"${LOG_PATH}/sync_ods_fina_indicator_${n_date}.log"
exec 2>>"${LOG_PATH}/sync_ods_fina_indicator_${n_date}.log"

echo "======== $(date '+%F %T') sync_ods_fina_indicator ========"

export PYTHONPATH="${DW_ROOT}/dw-utils:${DW_ROOT}/dw-sync:${PYTHONPATH:-}"
cd "${DW_ROOT}"

exec "${PYTHON_BIN}" "${SCRIPT_PATH}/sync_ods_fina_indicator.py" "$@"
