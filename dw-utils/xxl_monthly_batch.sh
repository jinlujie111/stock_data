#!/bin/bash
# =============================================================================
# stock_data 月批：公司信息 / 主营业务构成 / P0 财务报表
#
# 用法:
#   bash dw-utils/xxl_monthly_batch.sh
#   bash dw-utils/xxl_monthly_batch.sh 20260601
#
# Cron（每月 1 号 21:00）: 0 0 21 1 * *
# Quartz: 0 0 21 1 * ?
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

echo "======== stock_data 月批 ${n_date} $(date '+%F %T') ========"

run_data_sync "${n_date}" --source-table stock_company --force
# 主营构成已停用（ods_fina_mainbz_di 腾盘/现网未用）
# run_data_sync "${n_date}" --source-table fina_mainbz_vip --force
# run_data_sync "${n_date}" --source-table fina_mainbz --force

# P0：三张报表 + 业绩预告/快报（近2季 VIP）
run_data_sync "${n_date}" --source-table income_vip --force
run_data_sync "${n_date}" --source-table cashflow_vip --force
run_data_sync "${n_date}" --source-table balancesheet_vip --force
run_data_sync "${n_date}" --source-table forecast_vip --force
run_data_sync "${n_date}" --source-table express_vip --force

echo "======== 月批完成 ${n_date} ========"
