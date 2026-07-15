#!/bin/bash
# =============================================================================
# target_table: dws_dc_industry_mainline_monitor_di
# source_table: dws_dc_industry_mainline_score_di + dwm_dc_* (补充监控因子)
# 东财板块主线监控表（需求1 §4.4 每日输出物）
#
# 字段：排名、行业、主线得分(默认5日均)、资金连续流入、RS5d、涨停数、业绩增速、等级、阶段
# 阶段规则（v1.1）：
#   机构化：映射 ETF 近5交易日份额净增 + 主线分>=70 + 连续净流入>=3天 + RS5d>0
#   板块爆发：rs_5d>0 且 涨停扩散率>=同类型P80 且 连续净流入>=2天
#   资金试探：fund_accel>0 且 连续净流入>=1天
#   否则：观察
#
# 用法:
#   bash dw-dws/pro_dws_dc_industry_mainline_monitor_di.sh 20260527
#   或: run_dws_dc_industry_mainline_monitor 20260527
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
exec 1>>"${LOG_PATH}/pro_dws_dc_industry_mainline_monitor_di_${n_date}.log"
exec 2>>"${LOG_PATH}/pro_dws_dc_industry_mainline_monitor_di_${n_date}.log"

echo "======== $(date '+%F %T') pro_dws_dc_industry_mainline_monitor_di ${n_date_s} ~ ${n_date_e} ========"

