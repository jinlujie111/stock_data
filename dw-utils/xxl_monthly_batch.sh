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

# 公司信息 / 主营构成 / 三表+预告快报：现网产品无读方，已停同步（见 data_config status=0）
# AI 核心池若再开：ENABLE_AI_CORE_POOL=1 并单独恢复 stock_company
# run_data_sync "${n_date}" --source-table stock_company --force
# run_data_sync "${n_date}" --source-table fina_mainbz_vip --force
# run_data_sync "${n_date}" --source-table fina_mainbz --force
# run_data_sync "${n_date}" --source-table income_vip --force
# run_data_sync "${n_date}" --source-table cashflow_vip --force
# run_data_sync "${n_date}" --source-table balancesheet_vip --force
# run_data_sync "${n_date}" --source-table forecast_vip --force
# run_data_sync "${n_date}" --source-table express_vip --force

echo "SKIP: 月批无启用任务（财务报表/公司信息已暂停同步）"
echo "======== 月批完成 ${n_date} ========"
