#!/bin/bash
# 启动行业资金流网站（注册/登录）
if [ -z "${BASH_VERSION:-}" ]; then
  exec bash "$0" "$@"
fi

set -euo pipefail

SCRIPT_PATH="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DW_ROOT="$(cd "${SCRIPT_PATH}/.." && pwd)"
# shellcheck source=/dev/null
source "${DW_ROOT}/dw-utils/func.sh"

REQ="${SCRIPT_PATH}/requirements.txt"
if [[ -f "${REQ}" ]]; then
  "${PYTHON_BIN}" -m pip install -q -r "${REQ}" -i https://pypi.tuna.tsinghua.edu.cn/simple 2>/dev/null || \
    "${PYTHON_BIN}" -m pip install -q -r "${REQ}"
fi

export IFF_HOST="${IFF_HOST:-0.0.0.0}"
export IFF_PORT="${IFF_PORT:-8080}"
cd "${SCRIPT_PATH}"

exec "${PYTHON_BIN}" -m uvicorn app.main:app --host "${IFF_HOST}" --port "${IFF_PORT}" --reload
