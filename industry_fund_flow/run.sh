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
# 8080 常被 XXL-JOB 占用，默认改用 8082
export IFF_PORT="${IFF_PORT:-8082}"

export IFF_STOCK_MYSQL_HOST="${STOCK_MYSQL_HOST}"
export IFF_STOCK_MYSQL_PORT="${STOCK_MYSQL_PORT}"
export IFF_STOCK_MYSQL_USER="${STOCK_MYSQL_USER}"
export IFF_STOCK_MYSQL_PASSWORD="${STOCK_MYSQL_PASSWORD}"
export IFF_STOCK_MYSQL_DATABASE="${STOCK_MYSQL_DATABASE}"

echo "用户库: ${IFF_MYSQL_USER}@${IFF_MYSQL_HOST}:${IFF_MYSQL_PORT}/${IFF_MYSQL_DATABASE}"
echo "行情库: ${IFF_STOCK_MYSQL_USER}@${IFF_STOCK_MYSQL_HOST}:${IFF_STOCK_MYSQL_PORT}/${IFF_STOCK_MYSQL_DATABASE}"

if command -v ss >/dev/null 2>&1; then
  if ss -lnt | awk '{print $4}' | grep -qE ":${IFF_PORT}$"; then
    echo "ERROR: 端口 ${IFF_PORT} 已被占用。可换端口启动，例如: IFF_PORT=8082 bash industry_fund_flow/run.sh" >&2
    ss -lntp | grep ":${IFF_PORT} " || true
    exit 1
  fi
fi

echo "启动行业资金流网站: http://${IFF_HOST}:${IFF_PORT} （外网: http://<公网IP>:${IFF_PORT}）"
cd "${SCRIPT_PATH}"

exec "${PYTHON_BIN}" -m uvicorn app.main:app --host "${IFF_HOST}" --port "${IFF_PORT}" --reload
