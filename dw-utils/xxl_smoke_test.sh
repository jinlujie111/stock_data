#!/bin/bash
# =============================================================================
# XXL-JOB 环境诊断：模拟调度执行，所有结果打到 stderr（不进日志重定向）
#
# 用法（粘贴到 XXL GLUE 临时跑一轮，或 SSH）:
#   cd /opt/stock_data && bash dw-utils/xxl_smoke_test.sh
#   cd /opt/stock_data && bash dw-utils/xxl_smoke_test.sh 20260703
# =============================================================================
if [ -z "${BASH_VERSION:-}" ]; then
  exec bash "$0" "$@"
fi

set -uo pipefail

_log() { echo "[smoke] $*" >&2; }

SCRIPT_PATH="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DW_ROOT="$(cd "${SCRIPT_PATH}/.." && pwd)"
# shellcheck source=/dev/null
source "${DW_ROOT}/dw-utils/func.sh"

n_date="${1:-$(date +%Y%m%d)}"
fail=0

_check() {
  local name="$1"
  shift
  if "$@" >/dev/null 2>&1; then
    _log "OK   ${name}"
  else
    _log "FAIL ${name}"
    fail=$((fail + 1))
  fi
}

_log "======== XXL smoke test ${n_date} $(date '+%F %T') ========"
_log "USER=$(id)"
_log "PWD=$(pwd)"
_log "DW_ROOT=${DW_ROOT}"
_log "PYTHON_BIN=${PYTHON_BIN}"
_log "STOCK_LOG_DIR=${STOCK_LOG_DIR}"
_log "BASH_SOURCE=${BASH_SOURCE[0]:-?}"
_log "executorParams(n_date)=${n_date}"

_check "sync_runner.sh exists" test -f "${DW_ROOT}/dw-sync/sync_runner.sh"
_check "python3.11 exists" test -x "${PYTHON_BIN}"
_check "DW_ROOT writable" test -w "${DW_ROOT}"

log_dir="${STOCK_LOG_DIR}/${n_date}"
if mkdir -p "${log_dir}" 2>/dev/null; then
  _log "OK   mkdir STOCK_LOG_DIR date dir: ${log_dir}"
else
  _log "FAIL mkdir STOCK_LOG_DIR date dir: ${log_dir}"
  fail=$((fail + 1))
fi

root_log="/root/log/stock_log/${n_date}"
if mkdir -p "${root_log}" 2>/dev/null; then
  _log "OK   mkdir /root/log (pro_*.sh 默认路径)"
else
  _log "WARN cannot mkdir /root/log — 非 root 时第 2 步 DWM 会秒退，请 export STOCK_LOG_DIR"
fi

td_flag="$(trade_day_flag "${n_date}" 2>&1)" || true
_log "trade_day_flag(${n_date})=${td_flag}"

_log "-------- dry: load db_sync_task (first 3 lines) --------"
"${PYTHON_BIN}" - <<'PY' 2>&1 | head -5 >&2 || fail=$((fail + 1))
import os, sys
root = os.environ.get("STOCK_DATA_ROOT") or os.getcwd()
sys.path[:0] = [os.path.join(root, "dw-utils"), os.path.join(root, "dw-sync")]
from mysql_config import load_sync_tasks
tasks = load_sync_tasks()
print(f"tasks={len(tasks)}", flush=True)
for t in tasks[:3]:
    print(f"  id={t['id']} {t['source_table']} -> {t['target_table']}", flush=True)
PY

_log "-------- probe: run_data_sync start 5s (timeout) --------"
if command -v timeout >/dev/null 2>&1; then
  if timeout 5 bash "${DW_ROOT}/dw-sync/sync_runner.sh" "${n_date}" 2>&1 | tail -3 >&2; then
    _log "OK   sync_runner 5s 内未报错退出"
  else
    rc=$?
    if [[ "${rc}" -eq 124 ]]; then
      _log "OK   sync_runner 仍在运行(>5s)，属正常"
    else
      _log "FAIL sync_runner 5s 内 exit=${rc}"
      fail=$((fail + 1))
    fi
  fi
else
  _log "SKIP timeout 命令不存在，请手动 run_data_sync ${n_date}"
fi

_log "-------- probe: run_dwm_market_breadth log redirect --------"
probe="${log_dir}/_breadth_probe.log"
if bash "${DW_ROOT}/dw-dwm/pro_dwm_market_breadth_di.sh" "${n_date}" >>"${probe}" 2>&1; then
  _log "OK   pro_dwm_market_breadth_di finished (see ${probe})"
else
  _log "FAIL pro_dwm_market_breadth_di exit=$? (see ${probe})"
  tail -5 "${probe}" >&2 || true
  fail=$((fail + 1))
fi

_log "======== smoke done fail_count=${fail} ========"
exit "${fail}"
