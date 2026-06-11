#!/bin/bash
# =============================================================================
# target_table: dwm_ths_industry_diffusion_di
# source_table: ods_ths_daily_di, ods_ths_index_di, ods_ths_member_di,
#               ods_stock_detail_di, ods_limit_list_di, dwm_market_breadth_di
# 同花顺板块扩散效应（结构对齐东财 DWM，见 pro_dwm_dc_industry_diffusion_di.sh）
#
# 用法（必须用 bash，不要用 sh）:
#   bash dw-dwm/pro_dwm_ths_industry_diffusion_di.sh
#   bash dw-dwm/pro_dwm_ths_industry_diffusion_di.sh 20260527
#   或: run_dwm_ths_industry_diffusion 20260527  （先 source dw-utils/func.sh）
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
exec 1>>"${LOG_PATH}/pro_dwm_ths_industry_diffusion_di_${n_date}.log"
exec 2>>"${LOG_PATH}/pro_dwm_ths_industry_diffusion_di_${n_date}.log"

echo "======== $(date '+%F %T') pro_dwm_ths_industry_diffusion_di ${n_date_s} ~ ${n_date_e} ========"

${data_mysql} -e "
CREATE TABLE IF NOT EXISTS dwm_ths_industry_diffusion_di (
    id                    BIGINT PRIMARY KEY AUTO_INCREMENT,
    trade_date            DATE           NOT NULL COMMENT '交易日期',
    content_type          VARCHAR(32)    NULL COMMENT '板块类型(行业/概念/地域)',
    industry_code         VARCHAR(32)    NOT NULL COMMENT '板块代码(同花顺)',
    industry_name         VARCHAR(128)   NULL COMMENT '板块名称',
    constituent_cnt       INT            NOT NULL DEFAULT 0 COMMENT '成分股数',
    up_cnt                INT            NOT NULL DEFAULT 0 COMMENT '上涨家数',
    down_cnt              INT            NOT NULL DEFAULT 0 COMMENT '下跌家数',
    flat_cnt              INT            NOT NULL DEFAULT 0 COMMENT '平盘家数',
    up_ratio              DECIMAL(20, 6) NULL COMMENT '上涨家数占比',
    down_ratio            DECIMAL(20, 6) NULL COMMENT '下跌家数占比',
    flat_ratio            DECIMAL(20, 6) NULL COMMENT '平盘家数占比',
    limit_up_cnt          INT            NOT NULL DEFAULT 0 COMMENT '涨停家数(U)',
    limit_up_ratio        DECIMAL(20, 6) NULL COMMENT '涨停扩散率',
    limit_down_cnt        INT            NOT NULL DEFAULT 0 COMMENT '跌停家数(D)',
    limit_up_20cm_cnt     INT            NOT NULL DEFAULT 0 COMMENT '20cm涨停家数',
    limit_up_20cm_ratio   DECIMAL(20, 6) NULL COMMENT '20cm涨停占比',
    blast_cnt             INT            NOT NULL DEFAULT 0 COMMENT '炸板家数(Z)',
    touch_limit_cnt       INT            NOT NULL DEFAULT 0 COMMENT '触板家数(U+Z)',
    blast_ratio           DECIMAL(20, 6) NULL COMMENT '炸板率',
    board_success_ratio   DECIMAL(20, 6) NULL COMMENT '封板成功率',
    yesterday_limit_cnt   INT            NOT NULL DEFAULT 0 COMMENT '昨日涨停成分股数',
    continue_limit_cnt    INT            NOT NULL DEFAULT 0 COMMENT '昨日涨停今日续板数',
    continue_limit_ratio  DECIMAL(20, 6) NULL COMMENT '晋级率',
    max_limit_times       INT            NULL COMMENT '板块内最高连板数',
    market_advance_ratio  DECIMAL(20, 6) NULL COMMENT '全市场上涨占比',
    up_vs_market          DECIMAL(20, 6) NULL COMMENT '上涨占比/全市场上涨占比',
    diffusion_rank        INT            NULL COMMENT '上涨占比排名(同类型内)',
    created_at            DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at            DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_dwm_ths_industry_diffusion (trade_date, industry_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='同花顺板块扩散效应(DWM)';
"

load_ths_industry_diffusion() {
  local n_date="$1"
  local v_date
  v_date="$(format_date "${n_date}")"
  echo "DEBUG load_ths_industry_diffusion: n_date=${n_date} v_date=${v_date}"

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
    DELETE FROM dwm_ths_industry_diffusion_di WHERE trade_date = '${v_date}';

    INSERT INTO dwm_ths_industry_diffusion_di (
        trade_date,
        content_type,
        industry_code,
        industry_name,
        constituent_cnt,
        up_cnt,
        down_cnt,
        flat_cnt,
        up_ratio,
        down_ratio,
        flat_ratio,
        limit_up_cnt,
        limit_up_ratio,
        limit_down_cnt,
        limit_up_20cm_cnt,
        limit_up_20cm_ratio,
        blast_cnt,
        touch_limit_cnt,
        blast_ratio,
        board_success_ratio,
        yesterday_limit_cnt,
        continue_limit_cnt,
        continue_limit_ratio,
        max_limit_times,
        market_advance_ratio,
        up_vs_market,
        diffusion_rank
    )
    WITH prev_trade AS (
        SELECT MAX(trade_date) AS prev_trade_date
        FROM ods_stock_detail_di
        WHERE trade_date < '${v_date}'
    ),
    member_norm AS (
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
    board_info AS (
        SELECT
            d.trade_date,
            d.ts_code AS industry_code,
            i.name AS industry_name,
            CASE i.index_type
                WHEN 'I' THEN '行业'
                WHEN 'N' THEN '概念'
                WHEN 'R' THEN '地域'
            END AS content_type
        FROM ods_ths_daily_di d
        JOIN ods_ths_index_di i
          ON d.ts_code = i.ts_code
         AND i.index_type IN ('I', 'N', 'R')
        WHERE d.trade_date = '${v_date}'
    ),
    limit_u AS (
        SELECT ts_code, limit_times
        FROM ods_limit_list_di
        WHERE trade_date = '${v_date}' AND \`limit\` = 'U'
    ),
    limit_d AS (
        SELECT ts_code
        FROM ods_limit_list_di
        WHERE trade_date = '${v_date}' AND \`limit\` = 'D'
    ),
    limit_z AS (
        SELECT ts_code
        FROM ods_limit_list_di
        WHERE trade_date = '${v_date}' AND \`limit\` = 'Z'
    ),
    limit_u_prev AS (
        SELECT l.ts_code
        FROM ods_limit_list_di l
        CROSS JOIN prev_trade p
        WHERE l.trade_date = p.prev_trade_date
          AND l.\`limit\` = 'U'
    ),
    stock_stats AS (
        SELECT
            mn.industry_code,
            COUNT(DISTINCT mn.stock_code) AS constituent_cnt,
            SUM(CASE WHEN s.pct_chg > 0 THEN 1 ELSE 0 END) AS up_cnt,
            SUM(CASE WHEN s.pct_chg < 0 THEN 1 ELSE 0 END) AS down_cnt,
            SUM(CASE WHEN s.pct_chg = 0 OR s.pct_chg IS NULL THEN 1 ELSE 0 END) AS flat_cnt,
            SUM(CASE WHEN lu.ts_code IS NOT NULL THEN 1 ELSE 0 END) AS limit_up_cnt,
            SUM(CASE WHEN ld.ts_code IS NOT NULL THEN 1 ELSE 0 END) AS limit_down_cnt,
            SUM(CASE WHEN lz.ts_code IS NOT NULL THEN 1 ELSE 0 END) AS blast_cnt,
            SUM(
                CASE
                    WHEN lu.ts_code IS NOT NULL
                     AND (
                        mn.stock_code LIKE '30%.SZ'
                        OR mn.stock_code LIKE '301%.SZ'
                        OR mn.stock_code LIKE '688%.SH'
                     )
                    THEN 1 ELSE 0
                END
            ) AS limit_up_20cm_cnt,
            SUM(
                CASE
                    WHEN lup.ts_code IS NOT NULL AND lu.ts_code IS NOT NULL THEN 1
                    ELSE 0
                END
            ) AS continue_limit_cnt,
            SUM(CASE WHEN lup.ts_code IS NOT NULL THEN 1 ELSE 0 END) AS yesterday_limit_cnt,
            MAX(lu.limit_times) AS max_limit_times
        FROM member_norm mn
        LEFT JOIN ods_stock_detail_di s
          ON mn.stock_code = s.ts_code
         AND s.trade_date = '${v_date}'
        LEFT JOIN limit_u lu ON mn.stock_code = lu.ts_code
        LEFT JOIN limit_d ld ON mn.stock_code = ld.ts_code
        LEFT JOIN limit_z lz ON mn.stock_code = lz.ts_code
        LEFT JOIN limit_u_prev lup ON mn.stock_code = lup.ts_code
        GROUP BY mn.industry_code
    ),
    market_ref AS (
        SELECT advance_ratio AS market_advance_ratio
        FROM dwm_market_breadth_di
        WHERE trade_date = '${v_date}'
        LIMIT 1
    ),
    merged AS (
        SELECT
            bi.trade_date,
            bi.content_type,
            bi.industry_code,
            bi.industry_name,
            IFNULL(ss.constituent_cnt, 0) AS constituent_cnt,
            IFNULL(ss.up_cnt, 0) AS up_cnt,
            IFNULL(ss.down_cnt, 0) AS down_cnt,
            IFNULL(ss.flat_cnt, 0) AS flat_cnt,
            CASE WHEN ss.constituent_cnt > 0 THEN ROUND(ss.up_cnt / ss.constituent_cnt, 6) END AS up_ratio,
            CASE WHEN ss.constituent_cnt > 0 THEN ROUND(ss.down_cnt / ss.constituent_cnt, 6) END AS down_ratio,
            CASE WHEN ss.constituent_cnt > 0 THEN ROUND(ss.flat_cnt / ss.constituent_cnt, 6) END AS flat_ratio,
            IFNULL(ss.limit_up_cnt, 0) AS limit_up_cnt,
            CASE WHEN ss.constituent_cnt > 0 THEN ROUND(IFNULL(ss.limit_up_cnt, 0) / ss.constituent_cnt, 6) END AS limit_up_ratio,
            IFNULL(ss.limit_down_cnt, 0) AS limit_down_cnt,
            IFNULL(ss.limit_up_20cm_cnt, 0) AS limit_up_20cm_cnt,
            CASE WHEN ss.constituent_cnt > 0 THEN ROUND(IFNULL(ss.limit_up_20cm_cnt, 0) / ss.constituent_cnt, 6) END AS limit_up_20cm_ratio,
            IFNULL(ss.blast_cnt, 0) AS blast_cnt,
            IFNULL(ss.limit_up_cnt, 0) + IFNULL(ss.blast_cnt, 0) AS touch_limit_cnt,
            CASE
                WHEN IFNULL(ss.limit_up_cnt, 0) + IFNULL(ss.blast_cnt, 0) > 0
                THEN ROUND(IFNULL(ss.blast_cnt, 0) / (IFNULL(ss.limit_up_cnt, 0) + IFNULL(ss.blast_cnt, 0)), 6)
                ELSE NULL
            END AS blast_ratio,
            CASE
                WHEN IFNULL(ss.limit_up_cnt, 0) + IFNULL(ss.blast_cnt, 0) > 0
                THEN ROUND(
                    1 - IFNULL(ss.blast_cnt, 0) / (IFNULL(ss.limit_up_cnt, 0) + IFNULL(ss.blast_cnt, 0)), 6
                )
                ELSE NULL
            END AS board_success_ratio,
            IFNULL(ss.yesterday_limit_cnt, 0) AS yesterday_limit_cnt,
            IFNULL(ss.continue_limit_cnt, 0) AS continue_limit_cnt,
            CASE
                WHEN IFNULL(ss.yesterday_limit_cnt, 0) > 0
                THEN ROUND(IFNULL(ss.continue_limit_cnt, 0) / ss.yesterday_limit_cnt, 6)
                ELSE NULL
            END AS continue_limit_ratio,
            ss.max_limit_times,
            mr.market_advance_ratio,
            CASE
                WHEN mr.market_advance_ratio IS NOT NULL AND mr.market_advance_ratio <> 0 AND ss.constituent_cnt > 0
                THEN ROUND((ss.up_cnt / ss.constituent_cnt) / mr.market_advance_ratio, 6)
                ELSE NULL
            END AS up_vs_market
        FROM board_info bi
        LEFT JOIN stock_stats ss ON bi.industry_code = ss.industry_code
        CROSS JOIN market_ref mr
    ),
    ranked AS (
        SELECT
            m.*,
            ROW_NUMBER() OVER (
                PARTITION BY m.trade_date, m.content_type
                ORDER BY m.up_ratio DESC
            ) AS diffusion_rank
        FROM merged m
    )
    SELECT
        trade_date,
        content_type,
        industry_code,
        industry_name,
        constituent_cnt,
        up_cnt,
        down_cnt,
        flat_cnt,
        up_ratio,
        down_ratio,
        flat_ratio,
        limit_up_cnt,
        limit_up_ratio,
        limit_down_cnt,
        limit_up_20cm_cnt,
        limit_up_20cm_ratio,
        blast_cnt,
        touch_limit_cnt,
        blast_ratio,
        board_success_ratio,
        yesterday_limit_cnt,
        continue_limit_cnt,
        continue_limit_ratio,
        max_limit_times,
        market_advance_ratio,
        up_vs_market,
        diffusion_rank
    FROM ranked;
  "

  echo "OK ${v_date} ths_daily_rows=${ods_cnt}"
  ${data_mysql} -e "
    SELECT trade_date, content_type, industry_code, industry_name,
           up_ratio, limit_up_20cm_ratio, continue_limit_ratio, diffusion_rank
    FROM dwm_ths_industry_diffusion_di
    WHERE trade_date = '${v_date}'
    ORDER BY up_ratio DESC
    LIMIT 5;
  "
}

fail_cnt=0
for cur_date in $(get_continuous_date "${n_date_s}" "${n_date_e}"); do
  if ! load_ths_industry_diffusion "${cur_date}"; then
    fail_cnt=$((fail_cnt + 1))
  fi
done

if [[ "${fail_cnt}" -gt 0 ]]; then
  echo "DONE with ${fail_cnt} skipped day(s)"
  exit 1
fi
echo "DONE all days"
