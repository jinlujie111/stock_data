#!/bin/bash
# =============================================================================
# ODS 层数据完整度监控（全量维表 + 日快照 + 报告期覆盖 + 交易日连续性）
#
# 用法（必须用 bash）:
#   bash dw-monitor/pro_ods_completeness.sh              # 默认检查昨日
#   bash dw-monitor/pro_ods_completeness.sh 20260627
#   bash dw-monitor/pro_ods_completeness.sh --force 20260627
#   或: run_ods_completeness_monitor 20260627
#
# 检查项配置: dw-monitor/ods_checks.json（可增删表、阈值）
# 退出码: 0=无 ALERT；1=存在 ALERT（便于 crontab / XXL-JOB）
# 日志: /root/log/stock_log/${n_date}/pro_ods_completeness_${n_date}.log
# 告警摘要: 同目录 pro_ods_completeness_${n_date}.alert
# =============================================================================
if [ -z "${BASH_VERSION:-}" ]; then
  exec bash "$0" "$@"
fi

set -euo pipefail

SCRIPT_PATH="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DW_ROOT="$(cd "${SCRIPT_PATH}/.." && pwd)"
# shellcheck source=/dev/null
source "${DW_ROOT}/dw-utils/func.sh"

FORCE_CHECK=0
JSON_OUT=0
ARGS=()
for arg in "$@"; do
  case "${arg}" in
    --force|-f) FORCE_CHECK=1 ;;
    --json) JSON_OUT=1 ;;
    *) ARGS+=("${arg}") ;;
  esac
done

n_date="$(get_date "${ARGS[0]:-}")"
v_date="$(format_date "${n_date}")"

LOG_PATH="${STOCK_LOG_DIR:-/root/log/stock_log}/${n_date}"
mkdir -p "${LOG_PATH}"
LOG_FILE="${LOG_PATH}/pro_ods_completeness_${n_date}.log"
ALERT_FILE="${LOG_PATH}/pro_ods_completeness_${n_date}.alert"

exec 1>>"${LOG_FILE}"
exec 2>>"${LOG_FILE}"

: >"${ALERT_FILE}"

echo "======== $(date '+%F %T') pro_ods_completeness check_date=${v_date} ========"

export PYTHONPATH="${DW_ROOT}/dw-utils:${DW_ROOT}/dw-sync:${DW_ROOT}/dw-monitor:${PYTHONPATH:-}"

PY_ARGS=()
[[ "${FORCE_CHECK}" -eq 1 ]] && PY_ARGS+=(--force)
[[ "${JSON_OUT}" -eq 1 ]] && PY_ARGS+=(--json)
PY_ARGS+=("${n_date}")

set +e
MONITOR_OUT="$("${PYTHON_BIN}" "${SCRIPT_PATH}/ods_completeness_monitor.py" "${PY_ARGS[@]}" 2>&1)"
RC=$?
set -e

echo "${MONITOR_OUT}"

echo "${MONITOR_OUT}" | grep '^\[ALERT\]' >>"${ALERT_FILE}" || true

echo "--- 汇总 ---"
echo "check_date=${v_date} exit_code=${RC}"
if [[ "${RC}" -ne 0 ]]; then
  echo ">>> 告警明细见: ${ALERT_FILE}"
  if [[ -s "${ALERT_FILE}" ]]; then
    cat "${ALERT_FILE}"
  fi
  exit 1
fi
echo "ALL PASS"
exit 0
