#!/bin/bash
# =============================================================================
# stock_data 周批：行业-ETF 映射（需求1 机构化阶段前置，自动 index_match）
#
# 用法:
#   bash dw-utils/xxl_weekly_batch.sh
#   bash dw-utils/xxl_weekly_batch.sh 20260616
#
# Cron（每周一 03:00）: 0 0 3 * * 1
# =============================================================================
if [ -z "${BASH_VERSION:-}" ]; then
  exec bash "$0" "$@"
fi

set -euo pipefail

SCRIPT_PATH="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DW_ROOT="$(cd "${SCRIPT_PATH}/.." && pwd)"
# shellcheck source=/dev/null
source "${DW_ROOT}/dw-utils/func.sh"

n_date="${1:-$(date +%Y%m%d)}"

echo "======== stock_data 周批 ${n_date} $(date '+%F %T') ========"

run_data_sync "${n_date}" --source-table etf_basic --force
run_data_sync "${n_date}" --source-table etf_share_size --force
run_dim_industry_etf_map "${n_date}"

echo "======== 周批完成 ${n_date} ========"
