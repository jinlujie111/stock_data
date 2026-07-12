#!/bin/bash
# =============================================================================
# target_table: dwm_dc_industry_market_heat_di
# source_table: ods_dc_daily_di, ods_dc_index_di, ods_dc_member_di,
#               ods_stock_detail_di, ods_limit_list_di, ods_dc_hot_di
# 东财板块市场热度（需求文档「市场热度」维 raw 层）
#
# 参与计算的指标：
#   board_amount       = ods_dc_daily_di.amount（元）
#   amount_ratio       = board_amount / 全A成交额（ods_stock_detail_di 汇总，元）
#   limit_up_cnt       = 成分股涨停数（ods_limit_list_di limit=U）
#   limit_up_ratio     = limit_up_cnt / constituent_cnt
#   limit_up_20cm_cnt  = 成分股中创业板/科创板涨停数
#   up_cnt / up_ratio  = 成分上涨家数及占比
#   turnover_rate      = 板块换手率（ods_dc_daily_di）
#   heat_rank          = 当日 amount_ratio 降序排名（同 content_type 内）
#
# 仅保留、不参与任何衍生计算/heat_rank 的热榜字段：
#   dc_hot_rank        = 成分股在东财「人气榜」最佳排名（MIN）
#   dc_hot_rank_soar   = 成分股在东财「飙升榜」最佳排名（MIN）
#
# 用法（必须用 bash，不要用 sh）:
#   bash dw-dwm/pro_dwm_dc_industry_market_heat_di.sh
#   bash dw-dwm/pro_dwm_dc_industry_market_heat_di.sh 20260527
#   或: run_dwm_dc_industry_market_heat 20260527  （先 source dw-utils/func.sh）
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

LOG_PATH="${STOCK_LOG_DIR:-/root/log/stock_log}/${n_date}"
mkdir -p "${LOG_PATH}"
exec 1>>"${LOG_PATH}/pro_dwm_dc_industry_market_heat_di_${n_date}.log"
exec 2>>"${LOG_PATH}/pro_dwm_dc_industry_market_heat_di_${n_date}.log"

echo "======== $(date '+%F %T') pro_dwm_dc_industry_market_heat_di ${n_date_s} ~ ${n_date_e} ========"

