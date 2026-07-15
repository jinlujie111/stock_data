#!/bin/bash
# =============================================================================
# 指标口径修复后重跑（仅东财 DC；不跑 ODS sync）
#
# 覆盖本次修复的 7 步（按依赖顺序）：
#   1. market_breadth          市场广度
#   2. fund_flow               资金强度（连续天数按交易日历）
#   3. trend_strength          趋势 RS（基准日度窗口）
#   4. mainline_score          主线评分（缺失真降权等）
#   5. mainline_monitor        主线监控（ETF 匹配收紧）
#   6. vp                      板块量价（量比不含当日等）
#   7. dragon                  板块龙头（市值源 / 综合分）
#
# 用法:
#   cd /opt/stock_data
#   # 先验证昨天 1 天
#   bash tmp/xxl_backfill_metric_fix.sh 20260714 20260714
#   # 回填近 1 年
#   bash tmp/xxl_backfill_metric_fix.sh
#   bash tmp/xxl_backfill_metric_fix.sh 20250701 20260714
#   # 只跑部分步骤
#   bash tmp/xxl_backfill_metric_fix.sh 20250701 20260714 breadth,fund,trend
#   bash tmp/xxl_backfill_metric_fix.sh 20250701 20260714 score,monitor,vp,dragon
#
# 环境变量:
#   BACKFILL_DAYS=365
#   BACKFILL_STEPS=all
#     all | breadth,fund,trend,score,monitor,vp,dragon（逗号分隔）
#   SKIP_EXISTING=0          默认 0=覆盖重算（口径已变）；1=有数就跳过
#   FAIL_FAST=0              1=任一步失败即退出
#   STOCK_LOG_DIR=...
#
# XXL-JOB GLUE Shell:
#   cd /opt/stock_data && bash tmp/xxl_backfill_metric_fix.sh ${executorParams}
# 建议: 超时 0 或 ≥86400；单机串行；失败重试 0
#
# 说明:
#   - 按交易日升序逐日跑（连续天数 / 主线 MA / VP 窗口都依赖历史序）
#   - pro_*.sh 若含 UTF-8 BOM，调用时自动剥离
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
# 口径修复场景默认必须重算，不跳过已有数据
SKIP_EXISTING="${SKIP_EXISTING:-0}"
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
  # 用下游终点表判断是否「整日已齐」；断点续跑时才有意义
  if _step_enabled monitor; then
    tbl="dws_dc_industry_mainline_monitor_di"
  elif _step_enabled score; then
    tbl="dws_dc_industry_mainline_score_di"
  elif _step_enabled vp; then
    tbl="dwm_industry_vp_score_di"
  elif _step_enabled dragon; then
    tbl="dwm_sector_dragon_summary_di"
  elif _step_enabled trend; then
    tbl="dwm_dc_industry_trend_strength_di"
  elif _step_enabled fund; then
    tbl="dwm_dc_industry_fund_flow_di"
  else
    tbl="dwm_market_breadth_di"
  fi
  local cnt
  cnt="$(${data_mysql} -N -e "
    SELECT COUNT(*) FROM ${tbl} WHERE trade_date = '${v_date}';
  " 2>/dev/null || echo 0)"
  [[ -n "${cnt}" && "${cnt}" -gt 0 ]]
}

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
    echo "SKIP: 当日目标表已有数据（SKIP_EXISTING=1）"
    return 0
  fi

  # 1 市场广度
  if _step_enabled breadth; then
    _soft_run_pro "market_breadth" "${DW_ROOT}/dw-dwm/pro_dwm_market_breadth_di.sh" "${n_date}"
  fi

  # 2 资金强度（连续净流入按交易日历）
  if _step_enabled fund; then
    _soft_run_pro "fund_flow" "${DW_ROOT}/dw-dwm/pro_dwm_dc_industry_fund_flow_di.sh" "${n_date}"
  fi

  # 3 趋势 RS（基准日度窗口）
  if _step_enabled trend; then
    _soft_run_pro "trend_strength" "${DW_ROOT}/dw-dwm/pro_dwm_dc_industry_trend_strength_di.sh" "${n_date}"
  fi

  # 4–5 主线评分 + 监控（依赖上述 DWM；也依赖未改的 heat/prosperity/diffusion）
  if _step_enabled score; then
    _soft_run_pro "mainline_score" "${DW_ROOT}/dw-dws/pro_dws_dc_industry_mainline_score_di.sh" "${n_date}"
  fi
  if _step_enabled monitor; then
    _soft_run_pro "mainline_monitor" "${DW_ROOT}/dw-dws/pro_dws_dc_industry_mainline_monitor_di.sh" "${n_date}"
  fi

  # 6 量价
  if _step_enabled vp; then
    _soft_run_pro "vp_batch" "${DW_ROOT}/dw-dwm/pro_dwm_industry_vp_score.sh" "${n_date}"
  fi

  # 7 龙头
  if _step_enabled dragon; then
    _soft_run_pro "sector_dragon" "${DW_ROOT}/dw-dwm/pro_dwm_sector_dragon_score.sh" "${n_date}"
  fi
}

