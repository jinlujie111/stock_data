#!/bin/bash
# =============================================================================
# 东财板块四因子择时信号日批（趋势/资金/量价/情绪 → BUY/SELL）
#
# 用法:
#   bash dw-dwm/pro_dwm_board_timing_signal_di.sh
#   bash dw-dwm/pro_dwm_board_timing_signal_di.sh 20260715
#   bash dw-dwm/pro_dwm_board_timing_signal_di.sh 20260101 20260715
#   或: run_board_timing_batch 20260715
#
# 注意:
#   - 长区间会按月分块，不要与旧进程并行
#   - 卡死时先: pkill -f 'etl.board_timing.batch' ; mysqladmin processlist
# =============================================================================
if [ -z "${BASH_VERSION:-}" ]; then
  exec bash "$0" "$@"
fi

set -euo pipefail

SCRIPT_PATH="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DW_ROOT="$(cd "${SCRIPT_PATH}/.." && pwd)"
# shellcheck source=/dev/null
source "${DW_ROOT}/dw-utils/func.sh"

n_date="$(get_date "${1:-}")"
shift || true

START_ARG=""
if [[ $# -ge 1 && "${1}" =~ ^[0-9]{8}$ ]]; then
  # 兼容: end start  或  start end（取较小为 start）
  other="$(get_date "${1}")"
  shift || true
  if [[ "${other}" < "${n_date}" ]]; then
    START_ARG="${other}"
    END_ARG="${n_date}"
  else
    START_ARG="${n_date}"
    END_ARG="${other}"
  fi
  n_date="${END_ARG}"
fi

LOG_PATH="${STOCK_LOG_DIR:-/root/log/stock_log}/${n_date}"
mkdir -p "${LOG_PATH}"
LOG_FILE="${LOG_PATH}/pro_dwm_board_timing_signal_${n_date}.log"

export PYTHONPATH="${DW_ROOT}:${DW_ROOT}/dw-utils:${PYTHONPATH:-}"

# 区间回填：不因「结束日非交易日」整段跳过；单日仍检查
if [[ -z "${START_ARG}" ]]; then
  trade_flag="$(trade_day_flag "${n_date}" 2>/dev/null || echo 0)"
  if [[ "${trade_flag}" != "1" ]]; then
    echo "[SKIP] ${n_date} 非交易日，跳过板块择时批处理"
    exit 0
  fi
fi

# 若已有同脚本在跑，拒绝再开（避免 & 双开卡死）
if pgrep -f 'etl.board_timing.batch' >/dev/null 2>&1; then
  echo "[ERROR] 已有 etl.board_timing.batch 在运行，请先:" >&2
  echo "  pkill -f 'etl.board_timing.batch'" >&2
  echo "  # 并检查 MySQL: SHOW FULL PROCESSLIST;" >&2
  exit 1
fi

echo "日志: ${LOG_FILE}" >&2
echo "======== $(date '+%F %T') pro_dwm_board_timing_signal end=${n_date} start=${START_ARG:-same} ========" | tee -a "${LOG_FILE}" >&2

set +e
if [[ -n "${START_ARG}" ]]; then
  "${PYTHON_BIN}" -u -m etl.board_timing.batch "${n_date}" "${START_ARG}" "$@" >>"${LOG_FILE}" 2>&1
else
  "${PYTHON_BIN}" -u -m etl.board_timing.batch "${n_date}" "$@" >>"${LOG_FILE}" 2>&1
fi
rc=$?
set -e

echo "======== DONE exit=${rc} ========" | tee -a "${LOG_FILE}" >&2

if [[ "${rc}" -ne 0 ]]; then
  echo "[ERROR] 板块择时批处理失败 exit=${rc}，日志: ${LOG_FILE}" >&2
  tail -25 "${LOG_FILE}" >&2
fi
exit "${rc}"
