#!/bin/bash
# VP 批次数据核查：bash dw-dwm/verify_vp_batch_data.sh 20260710
if [ -z "${BASH_VERSION:-}" ]; then exec bash "$0" "$@"; fi
set -euo pipefail
SCRIPT_PATH="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DW_ROOT="$(cd "${SCRIPT_PATH}/.." && pwd)"
# shellcheck source=/dev/null
source "${DW_ROOT}/dw-utils/func.sh"
n_date="$(get_date "${1:-20260710}")"
export PYTHONPATH="${DW_ROOT}:${DW_ROOT}/dw-utils:${PYTHONPATH:-}"
LOG="${STOCK_LOG_DIR:-/root/log/stock_log}/${n_date}/pro_dwm_industry_vp_score_${n_date}.log"
echo "=== VP 核查 trade_date=${n_date} ==="
if [[ -f "${LOG}" ]]; then
  echo "--- 批处理日志 (末 15 行) ---"
  tail -15 "${LOG}" || true
else
  echo "[WARN] 无日志: ${LOG}"
fi
echo "--- Python 核查 ---"
"${PYTHON_BIN}" "${DW_ROOT}/etl/volume_price/verify_batch_data.py" "${n_date}"
