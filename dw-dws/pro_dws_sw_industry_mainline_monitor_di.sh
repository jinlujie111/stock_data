#!/bin/bash
# =============================================================================
# target_table: dws_sw_industry_mainline_monitor_di
# 申万行业主线监控表（L1/L2/L3），依赖 dws_sw_industry_mainline_score_di
#
# 用法:
#   bash dw-dws/pro_dws_sw_industry_mainline_monitor_di.sh 20260527
#   或: run_dws_sw_industry_mainline_monitor 20260527
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
exec 1>>"${LOG_PATH}/pro_dws_sw_industry_mainline_monitor_di_${n_date}.log"
exec 2>>"${LOG_PATH}/pro_dws_sw_industry_mainline_monitor_di_${n_date}.log"

echo "======== $(date '+%F %T') pro_dws_sw_industry_mainline_monitor_di ${n_date_s} ~ ${n_date_e} ========"

${data_mysql} -e "
CREATE TABLE IF NOT EXISTS dws_sw_industry_mainline_monitor_di (
    id                  BIGINT PRIMARY KEY AUTO_INCREMENT,
    trade_date          DATE           NOT NULL,
    industry_level      VARCHAR(4)     NOT NULL COMMENT 'L1/L2/L3',
    industry_code       VARCHAR(32)    NOT NULL,
    industry_name       VARCHAR(128)   NULL,
    rank_no             INT            NULL,
    main_score          DECIMAL(10, 2) NULL,
    total_score         DECIMAL(10, 2) NULL,
    total_score_ma3     DECIMAL(10, 2) NULL,
    total_score_ma5     DECIMAL(10, 2) NULL,
    total_score_ma10    DECIMAL(10, 2) NULL,
    mainline_level      VARCHAR(16)    NULL,
    mainline_stage      VARCHAR(16)    NULL,
    rs_5d               DECIMAL(20, 6) NULL,
    limit_up_cnt        INT            NULL,
    profit_yoy          DECIMAL(20, 6) NULL,
    amount_ratio        DECIMAL(20, 8) NULL,
    limit_up_ratio      DECIMAL(20, 6) NULL,
    up_ratio            DECIMAL(20, 6) NULL,
    score_fund          DECIMAL(10, 2) NULL,
    score_trend         DECIMAL(10, 2) NULL,
    score_heat          DECIMAL(10, 2) NULL,
    score_prosperity    DECIMAL(10, 2) NULL,
    score_diffusion     DECIMAL(10, 2) NULL,
    is_top20            TINYINT        NOT NULL DEFAULT 0,
    created_at          DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at          DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_dws_sw_mainline_monitor (trade_date, industry_level, industry_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='申万行业主线监控表(DWS)';
"

load_sw_mainline_monitor() {
  local n_date="$1"
  local v_date
  v_date="$(format_date "${n_date}")"

  local score_cnt
  score_cnt="$(${data_mysql} -N -e "
    SELECT COUNT(*) FROM dws_sw_industry_mainline_score_di WHERE trade_date = '${v_date}';
  ")"
  if [[ -z "${score_cnt}" || "${score_cnt}" -eq 0 ]]; then
    echo "WARN: skip ${v_date}, dws_sw_industry_mainline_score_di has no rows"
    return 1
  fi

  ${data_mysql} -e "
    DELETE FROM dws_sw_industry_mainline_monitor_di WHERE trade_date = '${v_date}';

    INSERT INTO dws_sw_industry_mainline_monitor_di (
        trade_date, industry_level, industry_code, industry_name, rank_no, main_score,
        total_score, total_score_ma3, total_score_ma5, total_score_ma10,
        mainline_level, mainline_stage, rs_5d, limit_up_cnt, profit_yoy,
        amount_ratio, limit_up_ratio, up_ratio,
        score_fund, score_trend, score_heat, score_prosperity, score_diffusion, is_top20
    )
    WITH enriched AS (
        SELECT
            s.*,
            COALESCE(s.total_score_ma5, s.total_score) AS main_score,
            CAST(JSON_UNQUOTE(JSON_EXTRACT(s.detail_json, '$.amount_ratio')) AS DECIMAL(20, 8)) AS amount_ratio,
            df.limit_up_ratio,
            df.up_ratio,
            df.limit_up_cnt,
            100 * PERCENT_RANK() OVER (
                PARTITION BY s.trade_date, s.industry_level ORDER BY df.limit_up_ratio
            ) AS lur_pctile
        FROM dws_sw_industry_mainline_score_di s
        LEFT JOIN dwm_sw_industry_diffusion_di df
          ON s.trade_date = df.trade_date
         AND s.industry_level = df.industry_level
         AND s.industry_code = df.industry_code
        WHERE s.trade_date = '${v_date}'
    ),
    staged AS (
        SELECT e.*,
            CASE
                WHEN e.rs_5d > 0 AND e.lur_pctile >= 80 AND IFNULL(e.limit_up_cnt, 0) >= 2 THEN '板块爆发'
                WHEN IFNULL(e.up_ratio, 0) > 0.5 AND IFNULL(e.limit_up_cnt, 0) >= 1 THEN '资金试探'
                ELSE '观察'
            END AS mainline_stage
        FROM enriched e
    ),
    ranked AS (
        SELECT st.*,
            ROW_NUMBER() OVER (PARTITION BY st.trade_date, st.industry_level ORDER BY st.main_score DESC) AS rank_no
        FROM staged st
    )
    SELECT trade_date, industry_level, industry_code, industry_name, rank_no, main_score,
        total_score, total_score_ma3, total_score_ma5, total_score_ma10,
        mainline_level, mainline_stage, rs_5d, limit_up_cnt, profit_yoy,
        amount_ratio, limit_up_ratio, up_ratio,
        score_fund, score_trend, score_heat, score_prosperity, score_diffusion,
        IF(rank_no <= 20, 1, 0)
    FROM ranked;
  "

  echo "OK ${v_date} score_rows=${score_cnt}"
  ${data_mysql} -e "
    SELECT rank_no, industry_name, main_score, mainline_level, mainline_stage
    FROM dws_sw_industry_mainline_monitor_di
    WHERE trade_date='${v_date}' AND industry_level='L1' ORDER BY rank_no LIMIT 10;
  "
}

fail_cnt=0
for cur_date in $(get_continuous_date "${n_date_s}" "${n_date_e}"); do
  if ! load_sw_mainline_monitor "${cur_date}"; then
    fail_cnt=$((fail_cnt + 1))
  fi
done

if [[ "${fail_cnt}" -gt 0 ]]; then
  echo "DONE with ${fail_cnt} skipped day(s)"
  exit 1
fi
echo "DONE all days"
