#!/bin/bash
# =============================================================================
# target_table: dws_sw_industry_mainline_score_di
# 申万行业主线评分（L1/L2/L3）：趋势/热度来自 ods_industry_daily_di，景气/扩散来自 DWM
# 资金维度暂无申万 DWM，score_fund 为空并按权重降权
#
# 用法:
#   bash dw-dws/pro_dws_sw_industry_mainline_score_di.sh 20260527
#   或: run_dws_sw_industry_mainline_score 20260527
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
exec 1>>"${LOG_PATH}/pro_dws_sw_industry_mainline_score_di_${n_date}.log"
exec 2>>"${LOG_PATH}/pro_dws_sw_industry_mainline_score_di_${n_date}.log"

echo "======== $(date '+%F %T') pro_dws_sw_industry_mainline_score_di ${n_date_s} ~ ${n_date_e} ========"

${data_mysql} -e "
CREATE TABLE IF NOT EXISTS dws_sw_industry_mainline_score_di (
    id                  BIGINT PRIMARY KEY AUTO_INCREMENT,
    trade_date          DATE           NOT NULL COMMENT '交易日期',
    industry_level      VARCHAR(4)     NOT NULL COMMENT 'L1/L2/L3',
    industry_code       VARCHAR(32)    NOT NULL COMMENT '申万行业代码',
    industry_name       VARCHAR(128)   NULL COMMENT '行业名称',
    score_fund          DECIMAL(10, 2) NULL COMMENT '资金强度(申万暂无)',
    score_trend         DECIMAL(10, 2) NULL COMMENT '趋势强度得分',
    score_heat          DECIMAL(10, 2) NULL COMMENT '市场热度得分',
    score_prosperity    DECIMAL(10, 2) NULL COMMENT '产业景气得分',
    score_diffusion     DECIMAL(10, 2) NULL COMMENT '扩散效应得分',
    total_score         DECIMAL(10, 2) NULL COMMENT '加权总分(降权)',
    total_score_ma3     DECIMAL(10, 2) NULL,
    total_score_ma5     DECIMAL(10, 2) NULL,
    total_score_ma10    DECIMAL(10, 2) NULL,
    mainline_level      VARCHAR(16)    NULL,
    rank_no             INT            NULL COMMENT '同层级内排名',
    rs_5d               DECIMAL(20, 6) NULL,
    limit_up_cnt        INT            NULL,
    profit_yoy          DECIMAL(20, 6) NULL,
    detail_json         JSON           NULL,
    created_at          DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at          DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_dws_sw_mainline_score (trade_date, industry_level, industry_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='申万行业主线评分(DWS)';
"

load_sw_mainline_score() {
  local n_date="$1"
  local v_date v_date_120
  v_date="$(format_date "${n_date}")"
  v_date_120="$(date -d "${n_date} 120 day ago" +%Y-%m-%d)"
  echo "DEBUG load_sw_mainline_score: n_date=${n_date} v_date=${v_date}"

  local diff_cnt
  diff_cnt="$(${data_mysql} -N -e "
    SELECT COUNT(*) FROM dwm_sw_industry_diffusion_di WHERE trade_date = '${v_date}';
  ")"
  if [[ -z "${diff_cnt}" || "${diff_cnt}" -eq 0 ]]; then
    echo "WARN: skip ${v_date}, dwm_sw_industry_diffusion_di has no rows"
    return 1
  fi

  ${data_mysql} -e "
    DELETE FROM dws_sw_industry_mainline_score_di WHERE trade_date = '${v_date}';

    INSERT INTO dws_sw_industry_mainline_score_di (
        trade_date, industry_level, industry_code, industry_name,
        score_fund, score_trend, score_heat, score_prosperity, score_diffusion,
        total_score, mainline_level, rank_no,
        rs_5d, limit_up_cnt, profit_yoy, detail_json
    )
    WITH market_total AS (
        SELECT SUM(amount * 1000) AS market_total_amount
        FROM ods_stock_detail_di
        WHERE trade_date = '${v_date}'
          AND (ts_code LIKE '%.SH' OR ts_code LIKE '%.SZ')
    ),
    bench AS (
        SELECT trade_date, pct_chg AS bench_pct
        FROM ods_index_daily_di
        WHERE ts_code = '000300.SH'
          AND trade_date <= '${v_date}'
          AND trade_date >= '${v_date_120}'
    ),
    ind_daily AS (
        SELECT
            d.trade_date,
            d.ts_code AS industry_code,
            d.name AS industry_name,
            d.amount,
            d.pct_change,
            b.bench_pct
        FROM ods_industry_daily_di d
        JOIN bench b ON d.trade_date = b.trade_date
        WHERE d.trade_date <= '${v_date}'
          AND d.trade_date >= '${v_date_120}'
    ),
    trend_enriched AS (
        SELECT
            trade_date,
            industry_code,
            industry_name,
            amount,
            SUM(pct_change) OVER (
                PARTITION BY industry_code ORDER BY trade_date
                ROWS BETWEEN 4 PRECEDING AND CURRENT ROW
            ) AS ret_5d,
            SUM(bench_pct) OVER (
                ORDER BY trade_date ROWS BETWEEN 4 PRECEDING AND CURRENT ROW
            ) AS bench_ret_5d
        FROM ind_daily
    ),
    trend_today AS (
        SELECT
            industry_code,
            industry_name,
            ROUND(ret_5d - bench_ret_5d, 6) AS rs_5d,
            amount AS ind_amount
        FROM trend_enriched
        WHERE trade_date = '${v_date}'
    ),
    base AS (
        SELECT
            d.trade_date,
            d.industry_level,
            d.industry_code,
            d.industry_name,
            t.rs_5d,
            CASE
                WHEN mt.market_total_amount IS NOT NULL AND mt.market_total_amount <> 0 AND t.ind_amount IS NOT NULL
                THEN ROUND(t.ind_amount * 10000 / mt.market_total_amount, 8)
                ELSE NULL
            END AS amount_ratio,
            p.earnings_yoy, p.forecast_rev_pct, p.upgrade_ratio,
            d.up_ratio, d.limit_up_20cm_ratio, d.continue_limit_ratio, d.limit_up_cnt
        FROM dwm_sw_industry_diffusion_di d
        LEFT JOIN dwm_sw_industry_prosperity_di p
          ON d.trade_date = p.trade_date
         AND d.industry_level = p.industry_level
         AND d.industry_code = p.industry_code
        LEFT JOIN trend_today t ON d.industry_code = t.industry_code
        CROSS JOIN market_total mt
        WHERE d.trade_date = '${v_date}'
    ),
    pct AS (
        SELECT b.*,
            100 * PERCENT_RANK() OVER (PARTITION BY trade_date, industry_level ORDER BY rs_5d) AS pr_rs5,
            100 * PERCENT_RANK() OVER (PARTITION BY trade_date, industry_level ORDER BY amount_ratio) AS pr_amt,
            100 * PERCENT_RANK() OVER (PARTITION BY trade_date, industry_level ORDER BY earnings_yoy) AS pr_ey,
            100 * PERCENT_RANK() OVER (PARTITION BY trade_date, industry_level ORDER BY forecast_rev_pct) AS pr_fr,
            100 * PERCENT_RANK() OVER (PARTITION BY trade_date, industry_level ORDER BY upgrade_ratio) AS pr_ur,
            100 * PERCENT_RANK() OVER (PARTITION BY trade_date, industry_level ORDER BY up_ratio) AS pr_up,
            100 * PERCENT_RANK() OVER (PARTITION BY trade_date, industry_level ORDER BY limit_up_20cm_ratio) AS pr_20,
            100 * PERCENT_RANK() OVER (PARTITION BY trade_date, industry_level ORDER BY continue_limit_ratio) AS pr_clr
        FROM base b
    ),
    dim AS (
        SELECT p.*,
            NULL AS score_fund,
            pr_rs5 AS score_trend,
            pr_amt AS score_heat,
            ROUND((IF(pr_ey IS NOT NULL,0.5*pr_ey,0)+IF(pr_fr IS NOT NULL,0.3*pr_fr,0)+IF(pr_ur IS NOT NULL,0.2*pr_ur,0))
                /NULLIF(IF(pr_ey IS NOT NULL,0.5,0)+IF(pr_fr IS NOT NULL,0.3,0)+IF(pr_ur IS NOT NULL,0.2,0),0),2) AS score_prosperity,
            ROUND((IF(pr_up IS NOT NULL,0.5*pr_up,0)+IF(pr_20 IS NOT NULL,0.3*pr_20,0)+IF(pr_clr IS NOT NULL,0.2*pr_clr,0))
                /NULLIF(IF(pr_up IS NOT NULL,0.5,0)+IF(pr_20 IS NOT NULL,0.3,0)+IF(pr_clr IS NOT NULL,0.2,0),0),2) AS score_diffusion
        FROM pct p
    ),
    tot AS (
        SELECT d.*,
            ROUND((IF(score_trend IS NOT NULL,25*score_trend,0)+IF(score_heat IS NOT NULL,15*score_heat,0)
                +IF(score_prosperity IS NOT NULL,15*score_prosperity,0)+IF(score_diffusion IS NOT NULL,10*score_diffusion,0))
                /NULLIF(IF(score_trend IS NOT NULL,25,0)+IF(score_heat IS NOT NULL,15,0)
                +IF(score_prosperity IS NOT NULL,15,0)+IF(score_diffusion IS NOT NULL,10,0),0),2) AS total_score
        FROM dim d
    ),
    ranked AS (
        SELECT t.*,
            ROW_NUMBER() OVER (PARTITION BY t.trade_date, t.industry_level ORDER BY t.total_score DESC) AS rank_no,
            CASE WHEN t.total_score>85 THEN '超级主线' WHEN t.total_score>=70 THEN '主线'
                 WHEN t.total_score>=60 THEN '轮动热点' ELSE '跟风' END AS mainline_level
        FROM tot t
    )
    SELECT trade_date, industry_level, industry_code, industry_name,
        score_fund, score_trend, score_heat, score_prosperity, score_diffusion,
        total_score, mainline_level, rank_no,
        rs_5d, limit_up_cnt, earnings_yoy,
        JSON_OBJECT('rs_5d',rs_5d,'amount_ratio',amount_ratio,'up_ratio',up_ratio) AS detail_json
    FROM ranked;
  "

  ${data_mysql} -e "
    UPDATE dws_sw_industry_mainline_score_di cur
    JOIN (
        SELECT trade_date, industry_level, industry_code,
            ROUND(AVG(total_score) OVER (PARTITION BY industry_code, industry_level ORDER BY trade_date ROWS BETWEEN 2 PRECEDING AND CURRENT ROW),2) AS total_score_ma3,
            ROUND(AVG(total_score) OVER (PARTITION BY industry_code, industry_level ORDER BY trade_date ROWS BETWEEN 4 PRECEDING AND CURRENT ROW),2) AS total_score_ma5,
            ROUND(AVG(total_score) OVER (PARTITION BY industry_code, industry_level ORDER BY trade_date ROWS BETWEEN 9 PRECEDING AND CURRENT ROW),2) AS total_score_ma10
        FROM dws_sw_industry_mainline_score_di WHERE trade_date <= '${v_date}'
    ) x ON cur.trade_date=x.trade_date AND cur.industry_level=x.industry_level AND cur.industry_code=x.industry_code
    SET cur.total_score_ma3=x.total_score_ma3, cur.total_score_ma5=x.total_score_ma5, cur.total_score_ma10=x.total_score_ma10
    WHERE cur.trade_date='${v_date}';
  "

  echo "OK ${v_date} diffusion_rows=${diff_cnt}"
  ${data_mysql} -e "
    SELECT trade_date, industry_level, industry_name, total_score, mainline_level, rank_no
    FROM dws_sw_industry_mainline_score_di
    WHERE trade_date='${v_date}' AND industry_level='L1'
    ORDER BY rank_no LIMIT 10;
  "
}

fail_cnt=0
for cur_date in $(get_continuous_date "${n_date_s}" "${n_date_e}"); do
  if ! load_sw_mainline_score "${cur_date}"; then
    fail_cnt=$((fail_cnt + 1))
  fi
done

if [[ "${fail_cnt}" -gt 0 ]]; then
  echo "DONE with ${fail_cnt} skipped day(s)"
  exit 1
fi
echo "DONE all days"
