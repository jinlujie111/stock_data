#!/bin/bash
# =============================================================================
# target_table: dwm_ths_industry_fund_flow_di
# source_table: ods_ths_member_di, ods_ths_index_di, ods_stock_fund_flow_di,
#               ods_stock_detail_di, ods_ths_daily_di
# 同花顺板块资金强度（估算）：成分股汇总个股主力/超大单净流入，衍生与东财 DWM 同结构指标
#
# 估算口径：
#   net_amount(元)     = SUM((超大单+大单)净流入万元)*10000
#   buy_elg_amount(元) = SUM(超大单净流入万元)*10000
#   board_amount(元)   = SUM(成分股成交额千元)*1000（无 ths 板块成交额时的估算）
#   pct_change         = ods_ths_daily_di.pct_change
#   dc_rank            = 当日 net_amount 降序排名（结构对齐东财表）
#
# 要点：
#   - ths_member.con_code 可能不含交易所后缀(.SZ/.SH)，程序自动补全
#   - 回看窗口 730 天（≈500 交易日），过大窗口会导致查询超时
#   - 含诊断：执行前检查代码格式匹配，不匹配时报错并给出样例
#
# 用法（必须用 bash，不要用 sh）:
#   bash dw-dwm/pro_dwm_ths_industry_fund_flow_di.sh              # 默认昨日
#   bash dw-dwm/pro_dwm_ths_industry_fund_flow_di.sh 20260527
#   bash dw-dwm/pro_dwm_ths_industry_fund_flow_di.sh 20260501 20260527
#   或: run_dwm_ths_industry_fund_flow 20260527  （先 source dw-utils/func.sh）
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
exec 1>>"${LOG_PATH}/pro_dwm_ths_industry_fund_flow_di_${n_date}.log"
exec 2>>"${LOG_PATH}/pro_dwm_ths_industry_fund_flow_di_${n_date}.log"

echo "======== $(date '+%F %T') pro_dwm_ths_industry_fund_flow_di ${n_date_s} ~ ${n_date_e} ========"

