#!/bin/bash
# =============================================================================
# 申万一级行业板块轮动每日信号 → stock_data.rotation_signal_di
#
# 依赖: sw_daily(ods_industry_daily_di) + moneyflow_ind_dc(ods_industry_fund_flow_di)
# XXL: 建议在 run_data_sync 之后、与量化选股同级执行
#
# 用法:
#   bash dw-dwm/pro_dwm_rotation_signal_di.sh
#   bash dw-dwm/pro_dwm_rotation_signal_di.sh 20260715
#   bash dw-dwm/pro_dwm_rotation_signal_di.sh 20260101 20260715
# =============================================================================
if [ -z "${BASH_VERSION:-}" ]; then
  exec bash "$0" "$@"
fi

set -euo pipefail

SCRIPT_PATH="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DW_ROOT="$(cd "${SCRIPT_PATH}/.." && pwd)"
# shellcheck source=/dev/null
source "${DW_ROOT}/dw-utils/func.sh"

# 无参：最新交易日；一参：单日；两参：区间
if [[ $# -ge 2 ]]; then
  start_arg="$1"
  end_arg="$2"
  n_date="$(get_date "${end_arg}")"
elif [[ $# -eq 1 ]]; then
  start_arg="$1"
  end_arg="$1"
  n_date="$(get_date "${1}")"
else
  start_arg=""
  end_arg=""
  n_date="$(get_date "")"
fi

LOG_PATH="${STOCK_LOG_DIR:-/root/log/stock_log}/${n_date}"
mkdir -p "${LOG_PATH}"
LOG_FILE="${LOG_PATH}/pro_dwm_rotation_signal_${n_date}.log"

export PYTHONPATH="${DW_ROOT}:${DW_ROOT}/dw-utils:${PYTHONPATH:-}"

echo "======== $(date '+%F %T') pro_dwm_rotation_signal start=${start_arg:-latest} end=${end_arg:-latest} ========" | tee -a "${LOG_FILE}"
echo "PYTHON_BIN=${PYTHON_BIN}" | tee -a "${LOG_FILE}"

set +e
if [[ -n "${start_arg}" && -n "${end_arg}" ]]; then
  "${PYTHON_BIN}" -m etl.sector_rotation.signal_batch "${start_arg}" "${end_arg}" >>"${LOG_FILE}" 2>&1
else
  "${PYTHON_BIN}" -m etl.sector_rotation.signal_batch >>"${LOG_FILE}" 2>&1
fi
rc=$?
set -e

echo "======== DONE exit=${rc} $(date '+%F %T') ========" | tee -a "${LOG_FILE}"

if [[ "${rc}" -ne 0 ]]; then
  echo "[ERROR] 板块轮动信号失败 exit=${rc}，日志: ${LOG_FILE}" >&2
  tail -30 "${LOG_FILE}" >&2
fi
exit "${rc}"
