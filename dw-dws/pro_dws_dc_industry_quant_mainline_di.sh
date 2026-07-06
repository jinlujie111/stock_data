#!/bin/bash
# =============================================================================
# target_table: dws_dc_industry_quant_mainline_di, dws_dc_industry_quant_mainline_signal_di
# 东财 FTELP 量化主线（需求3）：Top3 + 启动/退潮信号
#
# 用法:
#   bash dw-dws/pro_dws_dc_industry_quant_mainline_di.sh
#   bash dw-dws/pro_dws_dc_industry_quant_mainline_di.sh 20260616
#   bash dw-dws/pro_dws_dc_industry_quant_mainline_di.sh 20260616 "行业,概念"
#   run_dws_dc_industry_quant_mainline 20260616   # 先 source dw-utils/func.sh
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
content_types="${2:-${QUANT_MAINLINE_CONTENT_TYPES:-行业,概念}}"

LOG_PATH="${STOCK_LOG_DIR:-/root/log/stock_log}/${n_date}"
mkdir -p "${LOG_PATH}"
exec 1>>"${LOG_PATH}/pro_dws_dc_industry_quant_mainline_di_${n_date}.log"
exec 2>>"${LOG_PATH}/pro_dws_dc_industry_quant_mainline_di_${n_date}.log"

echo "======== $(date '+%F %T') pro_dws_dc_industry_quant_mainline ${n_date} types=${content_types} ========"

export PYTHONPATH="${DW_ROOT}:${DW_ROOT}/dw-utils:${PYTHONPATH:-}"

"${PYTHON_BIN}" -m etl.quant_mainline.batch "${n_date}" --content-types "${content_types}"

echo "DONE pro_dws_dc_industry_quant_mainline ${n_date}"
