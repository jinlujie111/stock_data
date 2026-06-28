#!/bin/bash
# =============================================================================
# 按 period 单季回补 ods_fina_indicator（如 20251231 年报）
#
# 用法:
#   bash dw-sync/backfill_fina_indicator_period.sh 20251231
#   bash dw-sync/backfill_fina_indicator_period.sh 20251231 --dry-run
#   或: source dw-utils/func.sh && backfill_fina_indicator_period 20251231
# =============================================================================
set -euo pipefail

_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DW_ROOT="$(cd "${_SCRIPT_DIR}/.." && pwd)"

# shellcheck source=/dev/null
source "${DW_ROOT}/dw-utils/func.sh"

export PYTHONPATH="${DW_ROOT}/dw-utils:${DW_ROOT}/dw-sync:${PYTHONPATH:-}"
cd "${DW_ROOT}"

exec "${PYTHON_BIN}" "${_SCRIPT_DIR}/backfill_fina_indicator_period.py" "$@"
