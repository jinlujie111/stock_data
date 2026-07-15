#!/bin/bash
# =============================================================================
# target_table: data_industry.quant_signal_di
# 量化选股每日信号：对所有启用策略打分选股并标注买卖点
#
# 用法:
#   bash dw-dwm/pro_dwm_quant_signal_di.sh                 # 最新交易日
#   bash dw-dwm/pro_dwm_quant_signal_di.sh 20260714        # 指定交易日
#   bash dw-dwm/pro_dwm_quant_signal_di.sh 20260101 20260714  # 区间回填
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

LOG_PATH="${STOCK_LOG_DIR:-/root/log/stock_log}/${n_date}"
mkdir -p "${LOG_PATH}"
LOG_FILE="${LOG_PATH}/pro_dwm_quant_signal_${n_date}.log"

export PYTHONPATH="${DW_ROOT}:${DW_ROOT}/dw-utils:${PYTHONPATH:-}"

trade_flag="$(trade_day_flag "${n_date}" 2>/dev/null || echo 0)"
if [[ "${trade_flag}" != "1" && -z "${2:-}" ]]; then
  echo "[SKIP] ${n_date} 非交易日，跳过量化信号"
  exit 0
fi

echo "日志: ${LOG_FILE}" >&2
echo "======== $(date '+%F %T') pro_dwm_quant_signal args=$* ========" >>"${LOG_FILE}"

set +e
"${PYTHON_BIN}" -m etl.quant.batch "$@" >>"${LOG_FILE}" 2>&1
rc=$?
set -e

echo "======== DONE exit=${rc} ========" >>"${LOG_FILE}"

if [[ "${rc}" -ne 0 ]]; then
  echo "[ERROR] 量化信号失败 exit=${rc}，日志: ${LOG_FILE}" >&2
  tail -25 "${LOG_FILE}" >&2
fi
exit "${rc}"
