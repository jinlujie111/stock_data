#!/bin/bash
# =============================================================================
# 仅跑需求1：五维 DWM + DWS 主线评分/监控（ODS 已齐时补跑）
#
# 用法:
#   bash dw-utils/xxl_mainline_batch.sh 20260616
#   bash dw-utils/xxl_mainline_batch.sh 20250601 20260616   # 区间
# =============================================================================
if [ -z "${BASH_VERSION:-}" ]; then
  exec bash "$0" "$@"
fi

set -euo pipefail

SCRIPT_PATH="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DW_ROOT="$(cd "${SCRIPT_PATH}/.." && pwd)"
# shellcheck source=/dev/null
source "${DW_ROOT}/dw-utils/func.sh"

n_date_s="$(get_date "${1:-}")"
n_date_e="$(get_date "${2:-${1:-}}")"

echo "======== 需求1 主线批 ${n_date_s} ~ ${n_date_e} $(date '+%F %T') ========"

for cur_date in $(get_continuous_date "${n_date_s}" "${n_date_e}"); do
  if [[ "$(trade_day_flag "${cur_date}")" != "1" ]]; then
    echo "SKIP: ${cur_date} 非交易日"
    continue
  fi
  echo "--- ${cur_date} ---"
  run_dwm_dc_industry_fund_flow "${cur_date}"
  run_dwm_dc_industry_trend_strength "${cur_date}"
  run_dwm_dc_industry_market_heat "${cur_date}"
  run_dwm_dc_industry_diffusion "${cur_date}"
  run_dwm_dc_industry_prosperity "${cur_date}"
  run_dws_dc_industry_mainline_score "${cur_date}"
  run_dws_dc_industry_mainline_monitor "${cur_date}"
done

echo "======== 需求1 主线批完成 ========"
