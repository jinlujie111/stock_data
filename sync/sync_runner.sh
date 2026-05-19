#!/bin/bash
# 数据源 → MySQL 统一同步（须通过本脚本启动，会先加载 dw/utils/func.sh）
# 用法:
#   dw/sync/sync_runner.sh
#   dw/sync/sync_runner.sh 20260516
#   dw/sync/sync_runner.sh --task-code industry_fund_flow
#   dw/sync/sync_runner.sh --list
#
# 或: source dw/utils/func.sh && run_data_sync ...

set -euo pipefail

SCRIPT_PATH=$(dirname "$(readlink -f "${BASH_SOURCE[0]}" 2>/dev/null || realpath "${BASH_SOURCE[0]}")")
DW_ROOT=$(cd "${SCRIPT_PATH}/.." && pwd)
PROJECT_ROOT=$(cd "${DW_ROOT}/.." && pwd)

export path_git_utils="${DW_ROOT}/utils"
if [[ -f "${PROJECT_ROOT}/dw-config/config.sh" ]]; then
    # shellcheck source=/dev/null
    source "${PROJECT_ROOT}/dw-config/config.sh"
fi
# shellcheck source=/dev/null
source "${path_git_utils}/func.sh"

PYTHON_BIN="${PYTHON_BIN:-python3}"
RUNNER_PY="${SCRIPT_PATH}/sync_runner.py"

trade_date=""
extra_args=()

if [[ $# -gt 0 && "${1:0:1}" != "-" && "${1}" =~ ^[0-9]{8}$ ]]; then
    trade_date="$1"
    shift
fi
extra_args=("$@")

cd "${SCRIPT_PATH}"
exec "${PYTHON_BIN}" "${RUNNER_PY}" ${trade_date:+--trade-date "${trade_date}"} "${extra_args[@]}"
