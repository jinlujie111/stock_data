#!/bin/bash
# =============================================================================
# 东财板块择时回测（T+1 开盘成交）+ 可选信号 QA
#
# 用法:
#   bash dw-dwm/pro_dwm_board_timing_backtest.sh
#   bash dw-dwm/pro_dwm_board_timing_backtest.sh 20260805
#   bash dw-dwm/pro_dwm_board_timing_backtest.sh 20260101 20260805
#   或: run_board_timing_backtest 20260805
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
  other="$(get_date "${1}")"
  shift || true
  if [[ "${other}" < "${n_date}" ]]; then
    START_ARG="${other}"
    END_ARG="${n_date}"
  else
    START_ARG="${n_date}"
    END_ARG="${other}"
    n_date="${END_ARG}"
  fi
fi

LOG_PATH="${STOCK_LOG_DIR:-/root/log/stock_log}/${n_date}"
mkdir -p "${LOG_PATH}"
LOG_FILE="${LOG_PATH}/pro_dwm_board_timing_backtest_${n_date}.log"

export PYTHONPATH="${DW_ROOT}:${DW_ROOT}/dw-utils:${PYTHONPATH:-}"

if [[ -z "${START_ARG}" ]]; then
  trade_flag="$(trade_day_flag "${n_date}" 2>/dev/null || echo 0)"
  if [[ "${trade_flag}" != "1" ]]; then
    echo "[SKIP] ${n_date} 非交易日，跳过板块择时回测"
    exit 0
  fi
fi

echo "日志: ${LOG_FILE}" >&2
echo "======== $(date '+%F %T') board_timing_backtest end=${n_date} start=${START_ARG:-lookback} ========" | tee -a "${LOG_FILE}" >&2

set +e
if [[ -n "${START_ARG}" ]]; then
  "${PYTHON_BIN}" -u -m etl.board_timing.backtest "${n_date}" "${START_ARG}" "$@" >>"${LOG_FILE}" 2>&1
else
  "${PYTHON_BIN}" -u -m etl.board_timing.backtest "${n_date}" "$@" >>"${LOG_FILE}" 2>&1
fi
rc=$?

# QA 不阻断日批（仅写日志）
"${PYTHON_BIN}" -u -m etl.board_timing.qa "${n_date}" >>"${LOG_FILE}" 2>&1 || true
set -e

echo "======== DONE exit=${rc} ========" | tee -a "${LOG_FILE}" >&2
if [[ "${rc}" -ne 0 ]]; then
  echo "[ERROR] 板块择时回测失败 exit=${rc}，日志: ${LOG_FILE}" >&2
  tail -25 "${LOG_FILE}" >&2
fi
exit "${rc}"
