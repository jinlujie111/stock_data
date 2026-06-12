#!/bin/bash
# =============================================================================
# target_table: dwm_ths_industry_market_heat_di
# source_table: ods_ths_daily_di, ods_ths_index_di, ods_ths_member_di,
#               ods_stock_detail_di, ods_limit_list_di, ods_ths_hot_di
# 同花顺板块市场热度（结构对齐东财 DWM）
#
# 参与计算的指标：同 pro_dwm_dc_industry_market_heat_di.sh
#   board_amount = 成分股 ods_stock_detail_di.amount 汇总（千元×1000→元）
#
# 仅保留、不参与计算的热榜字段（板块级直挂 ods_ths_hot_di）：
#   ths_hot_rank / ths_hot_value / ths_hot_market
#
# 用法（必须用 bash，不要用 sh）:
#   bash dw-dwm/pro_dwm_ths_industry_market_heat_di.sh
#   bash dw-dwm/pro_dwm_ths_industry_market_heat_di.sh 20260527
#   或: run_dwm_ths_industry_market_heat 20260527  （先 source dw-utils/func.sh）
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
exec 1>>"${LOG_PATH}/pro_dwm_ths_industry_market_heat_di_${n_date}.log"
exec 2>>"${LOG_PATH}/pro_dwm_ths_industry_market_heat_di_${n_date}.log"

echo "======== $(date '+%F %T') pro_dwm_ths_industry_market_heat_di ${n_date_s} ~ ${n_date_e} ========"

