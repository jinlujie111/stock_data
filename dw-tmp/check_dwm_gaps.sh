#!/bin/bash
# =============================================================================
# 检查 DWM 层缺失交易日（对比 ods_trading_day）
#
# 用法:
#   bash dw-tmp/check_dwm_gaps.sh
#   bash dw-tmp/check_dwm_gaps.sh --start 20250101 --end 20260609
#   bash dw-tmp/check_dwm_gaps.sh --group dc
#   bash dw-tmp/check_dwm_gaps.sh --table dwm_dc_industry_fund_flow_di
#   bash dw-tmp/check_dwm_gaps.sh --format dates --jobs dc_fund_flow
#   bash dw-tmp/check_dwm_gaps.sh --export dw-tmp/out/dwm_gaps.csv
# =============================================================================
if [ -z "${BASH_VERSION:-}" ]; then
  exec bash "$0" "$@"
fi

set -euo pipefail

SCRIPT_PATH="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DW_ROOT="$(cd "${SCRIPT_PATH}/.." && pwd)"
# shellcheck source=/dev/null
source "${DW_ROOT}/dw-utils/func.sh"

export PYTHONPATH="${DW_ROOT}/dw-utils:${DW_ROOT}/dw-tmp:${PYTHONPATH:-}"
cd "${DW_ROOT}"

exec "${PYTHON_BIN}" "${SCRIPT_PATH}/check_dwm_gaps.py" "$@"
