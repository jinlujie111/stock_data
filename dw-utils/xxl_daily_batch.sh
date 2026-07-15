#!/bin/bash
# =============================================================================
# stock_data 日批一键脚本（XXL-JOB / crontab 入口）
#
# 用法:
#   bash dw-utils/xxl_daily_batch.sh              # 默认今天
#   bash dw-utils/xxl_daily_batch.sh 20260616     # 指定业务日 YYYYMMDD
#
# XXL-JOB GLUE Shell（推荐，勿把整份 xxl_daily_batch 粘贴到 gluesource）:
#   cd /opt/stock_data && bash dw-utils/xxl_daily_batch.sh
# 或带业务日:
#   cd /opt/stock_data && bash dw-utils/xxl_daily_batch.sh ${executorParams}
# 注意: 执行器用户需能写 /opt/stock_data/log；各 pro_*.sh 默认写 /root/log，
#       若 XXL 非 root，请在 func.sh 或 crontab 中 export STOCK_LOG_DIR=/opt/stock_data/log/stock_log
# =============================================================================
if [ -z "${BASH_VERSION:-}" ]; then
  exec bash "$0" "$@"
fi

set -euo pipefail

SCRIPT_PATH="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DW_ROOT="$(cd "${SCRIPT_PATH}/.." && pwd)"
# shellcheck source=/dev/null
source "${DW_ROOT}/dw-utils/func.sh"

n_date="${1:-$(date +%Y%m%d)}"

if [[ "$(trade_day_flag "${n_date}")" != "1" ]]; then
  echo "SKIP: ${n_date} 非交易日 (ods_trading_day)"
  exit 0
fi

# 日志目录：默认 ${DW_ROOT}/log（XXL 非 root 用户无法写 /root/log）
STOCK_LOG_DIR="${STOCK_LOG_DIR:-${DW_ROOT}/log/stock_log}"
LOG_PATH="${STOCK_LOG_DIR}/${n_date}"
mkdir -p "${LOG_PATH}" || {
  echo "ERROR: 无法创建日志目录 ${LOG_PATH}（请检查 STOCK_LOG_DIR 权限）" >&2
  exit 1
}
LOG_FILE="${LOG_PATH}/xxl_daily_batch_${n_date}.log"

_on_err() {
  local rc=$?
  echo "FATAL: line ${1}, cmd=${2}, exit=${rc}" >&2
  echo "详细日志: ${LOG_FILE}" >&2
  exit "${rc}"
}
trap '_on_err ${LINENO} ${BASH_COMMAND}' ERR

echo "======== stock_data 日批开始 ${n_date} $(date '+%F %T') ========" >&2
echo "USER=$(id) DW_ROOT=${DW_ROOT} LOG=${LOG_FILE}" >&2

# tee：同时写文件 + 打到 XXL 控制台（避免 exec>> 后控制台无输出像「秒退」）
exec > >(tee -a "${LOG_FILE}") 2>&1

echo "======== stock_data 日批开始 ${n_date} $(date '+%F %T') ========"
echo "日志文件: ${LOG_FILE}"
echo "USER=$(id) DW_ROOT=${DW_ROOT} STOCK_LOG_DIR=${STOCK_LOG_DIR}"

_run_step() {
  local name="$1"
  shift
  echo "-------- STEP ${name} $(date '+%F %T') --------"
  if "$@"; then
    echo "-------- OK ${name} --------"
    return 0
  fi
  local rc=$?
  echo "-------- FAIL ${name} exit=${rc} $(date '+%F %T') --------"
  return "${rc}"
}

# --- 1) ODS ---
_run_step "run_data_sync" run_data_sync "${n_date}"

# --- 2) DWM：广度 ---
_run_step "run_dwm_market_breadth" run_dwm_market_breadth "${n_date}"

# --- 3) DWM：资金强度 ---
_run_step "run_dwm_dc_industry_fund_flow" run_dwm_dc_industry_fund_flow "${n_date}"
_run_step "run_dwm_ths_industry_fund_flow" run_dwm_ths_industry_fund_flow "${n_date}"

# --- 4) DWM：趋势强度 ---
_run_step "run_dwm_dc_industry_trend_strength" run_dwm_dc_industry_trend_strength "${n_date}"
_run_step "run_dwm_ths_industry_trend_strength" run_dwm_ths_industry_trend_strength "${n_date}"

# --- 5) DWM：市场热度 ---
_run_step "run_dwm_dc_industry_market_heat" run_dwm_dc_industry_market_heat "${n_date}"
_run_step "run_dwm_ths_industry_market_heat" run_dwm_ths_industry_market_heat "${n_date}"

# --- 6) DWM：扩散效应 ---
_run_step "run_dwm_dc_industry_diffusion" run_dwm_dc_industry_diffusion "${n_date}"
_run_step "run_dwm_ths_industry_diffusion" run_dwm_ths_industry_diffusion "${n_date}"
_run_step "run_dwm_sw_industry_diffusion" run_dwm_sw_industry_diffusion "${n_date}"

# --- 7) DWM：产业景气 ---
_run_step "run_dwm_dc_industry_prosperity" run_dwm_dc_industry_prosperity "${n_date}"
_run_step "run_dwm_ths_industry_prosperity" run_dwm_ths_industry_prosperity "${n_date}"
_run_step "run_dwm_sw_industry_prosperity" run_dwm_sw_industry_prosperity "${n_date}"

# --- 8) DWS：主线评分 + 监控（需求1）---
_run_step "run_dws_dc_industry_mainline_score" run_dws_dc_industry_mainline_score "${n_date}"
_run_step "run_dws_ths_industry_mainline_score" run_dws_ths_industry_mainline_score "${n_date}"
_run_step "run_dws_sw_industry_mainline_score" run_dws_sw_industry_mainline_score "${n_date}"
_run_step "run_dws_dc_industry_mainline_monitor" run_dws_dc_industry_mainline_monitor "${n_date}"
_run_step "run_dws_ths_industry_mainline_monitor" run_dws_ths_industry_mainline_monitor "${n_date}"
_run_step "run_dws_sw_industry_mainline_monitor" run_dws_sw_industry_mainline_monitor "${n_date}"

# --- 9) 板块量价 VP（需求5）---
_run_step "run_vp_batch" run_vp_batch "${n_date}"

# --- 10) 板块龙头 MVP（需求2）---
_run_step "run_sector_dragon_batch" run_sector_dragon_batch "${n_date}"

# --- 10.5) 量化选股每日信号（依赖个股行情/VP 因子，故在 VP 之后）---
_run_step "run_quant_signal" run_quant_signal "${n_date}"

# --- 11) ODS 完整度监控（有 ALERT 则 exit 1）---
_run_step "run_ods_completeness_monitor" run_ods_completeness_monitor "${n_date}"

echo "======== stock_data 日批完成 ${n_date} $(date '+%F %T') ========"
