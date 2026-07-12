#!/bin/bash
# =============================================================================
# 需求5：板块量价关系（VPA）日批
#
# 用法:
#   bash dw-dwm/pro_dwm_industry_vp_score.sh
#   bash dw-dwm/pro_dwm_industry_vp_score.sh 20260630
#   bash dw-dwm/pro_dwm_industry_vp_score.sh 20260630 --content-types 行业,概念
#   或: run_vp_batch 20260630
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

LOG_PATH="${STOCK_LOG_DIR:-/root/log/stock_log}/${n_date}"
mkdir -p "${LOG_PATH}"
LOG_FILE="${LOG_PATH}/pro_dwm_industry_vp_score_${n_date}.log"

export PYTHONPATH="${DW_ROOT}:${DW_ROOT}/dw-utils:${PYTHONPATH:-}"

trade_flag="$(trade_day_flag "${n_date}" 2>/dev/null || echo 0)"
if [[ "${trade_flag}" != "1" ]]; then
  echo "[SKIP] ${n_date} 非交易日，跳过 VPA 批处理"
  exit 0
fi

echo "日志: ${LOG_FILE}" >&2
echo "======== $(date '+%F %T') pro_dwm_industry_vp_score trade_date=${n_date} ========" >>"${LOG_FILE}"

set +e
"${PYTHON_BIN}" -m etl.volume_price.batch "${n_date}" "$@" >>"${LOG_FILE}" 2>&1
rc=$?
set -e

echo "======== DONE exit=${rc} ========" >>"${LOG_FILE}"

if [[ "${rc}" -ne 0 ]]; then
  echo "[ERROR] VPA 批处理失败 exit=${rc}，日志: ${LOG_FILE}" >&2
  tail -25 "${LOG_FILE}" >&2
fi
exit "${rc}"
