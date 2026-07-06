#!/bin/bash
# =============================================================================
# 需求4：AI 板块成分股识别 — 核心池批处理
#
# 用法:
#   bash dw-dwm/pro_dwm_ai_core_pool_di.sh
#   bash dw-dwm/pro_dwm_ai_core_pool_di.sh 20260626
#   bash dw-dwm/pro_dwm_ai_core_pool_di.sh 20260626 --mode full --force
#   bash dw-dwm/pro_dwm_ai_core_pool_di.sh 20260626 --force-trade-day  # 非交易日也跑
#   或: run_ai_core_pool_batch 20260626
#
# 环境变量（db_llm_token 无有效记录时的兜底）:
#   AI_CORE_LLM_API_KEY / OPENAI_API_KEY
#   AI_CORE_LLM_API_URL / OPENAI_API_BASE
#   AI_CORE_USE_RULES=1                    强制规则引擎
# 推荐：在 data_config.db_llm_token 维护各厂商 Key，见 mysql_tables/data_config.sql
# =============================================================================
if [ -z "${BASH_VERSION:-}" ]; then
  exec bash "$0" "$@"
fi

set -euo pipefail

SCRIPT_PATH="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DW_ROOT="$(cd "${SCRIPT_PATH}/.." && pwd)"
# shellcheck source=/dev/null
source "${DW_ROOT}/dw-utils/func.sh"

FORCE_TRADE=0
EXTRA_ARGS=()
if [[ $# -gt 0 && "${1}" =~ ^[0-9]{8}$ ]]; then
  n_date="$(get_date "$1")"
  shift
else
  n_date="$(get_date "")"
fi
for arg in "$@"; do
  case "${arg}" in
    --force-trade-day|-f) FORCE_TRADE=1 ;;
    *) EXTRA_ARGS+=("${arg}") ;;
  esac
done

LOG_PATH="${STOCK_LOG_DIR:-/root/log/stock_log}/${n_date}"
mkdir -p "${LOG_PATH}"
LOG_FILE="${LOG_PATH}/pro_dwm_ai_core_pool_${n_date}.log"

export PYTHONPATH="${DW_ROOT}:${DW_ROOT}/dw-utils:${PYTHONPATH:-}"

trade_flag="$(trade_day_flag "${n_date}" 2>/dev/null || echo 0)"
if [[ "${trade_flag}" != "1" && "${FORCE_TRADE}" != "1" ]]; then
  echo "[SKIP] ${n_date} 非交易日，跳过 AI 核心池（加 --force-trade-day 可强制执行）"
  exit 0
fi

echo "日志: ${LOG_FILE}" >&2
echo "======== $(date '+%F %T') pro_dwm_ai_core_pool trade_date=${n_date} ========" >>"${LOG_FILE}"

set +e
"${PYTHON_BIN}" -m etl.ai_core_pool.batch "${n_date}" "${EXTRA_ARGS[@]}" >>"${LOG_FILE}" 2>&1
rc=$?
set -e

echo "======== DONE exit=${rc} ========" >>"${LOG_FILE}"

if [[ "${rc}" -ne 0 ]]; then
  echo "[ERROR] AI 核心池失败 exit=${rc}，日志: ${LOG_FILE}" >&2
  tail -25 "${LOG_FILE}" >&2
fi
exit "${rc}"
