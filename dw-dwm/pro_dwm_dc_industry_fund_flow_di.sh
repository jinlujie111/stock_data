#!/bin/bash
# =============================================================================
# target_table: dwm_dc_industry_fund_flow_di
# source_table: ods_industry_fund_flow_di, ods_dc_daily_di
# 东财板块资金强度基本因子：流入强度、连续净流入天数、资金加速度
#
# 用法（必须用 bash，不要用 sh）:
#   bash dw-dwm/pro_dwm_dc_industry_fund_flow_di.sh              # 默认昨日
#   bash dw-dwm/pro_dwm_dc_industry_fund_flow_di.sh 20260527
#   bash dw-dwm/pro_dwm_dc_industry_fund_flow_di.sh 20260501 20260527
#   或: run_dwm_dc_industry_fund_flow 20260527  （先 source dw-utils/func.sh）
# =============================================================================
if [ -z "${BASH_VERSION:-}" ]; then
  exec bash "$0" "$@"
fi

set -euo pipefail

SCRIPT_PATH="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DW_ROOT="$(cd "${SCRIPT_PATH}/.." && pwd)"
# shellcheck source=/dev/null
source "${DW_ROOT}/dw-utils/func.sh"

n_date_s="$(get_date "${1:-}")"
n_date_e="$(get_date "${2:-${1:-}}")"
n_date="${n_date_e}"

LOG_PATH="/root/log/stock_log/${n_date}"
mkdir -p "${LOG_PATH}"
exec 1>>"${LOG_PATH}/pro_dwm_dc_industry_fund_flow_di_${n_date}.log"
exec 2>>"${LOG_PATH}/pro_dwm_dc_industry_fund_flow_di_${n_date}.log"

echo "======== $(date '+%F %T') pro_dwm_dc_industry_fund_flow_di ${n_date_s} ~ ${n_date_e} ========"

