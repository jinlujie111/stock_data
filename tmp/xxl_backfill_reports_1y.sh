#!/bin/bash
# =============================================================================
# 一次性：页面报表 DWM/DWS 近 1 年历史回填（ODS 已齐，不跑 sync）
#
# 覆盖 Web 依赖（东财 DC 口径）：
#   资金强度 / 行业板块 / 主线板块 / 量化主线 / 板块量价 / 板块龙头
# 不覆盖（直接读 ODS，ODS 齐即可）：热点股预览、涨停分析
#
# 用法:
#   cd /opt/stock_data
#   bash tmp/xxl_backfill_reports_1y.sh
#   bash tmp/xxl_backfill_reports_1y.sh 20250701 20260705
#   bash tmp/xxl_backfill_reports_1y.sh 20250701 20260705 dwm,dws
#
# 环境变量:
#   BACKFILL_DAYS=365        无参时：结束日=昨日，开始日=结束日往前 N 自然日
#   BACKFILL_STEPS=all       all | dwm,dws,vp,dragon,quant（逗号分隔）
#   SKIP_EXISTING=1          1=若当日 monitor 已有数据则整日跳过（便于断点续跑）
#   STOCK_LOG_DIR=...        日志根目录，默认 ${DW_ROOT}/log/stock_log
#   FAIL_FAST=0              1=任一步失败即退出（默认 0：记 WARN 继续下一天）
#
# XXL-JOB GLUE Shell（执行完可删本脚本）:
#   cd /opt/stock_data && bash tmp/xxl_backfill_reports_1y.sh
#   # 或指定区间:
#   cd /opt/stock_data && bash tmp/xxl_backfill_reports_1y.sh ${executorParams}
# 建议: 任务超时 0 或 ≥86400；单机串行；失败重试 0
#
# 说明:
#   - 按交易日升序逐日跑，保证资金连续天数/主线 MA 等窗口正确
#   - 不修改 dw-utils/xxl_daily_batch.sh 及任何 pro_*.sh
#   - pro_*.sh 若含 UTF-8 BOM，本脚本调用时自动剥离（避免 ﻿#!/bin/bash 报错）
#   - 全量约 240+ 交易日 × (VP+龙头较慢)，可分批 BACKFILL_STEPS
# =============================================================================
if [ -z "${BASH_VERSION:-}" ]; then
  exec bash "$0" "$@"
fi

set -euo pipefail

SCRIPT_PATH="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DW_ROOT="$(cd "${SCRIPT_PATH}/.." && pwd)"
# shellcheck source=/dev/null
source "${DW_ROOT}/dw-utils/func.sh"

BACKFILL_DAYS="${BACKFILL_DAYS:-365}"
BACKFILL_STEPS="${BACKFILL_STEPS:-all}"
SKIP_EXISTING="${SKIP_EXISTING:-1}"
FAIL_FAST="${FAIL_FAST:-0}"
STOCK_LOG_DIR="${STOCK_LOG_DIR:-${DW_ROOT}/log/stock_log}"

_resolve_range() {
  local start end
  if [[ -n "${2:-}" ]]; then
    start="$(get_date "$1")"
    end="$(get_date "$2" "$1")"
  elif [[ -n "${1:-}" ]]; then
    end="$(get_date "$1")"
    start="$(date -d "${end} -${BACKFILL_DAYS} days" +%Y%m%d)"
  else
    end="$(date -d yesterday +%Y%m%d)"
    start="$(date -d "${end} -${BACKFILL_DAYS} days" +%Y%m%d)"
  fi
  if [[ "${start}" -gt "${end}" ]]; then
    local tmp="${start}"
    start="${end}"
    end="${tmp}"
  fi
  echo "${start} ${end}"
}

_step_enabled() {
  local key="$1"
  if [[ "${BACKFILL_STEPS}" == "all" ]]; then
    return 0
  fi
  [[ ",${BACKFILL_STEPS}," == *",${key},"* ]]
}

