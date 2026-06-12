#!/bin/bash
# =============================================================================
# DWM 层历史数据回补入口（默认 20250101 ~ 昨日）
#
# 用法（必须用 bash）:
#   bash dw-tmp/run_dwm_history.sh
#   bash dw-tmp/run_dwm_history.sh --start 20250101 --end 20260609
#   bash dw-tmp/run_dwm_history.sh --group dc
#   bash dw-tmp/run_dwm_history.sh --jobs market_breadth,dc_fund_flow,dc_trend
#   bash dw-tmp/run_dwm_history.sh --list-jobs
#   bash dw-tmp/run_dwm_history.sh --sleep-job 3
#   bash dw-tmp/run_dwm_history.sh --strict   # 遇错即停（默认会继续跑后续任务）
#
# 说明：
#   - 先确保 ODS 层对应日期已回补（尤其 stock_detail、板块行情/成分、财务等）
#   - 各 pro_dwm_*.sh 按自然日循环，ODS 无数据日会自动 skip
#   - 扩散类依赖 dwm_market_breadth_di，编排顺序已内置
#   - 单任务详细日志仍在 /root/log/stock_log/{end_date}/pro_dwm_*_{end_date}.log
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
exec 1>>"${LOG_PATH}/run_dwm_history_${n_date}.log"
exec 2>>"${LOG_PATH}/run_dwm_history_${n_date}.log"

echo "======== $(date '+%F %T') run_dwm_history ========"

export PYTHONPATH="${DW_ROOT}/dw-utils:${DW_ROOT}/dw-tmp:${PYTHONPATH:-}"
cd "${DW_ROOT}"

exec "${PYTHON_BIN}" "${SCRIPT_PATH}/run_dwm_history.py" "$@"