${data_mysql} -e "
CREATE TABLE IF NOT EXISTS dwm_dc_industry_fund_flow_di (
    id                    BIGINT PRIMARY KEY AUTO_INCREMENT,
    trade_date            DATE           NOT NULL COMMENT '交易日期',
    content_type          VARCHAR(32)    NULL COMMENT '板块类型(行业/概念/地域)',
    industry_code         VARCHAR(32)    NOT NULL COMMENT '板块代码(东财)',
    industry_name         VARCHAR(128)   NULL COMMENT '板块名称',
    net_amount            DECIMAL(20, 4) NULL COMMENT '主力净流入净额(元)',
    net_amount_wan        DECIMAL(20, 4) NULL COMMENT '主力净流入净额(万元)',
    net_amount_rate       DECIMAL(20, 6) NULL COMMENT '主力净流入占比(%)',
    buy_elg_amount        DECIMAL(20, 4) NULL COMMENT '超大单净流入(元)',
    pct_change            DECIMAL(20, 6) NULL COMMENT '板块涨跌幅(%)',
    board_amount          DECIMAL(20, 4) NULL COMMENT '板块成交额(元,来源ods_dc_daily_di)',
    fund_inflow_strength  DECIMAL(20, 8) NULL COMMENT '资金流入强度=net_amount/board_amount',
    net_inflow_days       INT            NOT NULL DEFAULT 0 COMMENT '连续净流入天数(资金连续性)',
    net_amount_5d_avg     DECIMAL(20, 4) NULL COMMENT '近5交易日平均净流入(元,不含当日)',
    fund_accel            DECIMAL(20, 4) NULL COMMENT '资金加速度=net_amount-net_amount_5d_avg',
    elg_net_ratio         DECIMAL(20, 6) NULL COMMENT '超大单占主力净流入比',
    dc_rank               INT            NULL COMMENT '东财资金流排名',
    created_at            DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at            DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_dwm_dc_industry_fund_flow (trade_date, industry_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='东财板块资金强度(DWM,来源ods_industry_fund_flow_di+ods_dc_daily_di)';
"

load_dc_industry_fund_flow() {
  local n_date="$1"
  local v_date
  v_date="$(format_date "${n_date}")"

  local ods_cnt
  ods_cnt="$(${data_mysql} -N -e "
    SELECT COUNT(*)
    FROM ods_industry_fund_flow_di
    WHERE trade_date = '${v_date}';
  ")"
  if [[ -z "${ods_cnt}" || "${ods_cnt}" -eq 0 ]]; then
    echo "WARN: skip ${v_date}, ods_industry_fund_flow_di has no rows"
    return 1
  fi

  ${data_mysql} -e "
    DELETE FROM dwm_dc_industry_fund_flow_di WHERE trade_date = '${v_date}';

    INSERT INTO dwm_dc_industry_fund_flow_di (
        trade_date,
        content_type,
        industry_code,
        industry_name,
        net_amount,
        net_amount_wan,
        net_amount_rate,
        buy_elg_amount,
        pct_change,
        board_amount,
        fund_inflow_strength,
        net_inflow_days,
        net_amount_5d_avg,
        fund_accel,
        elg_net_ratio,
        dc_rank
    )
    WITH hist AS (
        SELECT
            f.trade_date,
            f.content_type,
            f.industry_code,
            f.industry_name,
            f.net_amount,
            f.net_amount_rate,
            f.buy_elg_amount,
            f.pct_change,
            f.\`rank\` AS dc_rank,
            CASE WHEN IFNULL(f.net_amount, 0) <= 0 THEN 1 ELSE 0 END AS is_break
        FROM ods_industry_fund_flow_di f
        WHERE f.trade_date <= '${v_date}'
    ),
    streak_base AS (
        SELECT
            h.*,
            SUM(h.is_break) OVER (
                PARTITION BY h.industry_code
                ORDER BY h.trade_date
                ROWS UNBOUNDED PRECEDING
            ) AS streak_grp
        FROM hist h
    ),
    metrics AS (
        SELECT
            s.trade_date,
            s.content_type,
            s.industry_code,
            s.industry_name,
            s.net_amount,
            s.net_amount_rate,
            s.buy_elg_amount,
            s.pct_change,
            s.dc_rank,
            CASE
                WHEN IFNULL(s.net_amount, 0) <= 0 THEN 0
                ELSE ROW_NUMBER() OVER (
                    PARTITION BY s.industry_code, s.streak_grp
                    ORDER BY s.trade_date
                )
            END AS net_inflow_days,
            AVG(s.net_amount) OVER (
                PARTITION BY s.industry_code
                ORDER BY s.trade_date
                ROWS BETWEEN 5 PRECEDING AND 1 PRECEDING
            ) AS net_amount_5d_avg
        FROM streak_base s
    )
    SELECT
        m.trade_date,
        m.content_type,
        m.industry_code,
        m.industry_name,
        m.net_amount,
        ROUND(m.net_amount / 10000, 4) AS net_amount_wan,
        m.net_amount_rate,
        m.buy_elg_amount,
        m.pct_change,
        d.amount AS board_amount,
        CASE
            WHEN d.amount IS NOT NULL AND d.amount <> 0
            THEN ROUND(m.net_amount / d.amount, 8)
            ELSE NULL
        END AS fund_inflow_strength,
        m.net_inflow_days,
        m.net_amount_5d_avg,
        CASE
            WHEN m.net_amount_5d_avg IS NOT NULL
            THEN ROUND(m.net_amount - m.net_amount_5d_avg, 4)
            ELSE NULL
        END AS fund_accel,
        CASE
            WHEN m.net_amount IS NOT NULL AND m.net_amount <> 0
            THEN ROUND(m.buy_elg_amount / m.net_amount, 6)
            ELSE NULL
        END AS elg_net_ratio,
        m.dc_rank
    FROM metrics m
    LEFT JOIN ods_dc_daily_di d
      ON d.trade_date = m.trade_date
     AND d.ts_code = m.industry_code
    WHERE m.trade_date = '${v_date}';
  "

  echo "OK ${v_date} ods_rows=${ods_cnt}"
  ${data_mysql} -e "
    SELECT trade_date, content_type, industry_code, industry_name,
           net_amount_wan, fund_inflow_strength, net_inflow_days, fund_accel
    FROM dwm_dc_industry_fund_flow_di
    WHERE trade_date = '${v_date}'
    ORDER BY net_amount DESC
    LIMIT 5;
  "
}

fail_cnt=0
for cur_date in $(get_continuous_date "${n_date_s}" "${n_date_e}"); do
  if ! load_dc_industry_fund_flow "${cur_date}"; then
    fail_cnt=$((fail_cnt + 1))
  fi
done

if [[ "${fail_cnt}" -gt 0 ]]; then
  echo "DONE with ${fail_cnt} skipped day(s)"
  exit 1
fi
echo "DONE all days"