${data_mysql} -e "
CREATE TABLE IF NOT EXISTS dwm_ths_industry_market_heat_di (
    id                  BIGINT PRIMARY KEY AUTO_INCREMENT,
    trade_date          DATE           NOT NULL COMMENT '交易日期',
    content_type        VARCHAR(32)    NULL COMMENT '板块类型(行业/概念/地域)',
    industry_code       VARCHAR(32)    NOT NULL COMMENT '板块代码(同花顺)',
    industry_name       VARCHAR(128)   NULL COMMENT '板块名称',
    constituent_cnt     INT            NOT NULL DEFAULT 0 COMMENT '成分股数',
    board_amount        DECIMAL(20, 4) NULL COMMENT '板块成交额(元,成分汇总)',
    market_total_amount DECIMAL(20, 4) NULL COMMENT '全A成交额(元)',
    amount_ratio        DECIMAL(20, 8) NULL COMMENT '成交额占比',
    limit_up_cnt        INT            NOT NULL DEFAULT 0 COMMENT '涨停家数',
    limit_up_ratio      DECIMAL(20, 6) NULL COMMENT '涨停扩散率',
    limit_up_20cm_cnt   INT            NOT NULL DEFAULT 0 COMMENT '20cm涨停家数',
    up_cnt              INT            NOT NULL DEFAULT 0 COMMENT '上涨家数',
    up_ratio            DECIMAL(20, 6) NULL COMMENT '上涨家数占比',
    turnover_rate       DECIMAL(20, 6) NULL COMMENT '板块换手率(%)',
    pct_change          DECIMAL(20, 6) NULL COMMENT '板块涨跌幅(%)',
    ths_hot_rank        INT            NULL COMMENT '同花顺热榜排名(仅保留不参与计算)',
    ths_hot_value       DECIMAL(20, 4) NULL COMMENT '同花顺热度值(仅保留不参与计算)',
    ths_hot_market      VARCHAR(32)    NULL COMMENT '同花顺热榜类型(行业板块/概念板块等)',
    heat_rank           INT            NULL COMMENT '成交额占比排名(同类型内,不含热榜)',
    created_at          DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at          DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_dwm_ths_industry_market_heat (trade_date, industry_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='同花顺板块市场热度(DWM,热榜字段仅透传)';
"

load_ths_industry_market_heat() {
  local n_date="$1"
  local v_date
  v_date="$(format_date "${n_date}")"
  echo "DEBUG load_ths_industry_market_heat: n_date=${n_date} v_date=${v_date}"

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
    DELETE FROM dwm_ths_industry_market_heat_di WHERE trade_date = '${v_date}';

    INSERT INTO dwm_ths_industry_market_heat_di (
        trade_date,
        content_type,
        industry_code,
        industry_name,
        constituent_cnt,
        board_amount,
        market_total_amount,
        amount_ratio,
        limit_up_cnt,
        limit_up_ratio,
        limit_up_20cm_cnt,
        up_cnt,
        up_ratio,
        turnover_rate,
        pct_change,
        ths_hot_rank,
        ths_hot_value,
        ths_hot_market,
        heat_rank
    )
    WITH member_norm AS (
        SELECT
            m.ts_code AS industry_code,
            CASE
                WHEN INSTR(m.con_code, '.') > 0 THEN m.con_code
                WHEN LEFT(m.con_code, 1) IN ('6', '5', '9') THEN CONCAT(m.con_code, '.SH')
                WHEN LEFT(m.con_code, 1) IN ('8', '4') THEN CONCAT(m.con_code, '.BJ')
                ELSE CONCAT(m.con_code, '.SZ')
            END AS stock_code
        FROM ods_ths_member_di m
        WHERE IFNULL(m.is_new, 'Y') = 'Y'
    ),
    market_total AS (
        SELECT
            SUM(s.amount * 1000) AS market_total_amount
        FROM ods_stock_detail_di s
        WHERE s.trade_date = '${v_date}'
          AND (s.ts_code LIKE '%.SH' OR s.ts_code LIKE '%.SZ')
    ),
    board_info AS (
        SELECT
            d.trade_date,
            d.ts_code AS industry_code,
            i.name AS industry_name,
            CASE i.index_type
                WHEN 'I' THEN '行业'
                WHEN 'N' THEN '概念'
                WHEN 'R' THEN '地域'
            END AS content_type,
            d.turnover_rate,
            d.pct_change
        FROM ods_ths_daily_di d
        JOIN ods_ths_index_di i
          ON d.ts_code = i.ts_code
         AND i.index_type IN ('I', 'N', 'R')
        WHERE d.trade_date = '${v_date}'
    ),
    amt_by_board AS (
        SELECT
            mn.industry_code,
            SUM(s.amount * 1000) AS board_amount
        FROM member_norm mn
        LEFT JOIN ods_stock_detail_di s
          ON mn.stock_code = s.ts_code
         AND s.trade_date = '${v_date}'
        GROUP BY mn.industry_code
    ),
    stock_stats AS (
        SELECT
            mn.industry_code,
            COUNT(DISTINCT mn.stock_code) AS constituent_cnt,
            SUM(CASE WHEN s.pct_chg > 0 THEN 1 ELSE 0 END) AS up_cnt,
            SUM(CASE WHEN l.limit = 'U' THEN 1 ELSE 0 END) AS limit_up_cnt,
            SUM(
                CASE
                    WHEN l.limit = 'U'
                     AND (
                        mn.stock_code LIKE '30%.SZ'
                        OR mn.stock_code LIKE '301%.SZ'
                        OR mn.stock_code LIKE '688%.SH'
                     )
                    THEN 1 ELSE 0
                END
            ) AS limit_up_20cm_cnt
        FROM member_norm mn
        LEFT JOIN ods_stock_detail_di s
          ON mn.stock_code = s.ts_code
         AND s.trade_date = '${v_date}'
        LEFT JOIN ods_limit_list_di l
          ON mn.stock_code = l.ts_code
         AND l.trade_date = '${v_date}'
        GROUP BY mn.industry_code
    ),
    ths_hot_ref AS (
        SELECT
            h.ts_code AS industry_code,
            h.ths_rank AS ths_hot_rank,
            h.hot AS ths_hot_value,
            h.market AS ths_hot_market
        FROM ods_ths_hot_di h
        WHERE h.trade_date = '${v_date}'
          AND h.market IN ('行业板块', '概念板块')
    ),
    merged AS (
        SELECT
            bi.trade_date,
            bi.content_type,
            bi.industry_code,
            bi.industry_name,
            IFNULL(ss.constituent_cnt, 0) AS constituent_cnt,
            ab.board_amount,
            mt.market_total_amount,
            CASE
                WHEN mt.market_total_amount IS NOT NULL AND mt.market_total_amount <> 0
                 AND ab.board_amount IS NOT NULL
                THEN ROUND(ab.board_amount / mt.market_total_amount, 8)
                ELSE NULL
            END AS amount_ratio,
            IFNULL(ss.limit_up_cnt, 0) AS limit_up_cnt,
            CASE
                WHEN IFNULL(ss.constituent_cnt, 0) > 0
                THEN ROUND(IFNULL(ss.limit_up_cnt, 0) / ss.constituent_cnt, 6)
                ELSE NULL
            END AS limit_up_ratio,
            IFNULL(ss.limit_up_20cm_cnt, 0) AS limit_up_20cm_cnt,
            IFNULL(ss.up_cnt, 0) AS up_cnt,
            CASE
                WHEN IFNULL(ss.constituent_cnt, 0) > 0
                THEN ROUND(IFNULL(ss.up_cnt, 0) / ss.constituent_cnt, 6)
                ELSE NULL
            END AS up_ratio,
            bi.turnover_rate,
            bi.pct_change,
            th.ths_hot_rank,
            th.ths_hot_value,
            th.ths_hot_market
        FROM board_info bi
        CROSS JOIN market_total mt
        LEFT JOIN amt_by_board ab ON bi.industry_code = ab.industry_code
        LEFT JOIN stock_stats ss ON bi.industry_code = ss.industry_code
        LEFT JOIN ths_hot_ref th ON bi.industry_code = th.industry_code
    ),
    ranked AS (
        SELECT
            m.*,
            ROW_NUMBER() OVER (
                PARTITION BY m.trade_date, m.content_type
                ORDER BY m.amount_ratio DESC
            ) AS heat_rank
        FROM merged m
    )
    SELECT
        trade_date,
        content_type,
        industry_code,
        industry_name,
        constituent_cnt,
        board_amount,
        market_total_amount,
        amount_ratio,
        limit_up_cnt,
        limit_up_ratio,
        limit_up_20cm_cnt,
        up_cnt,
        up_ratio,
        turnover_rate,
        pct_change,
        ths_hot_rank,
        ths_hot_value,
        ths_hot_market,
        heat_rank
    FROM ranked;
  "

  echo "OK ${v_date} ths_daily_rows=${ods_cnt}"
  ${data_mysql} -e "
    SELECT trade_date, content_type, industry_code, industry_name,
           amount_ratio, limit_up_ratio, ths_hot_rank, heat_rank
    FROM dwm_ths_industry_market_heat_di
    WHERE trade_date = '${v_date}'
    ORDER BY amount_ratio DESC
    LIMIT 5;
  "
}

run_dwm_by_trading_day "${n_date_s}" "${n_date_e}" load_ths_industry_market_heat || exit $?