${data_mysql} -e "
CREATE TABLE IF NOT EXISTS dwm_ths_industry_fund_flow_di (
    trade_date            DATE           NOT NULL COMMENT '交易日期',
    content_type          VARCHAR(32)    NULL COMMENT '板块类型(行业/概念/地域等)',
    industry_code         VARCHAR(32)    NOT NULL COMMENT '板块代码(同花顺)',
    industry_name         VARCHAR(128)   NULL COMMENT '板块名称',
    net_amount            DECIMAL(20, 4) NULL COMMENT '主力净流入净额(元,成分股汇总估算)',
    net_amount_wan        DECIMAL(20, 4) NULL COMMENT '主力净流入净额(万元)',
    net_amount_rate       DECIMAL(20, 6) NULL COMMENT '主力净流入占比(%)=net_amount/board_amount*100',
    buy_elg_amount        DECIMAL(20, 4) NULL COMMENT '超大单净流入(元,成分股汇总估算)',
    pct_change            DECIMAL(20, 6) NULL COMMENT '板块涨跌幅(%)',
    board_amount          DECIMAL(20, 4) NULL COMMENT '板块成交额(元,成分股成交额汇总估算)',
    fund_inflow_strength  DECIMAL(20, 8) NULL COMMENT '资金流入强度=net_amount/board_amount',
    net_inflow_days       INT            NOT NULL DEFAULT 0 COMMENT '连续净流入天数(资金连续性)',
    net_amount_5d_avg     DECIMAL(20, 4) NULL COMMENT '近5交易日平均净流入(元,不含当日)',
    fund_accel            DECIMAL(20, 4) NULL COMMENT '资金加速度=net_amount-net_amount_5d_avg',
    elg_net_ratio         DECIMAL(20, 6) NULL COMMENT '超大单占主力净流入比',
    dc_rank               INT            NULL COMMENT '当日主力净流入排名(估算)',
    created_at            DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at            DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_dwm_ths_industry_fund_flow (trade_date, industry_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='同花顺板块资金强度(DWM,成分股资金流汇总估算)';
"

load_ths_industry_fund_flow() {
  local n_date="$1"
  local v_date v_date_120
  v_date="$(format_date "${n_date}")"
  v_date_120="$(date -d "${n_date} 120 day ago" +%Y-%m-%d)"
  echo "DEBUG load_ths_industry_fund_flow: n_date=${n_date} v_date=${v_date} v_date_120=${v_date_120}"

  local ods_cnt
  ods_cnt="$(${data_mysql} -N -e "
    SELECT COUNT(*)
    FROM ods_ths_daily_di
    WHERE trade_date = '${v_date}';
  ")"
  if [[ -z "${ods_cnt}" || "${ods_cnt}" -eq 0 ]]; then
    echo "WARN: skip ${v_date}, ods_ths_daily_di has no rows"
    return 1
  fi

  ${data_mysql} -e "
    DELETE FROM dwm_ths_industry_fund_flow_di WHERE trade_date = '${v_date}';

    INSERT INTO dwm_ths_industry_fund_flow_di (
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
    WITH member_norm AS (
        SELECT
            m.ts_code,
            m.con_code,
            CASE
                WHEN INSTR(m.con_code, '.') > 0 THEN m.con_code
                WHEN LEFT(m.con_code, 1) IN ('6', '5', '9') THEN CONCAT(m.con_code, '.SH')
                ELSE CONCAT(m.con_code, '.SZ')
            END AS stock_code
        FROM ods_ths_member_di m
    ),
    base AS (
        -- 同花顺板块基础指标：成分股资金流汇总
        SELECT
            a.trade_date,
            CASE i.index_type
               WHEN 'I'  THEN '行业'
               WHEN 'N'  THEN '概念'
               WHEN 'R'  THEN '地域'
               WHEN 'S'  THEN '特色'
               WHEN 'ST' THEN '风格'
               WHEN 'TH' THEN '主题'
               WHEN 'BB' THEN '宽基'
               ELSE i.index_type
            END AS content_type,
            a.ts_code AS industry_code,
            i.name AS industry_name,
            SUM(st.buy_lg_amount + st.buy_elg_amount - st.sell_lg_amount - st.sell_elg_amount) * 10000 AS net_amount,
            SUM(st.buy_elg_amount - st.sell_elg_amount) * 10000 AS buy_elg_amount,
            a.pct_change,
            SUM(sto.amount) * 1000 AS board_amount
        FROM ods_ths_daily_di a
        JOIN member_norm b ON a.ts_code = b.ts_code
        JOIN ods_ths_index_di  i ON a.ts_code = i.ts_code
        JOIN ods_stock_fund_flow_di st
          ON b.stock_code = st.ts_code
         AND a.trade_date = st.trade_date
        JOIN ods_stock_detail_di sto
          ON b.stock_code = sto.ts_code
         AND a.trade_date = sto.trade_date
        WHERE a.trade_date <= '${v_date}'
          AND a.trade_date >= '${v_date_120}'
        GROUP BY a.trade_date,
             CASE i.index_type
               WHEN 'I'  THEN '行业'
               WHEN 'N'  THEN '概念'
               WHEN 'R'  THEN '地域'
               WHEN 'S'  THEN '特色'
               WHEN 'ST' THEN '风格'
               WHEN 'TH' THEN '主题'
               WHEN 'BB' THEN '宽基'
               ELSE i.index_type
            END,
             a.ts_code,
             i.name,
             a.pct_change
    ),
    hist AS (
        SELECT
            b.trade_date,
            b.content_type,
            b.industry_code,
            b.industry_name,
            b.net_amount,
            b.buy_elg_amount,
            b.pct_change,
            b.board_amount,
            CASE WHEN IFNULL(b.net_amount, 0) <= 0 THEN 1 ELSE 0 END AS is_break
        FROM base b
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
            s.buy_elg_amount,
            s.pct_change,
            s.board_amount,
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
    ),
    ranked AS (
        SELECT
            m.trade_date,
            m.content_type,
            m.industry_code,
            m.industry_name,
            m.net_amount,
            m.board_amount,
            m.buy_elg_amount,
            m.pct_change,
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
            ROW_NUMBER() OVER (
                PARTITION BY m.trade_date
                ORDER BY m.net_amount DESC
            ) AS dc_rank
        FROM metrics m
        WHERE m.trade_date = '${v_date}'
    )
    SELECT
        r.trade_date,
        r.content_type,
        r.industry_code,
        r.industry_name,
        r.net_amount,
        ROUND(r.net_amount / 10000, 4) AS net_amount_wan,
        CASE
            WHEN r.board_amount IS NOT NULL AND r.board_amount <> 0
            THEN ROUND(r.net_amount / r.board_amount * 100, 6)
            ELSE NULL
        END AS net_amount_rate,
        r.buy_elg_amount,
        r.pct_change,
        r.board_amount,
        CASE
            WHEN r.board_amount IS NOT NULL AND r.board_amount <> 0
            THEN ROUND(r.net_amount / r.board_amount, 8)
            ELSE NULL
        END AS fund_inflow_strength,
        r.net_inflow_days,
        r.net_amount_5d_avg,
        r.fund_accel,
        r.elg_net_ratio,
        r.dc_rank
    FROM ranked r;
  "

  echo "OK ${v_date} ods_rows=${ods_cnt}"
  ${data_mysql} -e "
    SELECT trade_date, content_type, industry_code, industry_name,
           net_amount_wan, fund_inflow_strength, net_inflow_days, fund_accel, dc_rank
    FROM dwm_ths_industry_fund_flow_di
    WHERE trade_date = '${v_date}'
    ORDER BY net_amount DESC
    LIMIT 5;
  "
}

fail_cnt=0
for cur_date in $(get_continuous_date "${n_date_s}" "${n_date_e}"); do
  if ! load_ths_industry_fund_flow "${cur_date}"; then
    fail_cnt=$((fail_cnt + 1))
  fi
done

if [[ "${fail_cnt}" -gt 0 ]]; then
  echo "DONE with ${fail_cnt} skipped day(s)"
  exit 1
fi
echo "DONE all days"
