#!/bin/bash
# =============================================================================
# target_table: dwm_sw_industry_prosperity_di
# source_table: ods_index_member_all, ods_fina_indicator, ods_report_rc_di
# 申万行业产业景气：按 L1/L2/L3 成分股聚合财务与卖方预测（主线评分默认行业体系）
#
# 指标口径：同 dwm_dc_industry_prosperity_di（业绩增速、预期修正、研报热度）
# 行业层级 industry_level = L1 / L2 / L3，对应 index_member_all 的 l1/l2/l3 代码
#
# 用法（必须用 bash，不要用 sh）:
#   bash dw-dwm/pro_dwm_sw_industry_prosperity_di.sh              # 默认昨日
#   bash dw-dwm/pro_dwm_sw_industry_prosperity_di.sh 20260527
#   bash dw-dwm/pro_dwm_sw_industry_prosperity_di.sh 20260501 20260527
#   或: run_dwm_sw_industry_prosperity 20260527  （先 source dw-utils/func.sh）
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
exec 1>>"${LOG_PATH}/pro_dwm_sw_industry_prosperity_di_${n_date}.log"
exec 2>>"${LOG_PATH}/pro_dwm_sw_industry_prosperity_di_${n_date}.log"

echo "======== $(date '+%F %T') pro_dwm_sw_industry_prosperity_di ${n_date_s} ~ ${n_date_e} ========"