_day_already_done() {
  local n_date="$1"
  local v_date tbl
  v_date="$(format_date "${n_date}")"
  if _step_enabled dws; then
    tbl="dws_dc_industry_mainline_monitor_di"
  elif _step_enabled vp; then
    tbl="dwm_industry_vp_score_di"
  elif _step_enabled dragon; then
    tbl="dwm_sector_dragon_summary_di"
  elif _step_enabled quant; then
    tbl="dws_dc_industry_quant_mainline_di"
  else
    tbl="dwm_dc_industry_fund_flow_di"
  fi
  local cnt
  cnt="$(${data_mysql} -N -e "
    SELECT COUNT(*) FROM ${tbl} WHERE trade_date = '${v_date}';
  " 2>/dev/null || echo 0)"
  [[ -n "${cnt}" && "${cnt}" -gt 0 ]]
}

# pro_*.sh 若被 Windows 编辑器保存为 UTF-8 BOM，直接 bash 会报：
#   line 1: ﻿#!/bin/bash: No such file or directory
# 临时去 BOM 副本放在同目录，保证脚本内 DW_ROOT 相对路径仍正确。
_bash_pro_sh() {
  local runner="$1"
  shift
  if [[ ! -f "${runner}" ]]; then
    echo "ERROR: 未找到 ${runner}" >&2
    return 1
  fi
  local hdr
  hdr="$(head -c 3 "${runner}" 2>/dev/null || true)"
  if [[ "${hdr}" == $'\xef\xbb\xbf' ]]; then
    local tmp="${runner%.sh}._bf$$.sh"
    tail -c +4 "${runner}" > "${tmp}"
    chmod +x "${tmp}"
    set +e
    bash "${tmp}" "$@"
    local rc=$?
    set -e
    rm -f "${tmp}"
    return "${rc}"
  fi
  bash "${runner}" "$@"
}

_soft_run_pro() {
  local label="$1"
  local runner="$2"
  shift 2
  _soft_run "${label}" _bash_pro_sh "${runner}" "$@"
}

_soft_run() {
  local label="$1"
  shift
  echo "  >> ${label}"
  if "$@"; then
    echo "  OK ${label}"
    return 0
  fi
  local rc=$?
  echo "  WARN FAIL ${label} exit=${rc}" >&2
  _FAILURES+=("${cur_date}:${label}:${rc}")
  if [[ "${FAIL_FAST}" == "1" ]]; then
    exit "${rc}"
  fi
  return 0
}

_run_day() {
  local n_date="$1"
  cur_date="${n_date}"
  echo ""
  echo "======== ${n_date} (${day_idx}/${day_total}) $(date '+%F %T') ========"

  if [[ "${SKIP_EXISTING}" == "1" ]] && _day_already_done "${n_date}"; then
    echo "SKIP: 当日目标表已有数据"
    return 0
  fi

  if _step_enabled dwm; then
    _soft_run_pro "dwm_dc_fund_flow" "${DW_ROOT}/dw-dwm/pro_dwm_dc_industry_fund_flow_di.sh" "${n_date}"
    _soft_run_pro "dwm_dc_trend" "${DW_ROOT}/dw-dwm/pro_dwm_dc_industry_trend_strength_di.sh" "${n_date}"
    _soft_run_pro "dwm_dc_heat" "${DW_ROOT}/dw-dwm/pro_dwm_dc_industry_market_heat_di.sh" "${n_date}"
    _soft_run_pro "dwm_dc_diffusion" "${DW_ROOT}/dw-dwm/pro_dwm_dc_industry_diffusion_di.sh" "${n_date}"
    _soft_run_pro "dwm_dc_prosperity" "${DW_ROOT}/dw-dwm/pro_dwm_dc_industry_prosperity_di.sh" "${n_date}"
  fi

  if _step_enabled dws; then
    _soft_run_pro "dws_mainline_score" "${DW_ROOT}/dw-dws/pro_dws_dc_industry_mainline_score_di.sh" "${n_date}"
    _soft_run_pro "dws_mainline_monitor" "${DW_ROOT}/dw-dws/pro_dws_dc_industry_mainline_monitor_di.sh" "${n_date}"
  fi

  if _step_enabled vp; then
    _soft_run_pro "vp_batch" "${DW_ROOT}/dw-dwm/pro_dwm_industry_vp_score.sh" "${n_date}"
  fi

  if _step_enabled dragon; then
    _soft_run_pro "sector_dragon" "${DW_ROOT}/dw-dwm/pro_dwm_sector_dragon_score.sh" "${n_date}"
  fi

  if _step_enabled quant; then
    _soft_run_pro "quant_mainline" "${DW_ROOT}/dw-dws/pro_dws_dc_industry_quant_mainline_di.sh" "${n_date}"
  fi
}

