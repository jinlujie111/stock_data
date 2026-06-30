#!/bin/bash
# =============================================================================
# stock_data 日批一键脚本（XXL-JOB / crontab 入口）
#
# 用法:
#   bash dw-utils/xxl_daily_batch.sh              # 默认今天
#   bash dw-utils/xxl_daily_batch.sh 20260616     # 指定业务日 YYYYMMDD
#
# XXL-JOB GLUE Shell: 将本文件内容粘贴，或:
#   cd /opt/stock_data && bash dw-utils/xxl_daily_batch.sh ${n_date}
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

echo "======== stock_data 日批开始 ${n_date} $(date '+%F %T') ========"

# --- 1) ODS ---
run_data_sync "${n_date}"

# --- 2) DWM：广度 ---
run_dwm_market_breadth "${n_date}"

# --- 3) DWM：资金强度 ---
run_dwm_dc_industry_fund_flow "${n_date}"
run_dwm_ths_industry_fund_flow "${n_date}"

# --- 4) DWM：趋势强度 ---
run_dwm_dc_industry_trend_strength "${n_date}"
run_dwm_ths_industry_trend_strength "${n_date}"

# --- 5) DWM：市场热度（需求4 DIM 前置）---
run_dwm_dc_industry_market_heat "${n_date}"
run_dwm_ths_industry_market_heat "${n_date}"

# --- 6) DWM：扩散效应 ---
run_dwm_dc_industry_diffusion "${n_date}"
run_dwm_ths_industry_diffusion "${n_date}"
run_dwm_sw_industry_diffusion "${n_date}"

# --- 7) DWM：产业景气 ---
run_dwm_dc_industry_prosperity "${n_date}"
run_dwm_ths_industry_prosperity "${n_date}"
run_dwm_sw_industry_prosperity "${n_date}"

# --- 8) DWS：主线评分 + 监控（需求1）---
run_dws_dc_industry_mainline_score "${n_date}"
run_dws_ths_industry_mainline_score "${n_date}"
run_dws_sw_industry_mainline_score "${n_date}"
run_dws_dc_industry_mainline_monitor "${n_date}"
run_dws_ths_industry_mainline_monitor "${n_date}"
run_dws_sw_industry_mainline_monitor "${n_date}"

# --- 9) DIM：东财热度赛道 + 成分（需求4）---
# 环境变量可选：AI_CORE_TRACK_TOP_N=50  AI_CORE_TRACK_CONTENT_TYPES=概念,行业
run_dim_industry_track "${n_date}"

# --- 9b) AI 核心池（需求4；无 LLM Key 时自动走规则引擎）---
run_ai_core_pool_batch "${n_date}"

# --- 10) 板块龙头 MVP（需求2）---
run_sector_dragon_batch "${n_date}"

# --- 11) 量化主线 FTELP（需求3，东财行业口径）---
run_dws_dc_industry_quant_mainline "${n_date}"

# --- 12) ODS 完整度监控（有 ALERT 则 exit 1，便于 XXL-JOB 告警）---
run_ods_completeness_monitor "${n_date}"

echo "======== stock_data 日批完成 ${n_date} $(date '+%F %T') ========"