${data_mysql} -e "
CREATE TABLE IF NOT EXISTS dwm_sw_industry_prosperity_di (
    id                    BIGINT PRIMARY KEY AUTO_INCREMENT,
    trade_date            DATE           NOT NULL COMMENT '交易日期(快照日)',
    industry_level        VARCHAR(8)     NOT NULL COMMENT '申万层级 L1/L2/L3',
    industry_code         VARCHAR(32)    NOT NULL COMMENT '申万行业代码',
    industry_name         VARCHAR(128)   NULL COMMENT '申万行业名称',
    constituent_cnt       INT            NOT NULL DEFAULT 0 COMMENT '成分股数',
    fina_coverage_cnt     INT            NOT NULL DEFAULT 0 COMMENT '有最新财报指标的成分股数',
    earnings_yoy          DECIMAL(20, 6) NULL COMMENT '归母净利润同比增速均值(%)',
    earnings_q_yoy        DECIMAL(20, 6) NULL COMMENT '单季度净利润同比增速均值(%)',
    roe_avg               DECIMAL(20, 6) NULL COMMENT 'ROE均值(%)',
    forecast_np_avg       DECIMAL(20, 4) NULL COMMENT '近30日研报预测净利润均值(万元)',
    forecast_rev_pct      DECIMAL(20, 6) NULL COMMENT '预测净利润30日环比变化率(%)',
    upgrade_ratio         DECIMAL(20, 6) NULL COMMENT '近30日研报上调评级占比',
    report_cnt_30d        INT            NOT NULL DEFAULT 0 COMMENT '近30日研报条数',
    report_cnt_mom        DECIMAL(20, 6) NULL COMMENT '研报条数环比(相对前30日,%)',
    policy_score          DECIMAL(10, 4) NOT NULL DEFAULT 0 COMMENT '政策热度(占位)',
    prosperity_rank       INT            NULL COMMENT 'earnings_yoy降序排名(同层级内)',
    created_at            DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at            DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_dwm_sw_industry_prosperity (trade_date, industry_level, industry_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='申万行业产业景气(DWM,成分股财务+卖方预测聚合)';
"

load_sw_industry_prosperity() {
  local n_date="$1"
  local v_date v_date_30 v_date_60
  v_date="$(format_date "${n_date}")"
  v_date_30="$(date -d "${n_date} 30 day ago" +%Y-%m-%d)"
  v_date_60="$(date -d "${n_date} 60 day ago" +%Y-%m-%d)"
  echo "DEBUG load_sw_industry_prosperity: n_date=${n_date} v_date=${v_date}"

  local mem_cnt
  mem_cnt="$(${data_mysql} -N -e "
    SELECT COUNT(*)
    FROM ods_index_member_all
    WHERE IFNULL(is_new, 'Y') = 'Y';
  ")"
  if [[ -z "${mem_cnt}" || "${mem_cnt}" -eq 0 ]]; then
    echo "WARN: skip ${v_date}, ods_index_member_all has no rows"
    return 1
  fi

  ${data_mysql} -e "
    DELETE FROM dwm_sw_industry_prosperity_di WHERE trade_date = '${v_date}';

    INSERT INTO dwm_sw_industry_prosperity_di (
        trade_date,
        industry_level,
        industry_code,
        industry_name,
        constituent_cnt,
        fina_coverage_cnt,
        earnings_yoy,
        earnings_q_yoy,
        roe_avg,
        forecast_np_avg,
        forecast_rev_pct,
        upgrade_ratio,
        report_cnt_30d,
        report_cnt_mom,
        policy_score,
        prosperity_rank
    )
    WITH member_expand AS (
        SELECT 'L1' AS industry_level, m.l1_code AS industry_code, m.l1_name AS industry_name, m.ts_code AS stock_code
        FROM ods_index_member_all m
        WHERE IFNULL(m.is_new, 'Y') = 'Y' AND m.l1_code IS NOT NULL AND TRIM(m.l1_code) <> ''
        UNION ALL
        SELECT 'L2', m.l2_code, m.l2_name, m.ts_code
        FROM ods_index_member_all m
        WHERE IFNULL(m.is_new, 'Y') = 'Y' AND m.l2_code IS NOT NULL AND TRIM(m.l2_code) <> ''
        UNION ALL
        SELECT 'L3', m.l3_code, m.l3_name, m.ts_code
        FROM ods_index_member_all m
        WHERE IFNULL(m.is_new, 'Y') = 'Y' AND m.l3_code IS NOT NULL AND TRIM(m.l3_code) <> ''
    ),
    fina_ranked AS (
        SELECT
            f.ts_code,
            f.netprofit_yoy,
            f.q_profit_yoy,
            f.roe,
            ROW_NUMBER() OVER (
                PARTITION BY f.ts_code
                ORDER BY f.end_date DESC, f.ann_date DESC
            ) AS rn
        FROM ods_fina_indicator f
        WHERE f.ann_date <= '${v_date}'
    ),
    fina_latest AS (
        SELECT ts_code, netprofit_yoy, q_profit_yoy, roe
        FROM fina_ranked
        WHERE rn = 1
    ),
    fina_board AS (
        SELECT
            me.industry_level,
            me.industry_code,
            MAX(me.industry_name) AS industry_name,
            COUNT(DISTINCT me.stock_code) AS constituent_cnt,
            COUNT(DISTINCT fl.ts_code) AS fina_coverage_cnt,
            ROUND(AVG(fl.netprofit_yoy), 6) AS earnings_yoy,
            ROUND(AVG(fl.q_profit_yoy), 6) AS earnings_q_yoy,
            ROUND(AVG(fl.roe), 6) AS roe_avg
        FROM member_expand me
        LEFT JOIN fina_latest fl ON me.stock_code = fl.ts_code
        GROUP BY me.industry_level, me.industry_code
    ),
    report_join AS (
        SELECT
            me.industry_level,
            me.industry_code,
            r.report_date,
            r.np,
            r.rating
        FROM member_expand me
        JOIN ods_report_rc_di r ON me.stock_code = r.ts_code
        WHERE r.report_date > '${v_date_60}'
          AND r.report_date <= '${v_date}'
    ),
    report_30 AS (
        SELECT
            industry_level,
            industry_code,
            COUNT(*) AS report_cnt_30d,
            ROUND(AVG(np), 4) AS forecast_np_avg,
            SUM(
                CASE
                    WHEN rating IS NOT NULL
                     AND (
                        rating LIKE '%买%'
                        OR rating LIKE '%增持%'
                        OR rating LIKE '%推荐%'
                        OR rating LIKE '%强推%'
                        OR UPPER(rating) IN ('BUY', 'OVERWEIGHT', 'OUTPERFORM')
                     )
                    THEN 1 ELSE 0
                END
            ) AS upgrade_cnt,
            SUM(CASE WHEN rating IS NOT NULL AND TRIM(rating) <> '' THEN 1 ELSE 0 END) AS rated_cnt
        FROM report_join
        WHERE report_date > '${v_date_30}'
          AND report_date <= '${v_date}'
        GROUP BY industry_level, industry_code
    ),
    report_prev AS (
        SELECT
            industry_level,
            industry_code,
            COUNT(*) AS report_cnt_prev_30d,
            ROUND(AVG(np), 4) AS forecast_np_avg_prev
        FROM report_join
        WHERE report_date > '${v_date_60}'
          AND report_date <= '${v_date_30}'
        GROUP BY industry_level, industry_code
    ),
    forecast_board AS (
        SELECT
            r30.industry_level,
            r30.industry_code,
            IFNULL(r30.report_cnt_30d, 0) AS report_cnt_30d,
            r30.forecast_np_avg,
            CASE
                WHEN rp.forecast_np_avg_prev IS NOT NULL AND rp.forecast_np_avg_prev <> 0
                THEN ROUND(
                    (r30.forecast_np_avg - rp.forecast_np_avg_prev)
                    / ABS(rp.forecast_np_avg_prev) * 100, 6
                )
                ELSE NULL
            END AS forecast_rev_pct,
            CASE
                WHEN r30.rated_cnt > 0
                THEN ROUND(r30.upgrade_cnt / r30.rated_cnt, 6)
                ELSE NULL
            END AS upgrade_ratio,
            CASE
                WHEN IFNULL(rp.report_cnt_prev_30d, 0) > 0
                THEN ROUND(
                    (IFNULL(r30.report_cnt_30d, 0) - rp.report_cnt_prev_30d)
                    / rp.report_cnt_prev_30d * 100, 6
                )
                ELSE NULL
            END AS report_cnt_mom
        FROM report_30 r30
        LEFT JOIN report_prev rp
          ON r30.industry_level = rp.industry_level
         AND r30.industry_code = rp.industry_code
    ),
    merged AS (
        SELECT
            '${v_date}' AS trade_date,
            fb.industry_level,
            fb.industry_code,
            fb.industry_name,
            IFNULL(fb.constituent_cnt, 0) AS constituent_cnt,
            IFNULL(fb.fina_coverage_cnt, 0) AS fina_coverage_cnt,
            fb.earnings_yoy,
            fb.earnings_q_yoy,
            fb.roe_avg,
            fc.forecast_np_avg,
            fc.forecast_rev_pct,
            fc.upgrade_ratio,
            IFNULL(fc.report_cnt_30d, 0) AS report_cnt_30d,
            fc.report_cnt_mom,
            0 AS policy_score
        FROM fina_board fb
        LEFT JOIN forecast_board fc
          ON fb.industry_level = fc.industry_level
         AND fb.industry_code = fc.industry_code
    ),
    ranked AS (
        SELECT
            m.*,
            ROW_NUMBER() OVER (
                PARTITION BY m.trade_date, m.industry_level
                ORDER BY m.earnings_yoy DESC
            ) AS prosperity_rank
        FROM merged m
    )
    SELECT
        trade_date,
        industry_level,
        industry_code,
        industry_name,
        constituent_cnt,
        fina_coverage_cnt,
        earnings_yoy,
        earnings_q_yoy,
        roe_avg,
        forecast_np_avg,
        forecast_rev_pct,
        upgrade_ratio,
        report_cnt_30d,
        report_cnt_mom,
        policy_score,
        prosperity_rank
    FROM ranked;
  "

  echo "OK ${v_date} sw_member_rows=${mem_cnt}"
  ${data_mysql} -e "
    SELECT trade_date, industry_level, industry_code, industry_name,
           earnings_yoy, forecast_rev_pct, prosperity_rank
    FROM dwm_sw_industry_prosperity_di
    WHERE trade_date = '${v_date}' AND industry_level = 'L1'
    ORDER BY earnings_yoy DESC
    LIMIT 5;
  "
}

fail_cnt=0
for cur_date in $(get_continuous_date "${n_date_s}" "${n_date_e}"); do
  if ! load_sw_industry_prosperity "${cur_date}"; then
    fail_cnt=$((fail_cnt + 1))
  fi
done

if [[ "${fail_cnt}" -gt 0 ]]; then
  echo "DONE with ${fail_cnt} skipped day(s)"
  exit 1
fi
echo "DONE all days"