# 参数: [START_YYYYMMDD] [END_YYYYMMDD] [STEPS]
if [[ $# -ge 3 ]]; then
  BACKFILL_STEPS="$3"
fi

read -r range_start range_end < <(_resolve_range "${1:-}" "${2:-}")
LOG_TAG="backfill_metric_fix_${range_start}_${range_end}"
LOG_PATH="${STOCK_LOG_DIR}/${LOG_TAG}"
mkdir -p "${LOG_PATH}"
LOG_FILE="${LOG_PATH}/xxl_backfill_metric_fix.log"

_FAILURES=()
day_idx=0
day_total=0
cur_date=""

mapfile -t TRADE_DAYS < <(get_trading_dates "${range_start}" "${range_end}")
day_total="${#TRADE_DAYS[@]}"

{
  echo "======== 指标修复回填开始 $(date '+%F %T') ========"
  echo "DW_ROOT=${DW_ROOT} USER=$(id)"
  echo "区间(交易日): ${range_start} ~ ${range_end} 共 ${day_total} 天"
  echo "BACKFILL_STEPS=${BACKFILL_STEPS} SKIP_EXISTING=${SKIP_EXISTING} FAIL_FAST=${FAIL_FAST}"
  echo "步骤: breadth → fund → trend → score → monitor → vp → dragon"
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
  echo "失败步数: ${#_FAILURES[@]}"
  if [[ ${#_FAILURES[@]} -gt 0 ]]; then
    printf '  %s\n' "${_FAILURES[@]:0:50}"
    if [[ ${#_FAILURES[@]} -gt 50 ]]; then
      echo "  ... 另有 $((${#_FAILURES[@]} - 50)) 条，见 ${LOG_FILE}"
    fi
  fi
  echo ""
  echo "--- 抽样校验（结束日 $(format_date "${range_end}")）---"
  ${data_mysql} -e "
    SELECT 'market_breadth' AS tbl, COUNT(*) cnt FROM dwm_market_breadth_di WHERE trade_date='$(format_date "${range_end}")'
    UNION ALL SELECT 'fund_flow', COUNT(*) FROM dwm_dc_industry_fund_flow_di WHERE trade_date='$(format_date "${range_end}")'
    UNION ALL SELECT 'trend_strength', COUNT(*) FROM dwm_dc_industry_trend_strength_di WHERE trade_date='$(format_date "${range_end}")'
    UNION ALL SELECT 'mainline_score', COUNT(*) FROM dws_dc_industry_mainline_score_di WHERE trade_date='$(format_date "${range_end}")'
    UNION ALL SELECT 'mainline_monitor', COUNT(*) FROM dws_dc_industry_mainline_monitor_di WHERE trade_date='$(format_date "${range_end}")'
    UNION ALL SELECT 'vp_score', COUNT(*) FROM dwm_industry_vp_score_di WHERE trade_date='$(format_date "${range_end}")'
    UNION ALL SELECT 'dragon_summary', COUNT(*) FROM dwm_sector_dragon_summary_di WHERE trade_date='$(format_date "${range_end}")';
  " 2>/dev/null || true
} | tee -a "${LOG_FILE}"

if [[ ${#_FAILURES[@]} -gt 0 ]]; then
  exit 1
fi