${data_mysql} -e "
CREATE TABLE IF NOT EXISTS dwm_dc_industry_market_heat_di (
    id                  BIGINT PRIMARY KEY AUTO_INCREMENT,
    trade_date          DATE           NOT NULL COMMENT '交易日期',
    content_type        VARCHAR(32)    NULL COMMENT '板块类型(行业/概念/地域)',
    industry_code       VARCHAR(32)    NOT NULL COMMENT '板块代码(东财)',
    industry_name       VARCHAR(128)   NULL COMMENT '板块名称',
    constituent_cnt     INT            NOT NULL DEFAULT 0 COMMENT '成分股数',
    board_amount        DECIMAL(20, 4) NULL COMMENT '板块成交额(元)',
    market_total_amount DECIMAL(20, 4) NULL COMMENT '全A成交额(元)',
    amount_ratio        DECIMAL(20, 8) NULL COMMENT '成交额占比=board_amount/market_total',
    limit_up_cnt        INT            NOT NULL DEFAULT 0 COMMENT '涨停家数',
    limit_up_ratio      DECIMAL(20, 6) NULL COMMENT '涨停扩散率=limit_up_cnt/constituent_cnt',
    limit_up_20cm_cnt   INT            NOT NULL DEFAULT 0 COMMENT '20cm涨停家数(创/科)',
    up_cnt              INT            NOT NULL DEFAULT 0 COMMENT '上涨家数',
    up_ratio            DECIMAL(20, 6) NULL COMMENT '上涨家数占比',
    turnover_rate       DECIMAL(20, 6) NULL COMMENT '板块换手率(%)',
    pct_change          DECIMAL(20, 6) NULL COMMENT '板块涨跌幅(%)',
    dc_hot_rank         INT            NULL COMMENT '东财人气榜成分最佳排名(仅保留不参与计算)',
    dc_hot_rank_soar    INT            NULL COMMENT '东财飙升榜成分最佳排名(仅保留不参与计算)',
    heat_rank           INT            NULL COMMENT '成交额占比排名(同类型内,不含热榜)',
    created_at          DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at          DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_dwm_dc_industry_market_heat (trade_date, industry_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='东财板块市场热度(DWM,热榜字段仅透传)';
"

load_dc_industry_market_heat() {
  local n_date="$1"
  local v_date
  v_date="$(format_date "${n_date}")"
  echo "DEBUG load_dc_industry_market_heat: n_date=${n_date} v_date=${v_date}"

  local ods_cnt mem_cnt
  ods_cnt="$(${data_mysql} -N -e "
    SELECT COUNT(*)
    FROM ods_dc_daily_di
    WHERE trade_date = '${v_date}';
  ")"
  mem_cnt="$(${data_mysql} -N -e "
    SELECT COUNT(*)
    FROM ods_dc_member_di
    WHERE trade_date = '${v_date}';
  ")"
  if [[ -z "${ods_cnt}" || "${ods_cnt}" -eq 0 ]]; then
    echo "WARN: skip ${v_date}, ods_dc_daily_di has no rows"
    return 1
  fi
  if [[ -z "${mem_cnt}" || "${mem_cnt}" -eq 0 ]]; then
    echo "WARN: skip ${v_date}, ods_dc_member_di has no rows"
    return 1
  fi

  ${data_mysql} -e "
    DELETE FROM dwm_dc_industry_market_heat_di WHERE trade_date = '${v_date}';

    INSERT INTO dwm_dc_industry_market_heat_di (
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
        dc_hot_rank,
        dc_hot_rank_soar,
        heat_rank
    )
    WITH member_norm AS (
        SELECT
            m.trade_date,
            m.ts_code AS industry_code,
            CASE
                WHEN INSTR(m.con_code, '.') > 0 THEN m.con_code
                WHEN LEFT(m.con_code, 1) IN ('6', '5', '9') THEN CONCAT(m.con_code, '.SH')
                WHEN LEFT(m.con_code, 1) IN ('8', '4') THEN CONCAT(m.con_code, '.BJ')
                ELSE CONCAT(m.con_code, '.SZ')
            END AS stock_code
        FROM ods_dc_member_di m
        WHERE m.trade_date = '${v_date}'
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
            COALESCE(idx.dc_name, d.ts_code) AS industry_name,
            CASE idx.idx_type
                WHEN '行业板块' THEN '行业'
                WHEN '概念板块' THEN '概念'
                WHEN '地域板块' THEN '地域'
                ELSE idx.idx_type
            END AS content_type,
            d.amount AS board_amount,
            d.turnover_rate,
            d.pct_change
        FROM ods_dc_daily_di d
        LEFT JOIN ods_dc_index_di idx
          ON d.trade_date = idx.trade_date
         AND d.ts_code = idx.ts_code
        WHERE d.trade_date = '${v_date}'
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
         AND mn.trade_date = s.trade_date
        LEFT JOIN ods_limit_list_di l
          ON mn.stock_code = l.ts_code
         AND mn.trade_date = l.trade_date
        GROUP BY mn.industry_code
    ),
    dc_hot_ref AS (
        SELECT
            mn.industry_code,
            MIN(CASE WHEN h.hot_type = '人气榜' THEN h.dc_rank END) AS dc_hot_rank,
            MIN(CASE WHEN h.hot_type = '飙升榜' THEN h.dc_rank END) AS dc_hot_rank_soar
        FROM member_norm mn
        JOIN ods_dc_hot_di h
          ON mn.stock_code = h.ts_code
         AND h.trade_date = '${v_date}'
         AND h.market = 'A股市场'
        GROUP BY mn.industry_code
    ),
    merged AS (
        SELECT
            bi.trade_date,
            bi.content_type,
            bi.industry_code,
            bi.industry_name,
            IFNULL(ss.constituent_cnt, 0) AS constituent_cnt,
            bi.board_amount,
            mt.market_total_amount,
            CASE
                WHEN mt.market_total_amount IS NOT NULL AND mt.market_total_amount <> 0
                THEN ROUND(bi.board_amount / mt.market_total_amount, 8)
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
            hr.dc_hot_rank,
            hr.dc_hot_rank_soar
        FROM board_info bi
        CROSS JOIN market_total mt
        LEFT JOIN stock_stats ss ON bi.industry_code = ss.industry_code
        LEFT JOIN dc_hot_ref hr ON bi.industry_code = hr.industry_code
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
        dc_hot_rank,
        dc_hot_rank_soar,
        heat_rank
    FROM ranked;
  "

  echo "OK ${v_date} dc_daily_rows=${ods_cnt} member_rows=${mem_cnt}"
  ${data_mysql} -e "
    SELECT trade_date, content_type, industry_code, industry_name,
           amount_ratio, limit_up_ratio, dc_hot_rank, heat_rank
    FROM dwm_dc_industry_market_heat_di
    WHERE trade_date = '${v_date}'
    ORDER BY amount_ratio DESC
    LIMIT 5;
  "
}

run_dwm_by_trading_day "${n_date_s}" "${n_date_e}" load_dc_industry_market_heat || exit $?
