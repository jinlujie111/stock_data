#!/bin/bash
# =============================================================================
# 回填 stk_high_shock / stk_alert（按 ods_trading_day 逐日同步）
#
# 用法:
#   bash dw-sync/backfill_stk_high_shock_alert.sh
#   bash dw-sync/backfill_stk_high_shock_alert.sh 20250101
#   bash dw-sync/backfill_stk_high_shock_alert.sh 20250101 20260807
#   bash dw-sync/backfill_stk_high_shock_alert.sh 20250101 20260807 --dry-run
#   source dw-utils/func.sh && run_backfill_stk_shock_alert
#
# 说明:
#   · 默认 start=20250101，end=今天（按交易日历取区间内交易日）
#   · 依次补 stk_high_shock、stk_alert（需 db_sync_task status=1 且 ODS 表已建）
#   · 约需 6000 积分；日量不大，但交易日多，注意限流与中断后续跑
#   · 日志: ${STOCK_LOG_DIR}/backfill_stk_shock_alert/backfill_*.log
# =============================================================================
if [ -z "${BASH_VERSION:-}" ]; then
  exec bash "$0" "$@"
fi

set -euo pipefail

SCRIPT_PATH="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DW_ROOT="$(cd "${SCRIPT_PATH}/.." && pwd)"
# shellcheck source=/dev/null
source "${DW_ROOT}/dw-utils/func.sh"

START_DATE="20250101"
END_DATE="$(date '+%Y%m%d')"
EXTRA_ARGS=()

if [[ $# -gt 0 && "$1" != --* ]]; then
  START_DATE="$(get_date "$1")"
  shift
  if [[ $# -gt 0 && "$1" != --* ]]; then
    END_DATE="$(get_date "$1")"
    shift
  fi
fi

while [[ $# -gt 0 ]]; do
  EXTRA_ARGS+=("$1")
  shift
done

# 始终带 --force：区间补数由 sync_data 按交易日列表驱动
HAS_FORCE=0
if [[ ${#EXTRA_ARGS[@]} -gt 0 ]]; then
  for a in "${EXTRA_ARGS[@]}"; do
    if [[ "$a" == "--force" ]]; then
      HAS_FORCE=1
      break
    fi
  done
fi
if [[ "${HAS_FORCE}" -eq 0 ]]; then
  EXTRA_ARGS+=(--force)
fi

LOG_DIR="${STOCK_LOG_DIR:-/root/log/stock_log}/backfill_stk_shock_alert"
mkdir -p "${LOG_DIR}"
LOG_FILE="${LOG_DIR}/backfill_${START_DATE}_${END_DATE}_$(date '+%Y%m%d_%H%M%S').log"

echo "日志: ${LOG_FILE}" >&2
echo "======== $(date '+%F %T') backfill stk_high_shock/stk_alert ${START_DATE} ~ ${END_DATE} ========" | tee -a "${LOG_FILE}"

SOURCES=(stk_high_shock stk_alert)
FAIL=0

for src in "${SOURCES[@]}"; do
  echo "—— $(date '+%F %T') 开始 ${src} ${START_DATE} ~ ${END_DATE} ——" | tee -a "${LOG_FILE}"
  set +e
  bash "${DW_ROOT}/dw-sync/sync_runner.sh" "${START_DATE}" \
    --end-date "${END_DATE}" \
    --source-table "${src}" \
    "${EXTRA_ARGS[@]}" \
    2>&1 | tee -a "${LOG_FILE}"
  rc=${PIPESTATUS[0]}
  set -e
  if [[ "${rc}" -ne 0 ]]; then
    echo "ERROR: ${src} 回填失败 exit=${rc}" | tee -a "${LOG_FILE}"
    FAIL=1
  else
    echo "OK: ${src} 回填完成" | tee -a "${LOG_FILE}"
  fi
done

echo "======== DONE fail=${FAIL} ========" | tee -a "${LOG_FILE}"
exit "${FAIL}"