${data_mysql} -e "
CREATE TABLE IF NOT EXISTS dws_dc_industry_mainline_monitor_di (
    id                  BIGINT PRIMARY KEY AUTO_INCREMENT,
    trade_date          DATE           NOT NULL COMMENT '交易日期',
    content_type        VARCHAR(32)    NULL COMMENT '板块类型(行业/概念/地域)',
    industry_code       VARCHAR(32)    NOT NULL COMMENT '板块代码',
    industry_name       VARCHAR(128)   NULL COMMENT '板块名称',
    rank_no             INT            NULL COMMENT '排名(同类型按展示分)',
    main_score          DECIMAL(10, 2) NULL COMMENT '主线得分(默认5日均,无则当日总分)',
    total_score         DECIMAL(10, 2) NULL COMMENT '当日五维总分',
    total_score_ma3     DECIMAL(10, 2) NULL,
    total_score_ma5     DECIMAL(10, 2) NULL,
    total_score_ma10    DECIMAL(10, 2) NULL,
    mainline_level      VARCHAR(16)    NULL COMMENT '超级主线/主线/轮动热点/跟风',
    mainline_stage      VARCHAR(16)    NULL COMMENT '资金试探/板块爆发/机构化/观察',
    fund_cont_days      INT            NULL COMMENT '资金连续净流入天数',
    rs_5d               DECIMAL(20, 6) NULL COMMENT '5日相对强度(%)',
    limit_up_cnt        INT            NULL COMMENT '涨停家数',
    profit_yoy          DECIMAL(20, 6) NULL COMMENT '业绩增速代理(%)',
    amount_ratio        DECIMAL(20, 8) NULL COMMENT '成交额占比',
    limit_up_ratio      DECIMAL(20, 6) NULL COMMENT '涨停扩散率',
    up_ratio            DECIMAL(20, 6) NULL COMMENT '上涨家数占比',
    score_fund          DECIMAL(10, 2) NULL COMMENT '资金维度分',
    score_trend         DECIMAL(10, 2) NULL COMMENT '趋势维度分',
    score_heat          DECIMAL(10, 2) NULL COMMENT '热度维度分',
    score_prosperity    DECIMAL(10, 2) NULL COMMENT '景气维度分',
    score_diffusion     DECIMAL(10, 2) NULL COMMENT '扩散维度分',
    is_top20            TINYINT        NOT NULL DEFAULT 0 COMMENT '是否同类型监控Top20',
    created_at          DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at          DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_dws_dc_mainline_monitor (trade_date, industry_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='东财板块主线监控表(DWS)';
"

load_dc_mainline_monitor() {
  local n_date="$1"
  local v_date
  v_date="$(format_date "${n_date}")"
  echo "DEBUG load_dc_mainline_monitor: n_date=${n_date} v_date=${v_date}"

  local score_cnt
  score_cnt="$(${data_mysql} -N -e "
    SELECT COUNT(*) FROM dws_dc_industry_mainline_score_di WHERE trade_date = '${v_date}';
  ")"
  if [[ -z "${score_cnt}" || "${score_cnt}" -eq 0 ]]; then
    echo "WARN: skip ${v_date}, dws_dc_industry_mainline_score_di has no rows (先跑 run_dws_dc_industry_mainline_score)"
    return 1
  fi

  ${data_mysql} -e "
    DELETE FROM dws_dc_industry_mainline_monitor_di WHERE trade_date = '${v_date}';

    INSERT INTO dws_dc_industry_mainline_monitor_di (
        trade_date,
        content_type,
        industry_code,
        industry_name,
        rank_no,
        main_score,
        total_score,
        total_score_ma3,
        total_score_ma5,
        total_score_ma10,
        mainline_level,
        mainline_stage,
        fund_cont_days,
        rs_5d,
        limit_up_cnt,
        profit_yoy,
        amount_ratio,
        limit_up_ratio,
        up_ratio,
        score_fund,
        score_trend,
        score_heat,
        score_prosperity,
        score_diffusion,
        is_top20
    )
    WITH etf_share_series AS (
        -- 口径说明#8：LAG(total_share,5) 为“前5条物理记录”，非严格交易日对齐(未接交易日历)。
        --   ods_etf_share_size_di 通常按交易日连续入库，物理行≈交易日；如需严格对齐可接 ods_trading_day，暂保留近似。
        SELECT
            es.ts_code,
            es.trade_date,
            es.total_share,
            LAG(es.total_share, 5) OVER (
                PARTITION BY es.ts_code ORDER BY es.trade_date
            ) AS share_lag5
        FROM ods_etf_share_size_di es
        WHERE es.trade_date <= '${v_date}'
    ),
    etf_latest AS (
        SELECT
            ts_code,
            total_share - share_lag5 AS share_chg_5d
        FROM etf_share_series
        WHERE trade_date = '${v_date}'
    ),
    etf_by_sw_name AS (
        SELECT
            dim.industry_name,
            MAX(CASE WHEN IFNULL(el.share_chg_5d, 0) > 0 THEN 1 ELSE 0 END) AS has_etf_inflow
        FROM dim_industry_etf_map dim
        JOIN etf_latest el ON dim.etf_code = el.ts_code
        WHERE dim.is_active = 1
        GROUP BY dim.industry_name
    ),
    dc_etf_match AS (
        -- 修复#8：dim_industry_etf_map.industry_code 为“申万行业代码”，与东财板块代码(BK*.DC)不在同一编码空间，
        --   无法按 industry_code 精确映射；原“双向 LIKE 模糊匹配”易误命中(如子串互相包含)，
        --   故收紧为“板块名称等值匹配”。宁可少命中(机构化阶段仅作加分信号)也不误命中；
        --   东财/申万命名不一致时该匹配偏保守(可能少命中)，属可接受的安全取舍。
        SELECT
            s.industry_code,
            MAX(IFNULL(ei.has_etf_inflow, 0)) AS has_etf_inflow
        FROM dws_dc_industry_mainline_score_di s
        LEFT JOIN etf_by_sw_name ei
          ON s.industry_name = ei.industry_name
        WHERE s.trade_date = '${v_date}'
        GROUP BY s.industry_code
    ),
    enriched AS (
        SELECT
            s.trade_date,
            s.content_type,
            s.industry_code,
            s.industry_name,
            s.total_score,
            s.total_score_ma3,
            s.total_score_ma5,
            s.total_score_ma10,
            s.mainline_level,
            s.fund_cont_days,
            s.rs_5d,
            s.limit_up_cnt,
            s.profit_yoy,
            s.score_fund,
            s.score_trend,
            s.score_heat,
            s.score_prosperity,
            s.score_diffusion,
            COALESCE(s.total_score_ma5, s.total_score) AS main_score,
            h.amount_ratio,
            COALESCE(h.limit_up_ratio, df.limit_up_ratio) AS limit_up_ratio,
            df.up_ratio,
            f.fund_accel,
            f.net_inflow_days,
            IFNULL(em.has_etf_inflow, 0) AS has_etf_inflow,
            100 * PERCENT_RANK() OVER (
                PARTITION BY s.trade_date, s.content_type
                ORDER BY COALESCE(h.limit_up_ratio, df.limit_up_ratio)
            ) AS lur_pctile
        FROM dws_dc_industry_mainline_score_di s
        LEFT JOIN dwm_dc_industry_fund_flow_di f
          ON s.trade_date = f.trade_date AND s.industry_code = f.industry_code
        LEFT JOIN dwm_dc_industry_market_heat_di h
          ON s.trade_date = h.trade_date AND s.industry_code = h.industry_code
        LEFT JOIN dwm_dc_industry_diffusion_di df
          ON s.trade_date = df.trade_date AND s.industry_code = df.industry_code
        LEFT JOIN dc_etf_match em ON s.industry_code = em.industry_code
        WHERE s.trade_date = '${v_date}'
    ),
    staged AS (
        SELECT
            e.*,
            CASE
                WHEN IFNULL(e.has_etf_inflow, 0) = 1
                 AND IFNULL(e.main_score, 0) >= 70
                 AND IFNULL(e.net_inflow_days, 0) >= 3
                 AND IFNULL(e.rs_5d, 0) > 0
                THEN '机构化'
                WHEN e.rs_5d > 0
                 AND e.lur_pctile >= 80
                 AND IFNULL(e.net_inflow_days, 0) >= 2
                THEN '板块爆发'
                WHEN IFNULL(e.fund_accel, 0) > 0
                 AND IFNULL(e.net_inflow_days, 0) >= 1
                THEN '资金试探'
                ELSE '观察'
            END AS mainline_stage
        FROM enriched e
    ),
    ranked AS (
        SELECT
            st.*,
            ROW_NUMBER() OVER (
                PARTITION BY st.trade_date, st.content_type
                ORDER BY st.main_score DESC
            ) AS rank_no
        FROM staged st
    )
    SELECT
        trade_date,
        content_type,
        industry_code,
        industry_name,
        rank_no,
        main_score,
        total_score,
        total_score_ma3,
        total_score_ma5,
        total_score_ma10,
        mainline_level,
        mainline_stage,
        fund_cont_days,
        rs_5d,
        limit_up_cnt,
        profit_yoy,
        amount_ratio,
        limit_up_ratio,
        up_ratio,
        score_fund,
        score_trend,
        score_heat,
        score_prosperity,
        score_diffusion,
        IF(rank_no <= 20, 1, 0) AS is_top20
    FROM ranked;
  "

  echo "OK ${v_date} score_rows=${score_cnt}"
  ${data_mysql} -e "
    SELECT trade_date, rank_no, industry_name, main_score, fund_cont_days,
           rs_5d, limit_up_cnt, profit_yoy, mainline_level, mainline_stage
    FROM dws_dc_industry_mainline_monitor_di
    WHERE trade_date = '${v_date}' AND content_type = '行业'
    ORDER BY rank_no
    LIMIT 15;
  "
}

fail_cnt=0
for cur_date in $(get_continuous_date "${n_date_s}" "${n_date_e}"); do
  if ! load_dc_mainline_monitor "${cur_date}"; then
    fail_cnt=$((fail_cnt + 1))
  fi
done

if [[ "${fail_cnt}" -gt 0 ]]; then
  echo "DONE with ${fail_cnt} skipped day(s)"
  exit 1
fi
echo "DONE all days"