# 参数: [START_YYYYMMDD] [END_YYYYMMDD] [STEPS]
if [[ $# -ge 3 ]]; then
  BACKFILL_STEPS="$3"
fi

read -r range_start range_end < <(_resolve_range "${1:-}" "${2:-}")
LOG_TAG="backfill_${range_start}_${range_end}"
LOG_PATH="${STOCK_LOG_DIR}/${LOG_TAG}"
mkdir -p "${LOG_PATH}"
LOG_FILE="${LOG_PATH}/xxl_backfill_reports.log"

_FAILURES=()
day_idx=0
day_total=0

mapfile -t TRADE_DAYS < <(get_trading_dates "${range_start}" "${range_end}")
day_total="${#TRADE_DAYS[@]}"

{
  echo "======== 页面报表历史回填开始 $(date '+%F %T') ========"
  echo "DW_ROOT=${DW_ROOT} USER=$(id)"
  echo "区间(交易日): ${range_start} ~ ${range_end} 共 ${day_total} 天"
  echo "BACKFILL_STEPS=${BACKFILL_STEPS} SKIP_EXISTING=${SKIP_EXISTING} FAIL_FAST=${FAIL_FAST}"
  echo "日志: ${LOG_FILE}"
} | tee -a "${LOG_FILE}"

if [[ "${day_total}" -eq 0 ]]; then
  echo "ERROR: ods_trading_day 在 ${range_start}~${range_end} 无交易日" | tee -a "${LOG_FILE}" >&2
  exit 1
fi

for cur_date in "${TRADE_DAYS[@]}"; do
  day_idx=$((day_idx + 1))
  _run_day "${cur_date}" 2>&1 | tee -a "${LOG_FILE}"
done

{
  echo ""
  echo "======== 回填结束 $(date '+%F %T') ========"
  echo "失败/跳过步数: ${#_FAILURES[@]}"
  if [[ ${#_FAILURES[@]} -gt 0 ]]; then
    printf '  %s\n' "${_FAILURES[@]:0:50}"
    if [[ ${#_FAILURES[@]} -gt 50 ]]; then
      echo "  ... 另有 $((${#_FAILURES[@]} - 50)) 条，见 ${LOG_FILE}"
    fi
  fi
  echo ""
  echo "--- 抽样校验（结束日 $(format_date "${range_end}")）---"
  ${data_mysql} -e "
    SELECT 'fund_flow' AS tbl, COUNT(*) cnt FROM dwm_dc_industry_fund_flow_di WHERE trade_date='$(format_date "${range_end}")'
    UNION ALL SELECT 'mainline_monitor', COUNT(*) FROM dws_dc_industry_mainline_monitor_di WHERE trade_date='$(format_date "${range_end}")'
    UNION ALL SELECT 'vp_score', COUNT(*) FROM dwm_industry_vp_score_di WHERE trade_date='$(format_date "${range_end}")'
    UNION ALL SELECT 'dragon_summary', COUNT(*) FROM dwm_sector_dragon_summary_di WHERE trade_date='$(format_date "${range_end}")'
    UNION ALL SELECT 'quant_mainline', COUNT(*) FROM dws_dc_industry_quant_mainline_di WHERE trade_date='$(format_date "${range_end}")';
  " 2>/dev/null || true
} | tee -a "${LOG_FILE}"

if [[ ${#_FAILURES[@]} -gt 0 ]]; then
  exit 1
fi
