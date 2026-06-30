#!/bin/bash
# =============================================================================
# 需求3 量化主线 — 测试一键脚本（行业 Top10 + 概念 Top10 分榜）
#
# 用法:
#   cd /opt/stock_data && bash scripts/test_quant_mainline.sh
#   cd /opt/stock_data && bash scripts/test_quant_mainline.sh 20260625
#   cd /opt/stock_data && bash scripts/test_quant_mainline.sh 20260625 --run-etl
#   cd /opt/stock_data && bash scripts/test_quant_mainline.sh 20260625 --api
#
# API 测试需 Cookie:
#   export IFF_TOKEN_COOKIE='iff_token=你的token'
# =============================================================================
if [ -z "${BASH_VERSION:-}" ]; then
  exec bash "$0" "$@"
fi

set -euo pipefail

SCRIPT_PATH="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DW_ROOT="$(cd "${SCRIPT_PATH}/.." && pwd)"
# shellcheck source=/dev/null
source "${DW_ROOT}/dw-utils/func.sh"

RUN_ETL=0
RUN_API=0
N_DATE=""

for arg in "$@"; do
  case "${arg}" in
    --run-etl) RUN_ETL=1 ;;
    --api) RUN_API=1 ;;
    *)
      if [[ -z "${N_DATE}" && "${arg}" =~ ^[0-9]{8}$ ]]; then
        N_DATE="${arg}"
      fi
      ;;
  esac
done

export PYTHONPATH="${DW_ROOT}:${DW_ROOT}/dw-utils:${PYTHONPATH:-}"

echo "======== [1/4] scoring 单元测试 ========"
"${PYTHON_BIN}" "${DW_ROOT}/scripts/test_quant_mainline_unit.py"

echo ""
echo "======== [2/4] 分榜排名单元测试 ========"
"${PYTHON_BIN}" "${DW_ROOT}/scripts/test_quant_mainline_rank_unit.py"

echo ""
echo "======== [3/4] 数据库验收 ============"
PY_ARGS=()
if [[ -n "${N_DATE}" ]]; then
  PY_ARGS+=("${N_DATE}")
else
  PY_ARGS+=("$(get_date)")
fi
if [[ "${RUN_ETL}" -eq 1 ]]; then
  PY_ARGS+=("--run-etl")
fi
"${PYTHON_BIN}" "${DW_ROOT}/scripts/test_quant_mainline_data.py" "${PY_ARGS[@]}"

if [[ "${RUN_API}" -eq 1 ]]; then
  echo ""
  echo "======== [4/4] API 验收 =============="
  TD_FOR_API="${N_DATE:-$(get_date)}"
  API_ARGS=("${TD_FOR_API}")
  if [[ -n "${IFF_TOKEN_COOKIE:-}" ]]; then
    API_ARGS+=("--cookie" "${IFF_TOKEN_COOKIE}")
  fi
  "${PYTHON_BIN}" "${DW_ROOT}/scripts/test_quant_mainline_api.py" "${API_ARGS[@]}"
else
  echo ""
  echo "跳过 API 测试（加 --api 且配置 IFF_TOKEN_COOKIE 可启用）"
fi

echo ""
echo "DONE test_quant_mainline"
