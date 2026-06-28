#!/bin/bash
# =============================================================================
# ODS 层数据完整性监控：按交易日核查各表是否有数据，缺失则报警
# （轻量版；完整度监控请用 pro_ods_completeness.sh / run_ods_completeness_monitor）
#
# 用法（必须用 bash）:
#   bash dw-monitor/pro_ods_data_check.sh              # 默认检查昨日
#   bash dw-monitor/pro_ods_data_check.sh 20260527
#   bash dw-monitor/pro_ods_data_check.sh --force 20260527   # 非交易日也检查
#   或: run_ods_data_check 20260527
#
# 退出码: 0=全部通过；1=存在缺失/不足（便于 crontab / 调度告警）
# 日志: /root/log/stock_log/${n_date}/pro_ods_data_check_${n_date}.log
# 告警摘要: 同目录 pro_ods_data_check_${n_date}.alert
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
ARGS=()
for arg in "$@"; do
  case "${arg}" in
    --force|-f) FORCE_CHECK=1 ;;
    *) ARGS+=("${arg}") ;;
  esac
done

n_date="$(get_date "${ARGS[0]:-}")"
v_date="$(format_date "${n_date}")"

LOG_PATH="/root/log/stock_log/${n_date}"
mkdir -p "${LOG_PATH}"
LOG_FILE="${LOG_PATH}/pro_ods_data_check_${n_date}.log"
ALERT_FILE="${LOG_PATH}/pro_ods_data_check_${n_date}.alert"

exec 1>>"${LOG_FILE}"
exec 2>>"${LOG_FILE}"

: >"${ALERT_FILE}"

echo "======== $(date '+%F %T') pro_ods_data_check trade_date=${v_date} ========"

# snapshot 表：table|date_column|min_rows|说明
# min_rows 为当日最少行数，低于则报警
# 注：ods_fina_indicator 按 ann_date 稀疏，不做日检（避免误报）
ODS_SNAPSHOT_CHECKS=(
  "ods_stock_detail_di|trade_date|4000|A股日线daily"
  "ods_industry_daily_di|trade_date|30|申万行业日线sw_daily"
  "ods_stock_fund_flow_di|trade_date|4000|个股资金流moneyflow"
  "ods_industry_fund_flow_di|trade_date|50|东财行业资金流moneyflow_ind_dc"
  "ods_dc_index_di|trade_date|50|东财板块指数dc_index"
  "ods_dc_daily_di|trade_date|50|东财板块日线dc_daily"
  "ods_dc_member_di|trade_date|1000|东财板块成分dc_member"
  "ods_dc_hot_di|trade_date|50|东财热榜dc_hot"
  "ods_limit_list_di|trade_date|5|涨跌停limit_list_d"
  "ods_index_daily_di|trade_date|3|指数日线index_daily"
  "ods_report_rc_di|report_date|1|卖方预测report_rc"
  "ods_etf_share_size_di|trade_date|100|ETF份额etf_share_size"
  "ods_ths_daily_di|trade_date|100|同花顺板块日线ths_daily"
  "ods_ths_hot_di|trade_date|50|同花顺热榜ths_hot"
)

# full 表：不按日，检查全表行数下限
ODS_FULL_CHECKS=(
  "ods_trading_day|5000|交易日历AkShare"
  "ods_industry_classify|200|申万行业分类index_classify"
  "ods_index_member_all|3000|申万成分index_member_all"
  "ods_etf_basic_di|50|ETF基础etf_basic"
  "ods_ths_index_di|200|同花顺板块指数ths_index"
  "ods_ths_member_di|5000|同花顺板块成分ths_member"
)

alert_cnt=0
ok_cnt=0

table_exists() {
  local tbl="$1"
  local n
  n="$(${data_mysql} -N -e "
    SELECT COUNT(*)
    FROM information_schema.tables
    WHERE table_schema = DATABASE()
      AND table_name = '${tbl}';
  " 2>/dev/null || echo 0)"
  [[ "${n:-0}" -ge 1 ]]
}

