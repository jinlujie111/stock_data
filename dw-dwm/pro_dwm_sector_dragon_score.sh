#!/bin/bash
# =============================================================================
# target_table: dwm_sector_stock_dragon_score_di, dwm_sector_dragon_summary_di
# 板块成分股龙头 MVP 评分（需求2：行业+概念全量批处理）
#
# 用法:
#   bash dw-dwm/pro_dwm_sector_dragon_score.sh
#   bash dw-dwm/pro_dwm_sector_dragon_score.sh 20260606
#   bash dw-dwm/pro_dwm_sector_dragon_score.sh 20260606 "行业,概念"
#   run_sector_dragon_batch 20260606   # 先 source dw-utils/func.sh
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
content_types="${2:-行业,概念}"
workers="${SECTOR_DRAGON_WORKERS:-8}"

LOG_PATH="/root/log/stock_log/${n_date}"
mkdir -p "${LOG_PATH}"
exec 1>>"${LOG_PATH}/pro_dwm_sector_dragon_score_${n_date}.log"
exec 2>>"${LOG_PATH}/pro_dwm_sector_dragon_score_${n_date}.log"

echo "======== $(date '+%F %T') pro_dwm_sector_dragon_score ${n_date} types=${content_types} ========"

export PYTHONPATH="${DW_ROOT}:${DW_ROOT}/dw-utils:${PYTHONPATH:-}"

"${PYTHON_BIN}" -m etl.sector_dragon.batch "${n_date}" \
  --content-types "${content_types}" \
  --workers "${workers}"

echo "DONE pro_dwm_sector_dragon_score ${n_date}"
