#!/bin/bash
# =============================================================================
# stock_data 月批：公司信息 / 主营业务构成（VIP 近2季 + 按股补全）
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
run_data_sync "${n_date}" --source-table fina_mainbz_vip --force
# fina_mainbz 按股补 VIP 截断缺失，耗时长，建议单独夜间跑
run_data_sync "${n_date}" --source-table fina_mainbz --force

echo "======== 月批完成 ${n_date} ========"