check_snapshot() {
  local tbl="$1" col="$2" min="$3" label="$4"
  if ! table_exists "${tbl}"; then
    echo "[ALERT] ${tbl} (${label}) 表不存在"
    echo "[ALERT] ${tbl} (${label}) 表不存在" >>"${ALERT_FILE}"
    alert_cnt=$((alert_cnt + 1))
    return 1
  fi
  local cnt
  cnt="$(${data_mysql} -N -e "
    SELECT COUNT(*) FROM ${tbl} WHERE ${col} = '${v_date}';
  " 2>/dev/null || echo "")"
  if [[ -z "${cnt}" || "${cnt}" -lt "${min}" ]]; then
    echo "[ALERT] ${tbl} (${label}) 数据缺失或不足: ${col}=${v_date} rows=${cnt:-0} require>=${min}"
    echo "[ALERT] ${tbl} (${label}) ${col}=${v_date} rows=${cnt:-0} require>=${min}" >>"${ALERT_FILE}"
    alert_cnt=$((alert_cnt + 1))
    return 1
  fi
  echo "[OK] ${tbl} (${label}) ${col}=${v_date} rows=${cnt}"
  ok_cnt=$((ok_cnt + 1))
  return 0
}

check_full() {
  local tbl="$1" min="$2" label="$3"
  if ! table_exists "${tbl}"; then
    echo "[ALERT] ${tbl} (${label}) 表不存在"
    echo "[ALERT] ${tbl} (${label}) 表不存在" >>"${ALERT_FILE}"
    alert_cnt=$((alert_cnt + 1))
    return 1
  fi
  local cnt
  cnt="$(${data_mysql} -N -e "SELECT COUNT(*) FROM ${tbl};" 2>/dev/null || echo "")"
  if [[ -z "${cnt}" || "${cnt}" -lt "${min}" ]]; then
    echo "[ALERT] ${tbl} (${label}) 全表数据不足: rows=${cnt:-0} require>=${min}"
    echo "[ALERT] ${tbl} (${label}) total_rows=${cnt:-0} require>=${min}" >>"${ALERT_FILE}"
    alert_cnt=$((alert_cnt + 1))
    return 1
  fi
  echo "[OK] ${tbl} (${label}) total_rows=${cnt}"
  ok_cnt=$((ok_cnt + 1))
  return 0
}

# 交易日判断（ods_trading_day）
trade_flag="$(trade_day_flag "${n_date}" 2>/dev/null || echo 0)"
if [[ "${FORCE_CHECK}" -eq 0 && "${trade_flag}" != "1" ]]; then
  echo "[SKIP] ${v_date} 非交易日(ods_trading_day 无记录)，跳过 ODS 日检。加 --force 可强制执行"
  exit 0
fi

echo "--- 交易日快照表检查 (${v_date}) ---"
for item in "${ODS_SNAPSHOT_CHECKS[@]}"; do
  IFS='|' read -r tbl col min label <<<"${item}"
  check_snapshot "${tbl}" "${col}" "${min}" "${label}" || true
done

echo "--- 全量维表检查 ---"
for item in "${ODS_FULL_CHECKS[@]}"; do
  IFS='|' read -r tbl min label <<<"${item}"
  check_full "${tbl}" "${min}" "${label}" || true
done

# 额外：当日必须在交易日历中
cal_cnt="$(${data_mysql} -N -e "
  SELECT COUNT(*) FROM ods_trading_day WHERE trade_date = '${v_date}';
" 2>/dev/null || echo 0)"
if [[ "${cal_cnt:-0}" -lt 1 ]]; then
  echo "[ALERT] ods_trading_day 缺少当日 ${v_date}"
  echo "[ALERT] ods_trading_day missing trade_date=${v_date}" >>"${ALERT_FILE}"
  alert_cnt=$((alert_cnt + 1))
else
  echo "[OK] ods_trading_day 含 ${v_date}"
  ok_cnt=$((ok_cnt + 1))
fi

echo "--- 汇总 ---"
echo "trade_date=${v_date} OK=${ok_cnt} ALERT=${alert_cnt}"
if [[ "${alert_cnt}" -gt 0 ]]; then
  echo ">>> 告警明细见: ${ALERT_FILE}"
  cat "${ALERT_FILE}"
  exit 1
fi
echo "ALL PASS"
exit 0
