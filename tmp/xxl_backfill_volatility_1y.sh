#!/bin/bash
# =============================================================================
# 一次性：近 1 年大盘/东财板块年化波动率历史回填
#
# 用法:
#   cd /opt/stock_data
#   bash tmp/xxl_backfill_volatility_1y.sh
#   bash tmp/xxl_backfill_volatility_1y.sh 20250707 20260707
#
# XXL-JOB GLUE Shell:
#   cd /opt/stock_data && bash tmp/xxl_backfill_volatility_1y.sh ${executorParams}
# =============================================================================
if [ -z "${BASH_VERSION:-}" ]; then
  exec bash "$0" "$@"
fi

set -euo pipefail

SCRIPT_PATH="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DW_ROOT="$(cd "${SCRIPT_PATH}/.." && pwd)"
# shellcheck source=/dev/null
source "${DW_ROOT}/dw-utils/func.sh"

end_date="$(get_date "${2:-${1:-$(date -d yesterday +%Y%m%d)}}")"
start_date="$(get_date "${1:-$(date -d "${end_date} -365 days" +%Y%m%d)}")"

echo "======== 波动率历史回填开始 ${start_date} ~ ${end_date} $(date '+%F %T') ========"
run_dwm_market_volatility "${start_date}" "${end_date}"
run_dwm_dc_industry_volatility "${start_date}" "${end_date}"
echo "======== 波动率历史回填完成 $(date '+%F %T') ========"
