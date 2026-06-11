#!/bin/bash
# =============================================================================
# target_table: dws_dc_industry_mainline_score_di
# source_table: dwm_dc_industry_fund_flow_di, dwm_dc_industry_trend_strength_di,
#               dwm_dc_industry_market_heat_di, dwm_dc_industry_prosperity_di,
#               dwm_dc_industry_diffusion_di
# 东财板块主线五维评分与排名（DWS 主题层）
#
# 口径（需求1）：
#   子因子截面 PERCENT_RANK×100 → 维内加权 → 五维加权总分
#   资金 35%：流入强度40%+连续净流入30%+加速度20%+超大单占比10%
#   趋势 25%：RS5d40%+均线多头30%+60日新高20%+回撤修复10%(recovery_days越小越好)
#   热度 15%：成交额占比50%+涨停扩散30%+换手率20%（不含 App 热榜排名）
#   景气 15%：业绩增速50%+预期修正30%+上调评级20%
#   扩散 10%：上涨占比50%+20cm涨停30%+晋级率20%
#   缺失维度按权重降权；维内缺失子因子同样降权
#
# 用法（必须用 bash）:
#   bash dw-dws/pro_dws_dc_industry_mainline_score_di.sh
#   bash dw-dws/pro_dws_dc_industry_mainline_score_di.sh 20260527
#   或: run_dws_dc_industry_mainline_score 20260527
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
exec 1>>"${LOG_PATH}/pro_dws_dc_industry_mainline_score_di_${n_date}.log"
exec 2>>"${LOG_PATH}/pro_dws_dc_industry_mainline_score_di_${n_date}.log"

echo "======== $(date '+%F %T') pro_dws_dc_industry_mainline_score_di ${n_date_s} ~ ${n_date_e} ========"

