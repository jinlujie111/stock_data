#!/bin/bash
# =============================================================================
# 数据同步入口：加载 dw-utils/func.sh 后执行 sync_data.py
# =============================================================================
set -euo pipefail

_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DW_ROOT="$(cd "${_SCRIPT_DIR}/.." && pwd)"

# shellcheck source=/dev/null
source "${DW_ROOT}/dw-utils/func.sh"

export PYTHONPATH="${DW_ROOT}/dw-utils:${DW_ROOT}/dw-sync:${PYTHONPATH:-}"
cd "${DW_ROOT}"

exec "${PYTHON_BIN}" "${_SCRIPT_DIR}/sync_data.py" "$@"
