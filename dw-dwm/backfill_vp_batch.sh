#!/bin/bash
# =============================================================================
# VP 六维指标历史回溯（按 ods_trading_day 升序逐日 run_batch）
#
# 用法:
#   bash dw-dwm/backfill_vp_batch.sh
#   bash dw-dwm/backfill_vp_batch.sh 20260101 20260710
#   bash dw-dwm/backfill_vp_batch.sh 20260101 20260710 --skip-existing
#   bash dw-dwm/backfill_vp_batch.sh --start 20260101 --end 20260710
#   run_vp_backfill
#   run_vp_backfill 20260101 20260710
#
# 说明:
#   · 默认 --start 20260101，--end 为 ods_stock_detail_di 最大交易日
#   · 必须按时间顺序跑；中断可用 --skip-existing 续跑
#   · 日志: ${STOCK_LOG_DIR}/backfill_vp/backfill_vp_YYYYMMDD_HHMMSS.log
# =============================================================================
if [ -z "${BASH_VERSION:-}" ]; then
  exec bash "$0" "$@"
fi

set -euo pipefail

SCRIPT_PATH="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DW_ROOT="$(cd "${SCRIPT_PATH}/.." && pwd)"
# shellcheck source=/dev/null
source "${DW_ROOT}/dw-utils/func.sh"

PY_ARGS=(--start 20260101)
if [[ $# -gt 0 && "$1" != --* ]]; then
  PY_ARGS=(--start "$1")
  shift
  if [[ $# -gt 0 && "$1" != --* ]]; then
    PY_ARGS+=(--end "$1")
    shift
  fi
fi
PY_ARGS+=("$@")

LOG_DIR="${STOCK_LOG_DIR:-/root/log/stock_log}/backfill_vp"
mkdir -p "${LOG_DIR}"
LOG_FILE="${LOG_DIR}/backfill_vp_$(date '+%Y%m%d_%H%M%S').log"

export PYTHONPATH="${DW_ROOT}:${DW_ROOT}/dw-utils:${DW_ROOT}/dw-sync:${PYTHONPATH:-}"

echo "日志: ${LOG_FILE}" >&2
echo "======== $(date '+%F %T') backfill_vp ${PY_ARGS[*]} ========" | tee -a "${LOG_FILE}"

set +e
"${PYTHON_BIN}" -m etl.volume_price.backfill "${PY_ARGS[@]}" 2>&1 | tee -a "${LOG_FILE}"
rc=${PIPESTATUS[0]}
set -e

echo "======== DONE exit=${rc} ========" | tee -a "${LOG_FILE}"
exit "${rc}"