${data_mysql} -e "
CREATE TABLE IF NOT EXISTS dws_dc_industry_mainline_score_di (
    id                  BIGINT PRIMARY KEY AUTO_INCREMENT,
    trade_date          DATE           NOT NULL COMMENT '交易日期',
    content_type        VARCHAR(32)    NULL COMMENT '板块类型(行业/概念/地域)',
    industry_code       VARCHAR(32)    NOT NULL COMMENT '板块代码(东财)',
    industry_name       VARCHAR(128)   NULL COMMENT '板块名称',
    score_fund          DECIMAL(10, 2) NULL COMMENT '资金强度得分0-100',
    score_trend         DECIMAL(10, 2) NULL COMMENT '趋势强度得分0-100',
    score_heat          DECIMAL(10, 2) NULL COMMENT '市场热度得分0-100',
    score_prosperity    DECIMAL(10, 2) NULL COMMENT '产业景气得分0-100',
    score_diffusion     DECIMAL(10, 2) NULL COMMENT '扩散效应得分0-100',
    total_score         DECIMAL(10, 2) NULL COMMENT '五维加权总分',
    total_score_ma3     DECIMAL(10, 2) NULL COMMENT '总分3日均(按入库序)',
    total_score_ma5     DECIMAL(10, 2) NULL COMMENT '总分5日均',
    total_score_ma10    DECIMAL(10, 2) NULL COMMENT '总分10日均',
    mainline_level      VARCHAR(16)    NULL COMMENT '超级主线/主线/轮动热点/跟风',
    rank_no             INT            NULL COMMENT '总分排名(同类型内)',
    fund_cont_days      INT            NULL COMMENT '连续净流入天数',
    rs_5d               DECIMAL(20, 6) NULL COMMENT '5日相对强度',
    limit_up_cnt        INT            NULL COMMENT '涨停家数',
    profit_yoy          DECIMAL(20, 6) NULL COMMENT '业绩增速代理(%)',
    detail_json         JSON           NULL COMMENT '子因子原始值快照',
    created_at          DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at          DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_dws_dc_mainline_score (trade_date, industry_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='东财板块主线五维评分(DWS)';
"

load_dc_mainline_score() {
  local n_date="$1"
  local v_date
  v_date="$(format_date "${n_date}")"
  echo "DEBUG load_dc_mainline_score: n_date=${n_date} v_date=${v_date}"

  local fund_cnt
  fund_cnt="$(${data_mysql} -N -e "
    SELECT COUNT(*) FROM dwm_dc_industry_fund_flow_di WHERE trade_date = '${v_date}';
  ")"
  if [[ -z "${fund_cnt}" || "${fund_cnt}" -eq 0 ]]; then
    echo "WARN: skip ${v_date}, dwm_dc_industry_fund_flow_di has no rows"
    return 1
  fi

  ${data_mysql} -e "
    DELETE FROM dws_dc_industry_mainline_score_di WHERE trade_date = '${v_date}';

    INSERT INTO dws_dc_industry_mainline_score_di (
        trade_date,
        content_type,
        industry_code,
        industry_name,
        score_fund,
        score_trend,
        score_heat,
        score_prosperity,
        score_diffusion,
        total_score,
        mainline_level,
        rank_no,
        fund_cont_days,
        rs_5d,
        limit_up_cnt,
        profit_yoy,
        detail_json
    )
    WITH base AS (
        SELECT
            f.trade_date,
            f.content_type,
            f.industry_code,
            f.industry_name,
            f.fund_inflow_strength,
            f.net_inflow_days,
            f.fund_accel,
            f.elg_net_ratio,
            t.rs_5d,
            t.ma_bullish,
            t.is_new_high_60d,
            t.recovery_days,
            h.amount_ratio,
            h.limit_up_ratio,
            h.turnover_rate,
            h.limit_up_cnt,
            p.earnings_yoy,
            p.forecast_rev_pct,
            p.upgrade_ratio,
            d.up_ratio,
            d.limit_up_20cm_ratio,
            d.continue_limit_ratio
        FROM dwm_dc_industry_fund_flow_di f
        LEFT JOIN dwm_dc_industry_trend_strength_di t
          ON f.trade_date = t.trade_date AND f.industry_code = t.industry_code
        LEFT JOIN dwm_dc_industry_market_heat_di h
          ON f.trade_date = h.trade_date AND f.industry_code = h.industry_code
        LEFT JOIN dwm_dc_industry_prosperity_di p
          ON f.trade_date = p.trade_date AND f.industry_code = p.industry_code
        LEFT JOIN dwm_dc_industry_diffusion_di d
          ON f.trade_date = d.trade_date AND f.industry_code = d.industry_code
        WHERE f.trade_date = '${v_date}'
    ),
    pct AS (
        SELECT
            b.*,
            100 * PERCENT_RANK() OVER (PARTITION BY trade_date, content_type ORDER BY fund_inflow_strength) AS pr_fis,
            100 * PERCENT_RANK() OVER (PARTITION BY trade_date, content_type ORDER BY net_inflow_days) AS pr_nid,
            100 * PERCENT_RANK() OVER (PARTITION BY trade_date, content_type ORDER BY fund_accel) AS pr_fa,
            100 * PERCENT_RANK() OVER (PARTITION BY trade_date, content_type ORDER BY elg_net_ratio) AS pr_elg,
            100 * PERCENT_RANK() OVER (PARTITION BY trade_date, content_type ORDER BY rs_5d) AS pr_rs5,
            100 * PERCENT_RANK() OVER (PARTITION BY trade_date, content_type ORDER BY ma_bullish) AS pr_mab,
            100 * PERCENT_RANK() OVER (PARTITION BY trade_date, content_type ORDER BY is_new_high_60d) AS pr_nh,
            100 * PERCENT_RANK() OVER (PARTITION BY trade_date, content_type ORDER BY recovery_days DESC) AS pr_rec,
            100 * PERCENT_RANK() OVER (PARTITION BY trade_date, content_type ORDER BY amount_ratio) AS pr_amt,
            100 * PERCENT_RANK() OVER (PARTITION BY trade_date, content_type ORDER BY limit_up_ratio) AS pr_lur,
            100 * PERCENT_RANK() OVER (PARTITION BY trade_date, content_type ORDER BY turnover_rate) AS pr_tr,
            100 * PERCENT_RANK() OVER (PARTITION BY trade_date, content_type ORDER BY earnings_yoy) AS pr_ey,
            100 * PERCENT_RANK() OVER (PARTITION BY trade_date, content_type ORDER BY forecast_rev_pct) AS pr_fr,
            100 * PERCENT_RANK() OVER (PARTITION BY trade_date, content_type ORDER BY upgrade_ratio) AS pr_ur,
            100 * PERCENT_RANK() OVER (PARTITION BY trade_date, content_type ORDER BY up_ratio) AS pr_up,
            100 * PERCENT_RANK() OVER (PARTITION BY trade_date, content_type ORDER BY limit_up_20cm_ratio) AS pr_20,
            100 * PERCENT_RANK() OVER (PARTITION BY trade_date, content_type ORDER BY continue_limit_ratio) AS pr_clr
        FROM base b
    ),
    dim AS (
        SELECT
            p.*,
            ROUND(
                (
                    IF(pr_fis IS NOT NULL, 0.4 * pr_fis, 0)
                  + IF(pr_nid IS NOT NULL, 0.3 * pr_nid, 0)
                  + IF(pr_fa IS NOT NULL, 0.2 * pr_fa, 0)
                  + IF(pr_elg IS NOT NULL, 0.1 * pr_elg, 0)
                ) / NULLIF(
                    IF(pr_fis IS NOT NULL, 0.4, 0)
                  + IF(pr_nid IS NOT NULL, 0.3, 0)
                  + IF(pr_fa IS NOT NULL, 0.2, 0)
                  + IF(pr_elg IS NOT NULL, 0.1, 0), 0
                ), 2
            ) AS score_fund,
            ROUND(
                (
                    IF(pr_rs5 IS NOT NULL, 0.4 * pr_rs5, 0)
                  + IF(pr_mab IS NOT NULL, 0.3 * pr_mab, 0)
                  + IF(pr_nh IS NOT NULL, 0.2 * pr_nh, 0)
                  + IF(pr_rec IS NOT NULL, 0.1 * pr_rec, 0)
                ) / NULLIF(
                    IF(pr_rs5 IS NOT NULL, 0.4, 0)
                  + IF(pr_mab IS NOT NULL, 0.3, 0)
                  + IF(pr_nh IS NOT NULL, 0.2, 0)
                  + IF(pr_rec IS NOT NULL, 0.1, 0), 0
                ), 2
            ) AS score_trend,
            ROUND(
                (
                    IF(pr_amt IS NOT NULL, 0.5 * pr_amt, 0)
                  + IF(pr_lur IS NOT NULL, 0.3 * pr_lur, 0)
                  + IF(pr_tr IS NOT NULL, 0.2 * pr_tr, 0)
                ) / NULLIF(
                    IF(pr_amt IS NOT NULL, 0.5, 0)
                  + IF(pr_lur IS NOT NULL, 0.3, 0)
                  + IF(pr_tr IS NOT NULL, 0.2, 0), 0
                ), 2
            ) AS score_heat,
            ROUND(
                (
                    IF(pr_ey IS NOT NULL, 0.5 * pr_ey, 0)
                  + IF(pr_fr IS NOT NULL, 0.3 * pr_fr, 0)
                  + IF(pr_ur IS NOT NULL, 0.2 * pr_ur, 0)
                ) / NULLIF(
                    IF(pr_ey IS NOT NULL, 0.5, 0)
                  + IF(pr_fr IS NOT NULL, 0.3, 0)
                  + IF(pr_ur IS NOT NULL, 0.2, 0), 0
                ), 2
            ) AS score_prosperity,
            ROUND(
                (
                    IF(pr_up IS NOT NULL, 0.5 * pr_up, 0)
                  + IF(pr_20 IS NOT NULL, 0.3 * pr_20, 0)
                  + IF(pr_clr IS NOT NULL, 0.2 * pr_clr, 0)
                ) / NULLIF(
                    IF(pr_up IS NOT NULL, 0.5, 0)
                  + IF(pr_20 IS NOT NULL, 0.3, 0)
                  + IF(pr_clr IS NOT NULL, 0.2, 0), 0
                ), 2
            ) AS score_diffusion
        FROM pct p
    ),
    tot AS (
        SELECT
            d.*,
            ROUND(
                (
                    IF(score_fund IS NOT NULL, 35 * score_fund, 0)
                  + IF(score_trend IS NOT NULL, 25 * score_trend, 0)
                  + IF(score_heat IS NOT NULL, 15 * score_heat, 0)
                  + IF(score_prosperity IS NOT NULL, 15 * score_prosperity, 0)
                  + IF(score_diffusion IS NOT NULL, 10 * score_diffusion, 0)
                ) / NULLIF(
                    IF(score_fund IS NOT NULL, 35, 0)
                  + IF(score_trend IS NOT NULL, 25, 0)
                  + IF(score_heat IS NOT NULL, 15, 0)
                  + IF(score_prosperity IS NOT NULL, 15, 0)
                  + IF(score_diffusion IS NOT NULL, 10, 0), 0
                ), 2
            ) AS total_score
        FROM dim d
    ),
    ranked AS (
        SELECT
            t.*,
            ROW_NUMBER() OVER (
                PARTITION BY t.trade_date, t.content_type
                ORDER BY t.total_score DESC
            ) AS rank_no,
            CASE
                WHEN t.total_score > 85 THEN '超级主线'
                WHEN t.total_score >= 70 THEN '主线'
                WHEN t.total_score >= 60 THEN '轮动热点'
                ELSE '跟风'
            END AS mainline_level
        FROM tot t
    )
    SELECT
        trade_date,
        content_type,
        industry_code,
        industry_name,
        score_fund,
        score_trend,
        score_heat,
        score_prosperity,
        score_diffusion,
        total_score,
        mainline_level,
        rank_no,
        net_inflow_days AS fund_cont_days,
        rs_5d,
        limit_up_cnt,
        earnings_yoy AS profit_yoy,
        JSON_OBJECT(
            'fund_inflow_strength', fund_inflow_strength,
            'net_inflow_days', net_inflow_days,
            'fund_accel', fund_accel,
            'rs_5d', rs_5d,
            'amount_ratio', amount_ratio,
            'limit_up_ratio', limit_up_ratio,
            'earnings_yoy', earnings_yoy,
            'up_ratio', up_ratio,
            'limit_up_20cm_ratio', limit_up_20cm_ratio
        ) AS detail_json
    FROM ranked;
  "

  ${data_mysql} -e "
    UPDATE dws_dc_industry_mainline_score_di cur
    JOIN (
        SELECT
            trade_date,
            industry_code,
            ROUND(AVG(total_score) OVER (
                PARTITION BY industry_code ORDER BY trade_date
                ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
            ), 2) AS total_score_ma3,
            ROUND(AVG(total_score) OVER (
                PARTITION BY industry_code ORDER BY trade_date
                ROWS BETWEEN 4 PRECEDING AND CURRENT ROW
            ), 2) AS total_score_ma5,
            ROUND(AVG(total_score) OVER (
                PARTITION BY industry_code ORDER BY trade_date
                ROWS BETWEEN 9 PRECEDING AND CURRENT ROW
            ), 2) AS total_score_ma10
        FROM dws_dc_industry_mainline_score_di
        WHERE trade_date <= '${v_date}'
    ) x ON cur.trade_date = x.trade_date AND cur.industry_code = x.industry_code
    SET
        cur.total_score_ma3 = x.total_score_ma3,
        cur.total_score_ma5 = x.total_score_ma5,
        cur.total_score_ma10 = x.total_score_ma10
    WHERE cur.trade_date = '${v_date}';
  "

  echo "OK ${v_date} fund_rows=${fund_cnt}"
  ${data_mysql} -e "
    SELECT trade_date, content_type, industry_name, total_score, mainline_level, rank_no,
           score_fund, score_trend, score_heat, score_prosperity, score_diffusion
    FROM dws_dc_industry_mainline_score_di
    WHERE trade_date = '${v_date}' AND content_type = '行业'
    ORDER BY rank_no
    LIMIT 10;
  "
}

fail_cnt=0
for cur_date in $(get_continuous_date "${n_date_s}" "${n_date_e}"); do
  if ! load_dc_mainline_score "${cur_date}"; then
    fail_cnt=$((fail_cnt + 1))
  fi
done

if [[ "${fail_cnt}" -gt 0 ]]; then
  echo "DONE with ${fail_cnt} skipped day(s)"
  exit 1
fi
echo "DONE all days"
