#!/bin/bash
# =============================================================================
# 【临时脚本 · 用完可删】
# 补全 ods_dc_member_di：2025-01-01 ~ 2026-06-11（可调参）
# 不接入 func.sh 正式命令，不修改 dw-sync 调度。
#
# 用法:
#   bash dw-tmp/backfill_dc_member.sh
#   bash dw-tmp/backfill_dc_member.sh --start 20250301 --end 20260611
#   bash dw-tmp/backfill_dc_member.sh --dry-run
#   bash dw-tmp/backfill_dc_member.sh --force
#
# 建议 nohup 后台（耗时长）:
#   nohup bash dw-tmp/backfill_dc_member.sh > /root/log/stock_log/backfill_dc_member.log 2>&1 &
# =============================================================================
if [ -z "${BASH_VERSION:-}" ]; then
  exec bash "$0" "$@"
fi

set -euo pipefail

SCRIPT_PATH="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DW_ROOT="$(cd "${SCRIPT_PATH}/.." && pwd)"
# shellcheck source=/dev/null
source "${DW_ROOT}/dw-utils/func.sh"

export PYTHONPATH="${DW_ROOT}:${DW_ROOT}/dw-utils:${DW_ROOT}/dw-sync:${PYTHONPATH:-}"

LOG_DIR="/root/log/stock_log"
mkdir -p "${LOG_DIR}"
STAMP="$(date +%Y%m%d_%H%M%S)"
LOG_FILE="${LOG_DIR}/backfill_dc_member_${STAMP}.log"

echo "======== $(date '+%F %T') backfill_dc_member 开始 ========"
echo "日志: ${LOG_FILE}"

"${PYTHON_BIN}" "${DW_ROOT}/dw-tmp/backfill_dc_member.py" "$@" 2>&1 | tee -a "${LOG_FILE}"
echo "======== $(date '+%F %T') backfill_dc_member 结束 ========"
