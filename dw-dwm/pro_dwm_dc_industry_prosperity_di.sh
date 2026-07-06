#!/bin/bash
# =============================================================================
# target_table: dwm_dc_industry_prosperity_di
# source_table: ods_dc_member_di, ods_dc_index_di, ods_fina_indicator, ods_report_rc_di
# 东财板块产业景气（基本面因子，供五维评分「产业景气」维 raw 层）
#
# 指标口径（对齐需求文档 §4.2 / §5.1 景气类）：
#   earnings_yoy       = 成分股最新财报归母净利润同比增速(%) 的等权均值（ann_date<=trade_date 时点）
#   earnings_q_yoy     = 成分股单季度净利润同比增速(%) 均值
#   roe_avg            = 成分股 ROE 均值
#   forecast_np_avg    = 近30自然日卖方研报预测净利润(np,万元) 成分均值
#   forecast_rev_pct   = 近30日 vs 前30日 forecast_np_avg 变化率(%)
#   upgrade_ratio      = 近30日研报中评级含买/增持/推荐占比
#   report_cnt_30d     = 近30日研报条数（成分股汇总）
#   report_cnt_mom     = 研报条数环比 = (近30日−前30日)/前30日×100
#   policy_score       = 政策热度占位(默认0，后续人工/NLP 写入)
#   prosperity_rank    = 当日 earnings_yoy 降序排名（同 content_type 内）
#
# 要点：
#   - 板块范围 idx_type 行业/概念/地域，与资金/趋势 DWM 对齐
#   - 财务为季频稀疏数据，fina_coverage_cnt 记录有财报成分数
#   - 标准化 0–100 在 DWS/评分引擎做，本表仅落原始因子
#
# 用法（必须用 bash，不要用 sh）:
#   bash dw-dwm/pro_dwm_dc_industry_prosperity_di.sh              # 默认昨日
#   bash dw-dwm/pro_dwm_dc_industry_prosperity_di.sh 20260527
#   bash dw-dwm/pro_dwm_dc_industry_prosperity_di.sh 20260501 20260527
#   或: run_dwm_dc_industry_prosperity 20260527  （先 source dw-utils/func.sh）
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
exec 1>>"${LOG_PATH}/pro_dwm_dc_industry_prosperity_di_${n_date}.log"
exec 2>>"${LOG_PATH}/pro_dwm_dc_industry_prosperity_di_${n_date}.log"

echo "======== $(date '+%F %T') pro_dwm_dc_industry_prosperity_di ${n_date_s} ~ ${n_date_e} ========"

${data_mysql} -e "
CREATE TABLE IF NOT EXISTS dwm_dc_industry_prosperity_di (
    id                    BIGINT PRIMARY KEY AUTO_INCREMENT,
    trade_date            DATE           NOT NULL COMMENT '交易日期(快照日)',
    content_type          VARCHAR(32)    NULL COMMENT '板块类型(行业/概念/地域)',
    industry_code         VARCHAR(32)    NOT NULL COMMENT '板块代码(东财)',
    industry_name         VARCHAR(128)   NULL COMMENT '板块名称',
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
    policy_score          DECIMAL(10, 4) NOT NULL DEFAULT 0 COMMENT '政策热度(占位,0-1或0-100)',
    prosperity_rank       INT            NULL COMMENT 'earnings_yoy降序排名(同类型内)',
    created_at            DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at            DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_dwm_dc_industry_prosperity (trade_date, industry_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='东财板块产业景气(DWM,成分股财务+卖方预测聚合)';
"

load_dc_industry_prosperity() {
  local n_date="$1"
  local v_date v_date_30 v_date_60
  v_date="$(format_date "${n_date}")"
  v_date_30="$(date -d "${n_date} 30 day ago" +%Y-%m-%d)"
  v_date_60="$(date -d "${n_date} 60 day ago" +%Y-%m-%d)"
  echo "DEBUG load_dc_industry_prosperity: n_date=${n_date} v_date=${v_date}"

  local mem_cnt
  mem_cnt="$(${data_mysql} -N -e "
    SELECT COUNT(*)
    FROM ods_dc_member_di
    WHERE trade_date = '${v_date}';
  ")"
  if [[ -z "${mem_cnt}" || "${mem_cnt}" -eq 0 ]]; then
    echo "WARN: skip ${v_date}, ods_dc_member_di has no rows"
    return 1
  fi

  ${data_mysql} -e "
    DELETE FROM dwm_dc_industry_prosperity_di WHERE trade_date = '${v_date}';

    INSERT INTO dwm_dc_industry_prosperity_di (
        trade_date,
        content_type,
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
    board_info AS (
        SELECT
            i.ts_code AS industry_code,
            i.dc_name AS industry_name,
            CASE i.idx_type
                WHEN '行业板块' THEN '行业'
                WHEN '概念板块' THEN '概念'
                WHEN '地域板块' THEN '地域'
                ELSE i.idx_type
            END AS content_type
        FROM ods_dc_index_di i
        WHERE i.trade_date = '${v_date}'
          AND i.idx_type IN ('行业板块', '概念板块', '地域板块')
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
            mn.industry_code,
            COUNT(DISTINCT mn.stock_code) AS constituent_cnt,
            COUNT(DISTINCT fl.ts_code) AS fina_coverage_cnt,
            ROUND(AVG(fl.netprofit_yoy), 6) AS earnings_yoy,
            ROUND(AVG(fl.q_profit_yoy), 6) AS earnings_q_yoy,
            ROUND(AVG(fl.roe), 6) AS roe_avg
        FROM member_norm mn
        LEFT JOIN fina_latest fl ON mn.stock_code = fl.ts_code
        GROUP BY mn.industry_code
    ),
    report_join AS (
        SELECT
            mn.industry_code,
            r.report_date,
            r.np,
            r.rating
        FROM member_norm mn
        JOIN ods_report_rc_di r ON mn.stock_code = r.ts_code
        WHERE r.report_date > '${v_date_60}'
          AND r.report_date <= '${v_date}'
    ),
    report_30 AS (
        SELECT
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
        GROUP BY industry_code
    ),
    report_prev AS (
        SELECT
            industry_code,
            COUNT(*) AS report_cnt_prev_30d,
            ROUND(AVG(np), 4) AS forecast_np_avg_prev
        FROM report_join
        WHERE report_date > '${v_date_60}'
          AND report_date <= '${v_date_30}'
        GROUP BY industry_code
    ),
    forecast_board AS (
        SELECT
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
        LEFT JOIN report_prev rp ON r30.industry_code = rp.industry_code
    ),
    merged AS (
        SELECT
            '${v_date}' AS trade_date,
            bi.content_type,
            bi.industry_code,
            bi.industry_name,
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
        FROM board_info bi
        LEFT JOIN fina_board fb ON bi.industry_code = fb.industry_code
        LEFT JOIN forecast_board fc ON bi.industry_code = fc.industry_code
    ),
    ranked AS (
        SELECT
            m.*,
            ROW_NUMBER() OVER (
                PARTITION BY m.trade_date, m.content_type
                ORDER BY m.earnings_yoy DESC
            ) AS prosperity_rank
        FROM merged m
    )
    SELECT
        trade_date,
        content_type,
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

  echo "OK ${v_date} dc_member_rows=${mem_cnt}"
  ${data_mysql} -e "
    SELECT trade_date, content_type, industry_code, industry_name,
           earnings_yoy, forecast_rev_pct, upgrade_ratio, report_cnt_30d, prosperity_rank
    FROM dwm_dc_industry_prosperity_di
    WHERE trade_date = '${v_date}'
    ORDER BY earnings_yoy DESC
    LIMIT 5;
  "
}

run_dwm_by_trading_day "${n_date_s}" "${n_date_e}" load_dc_industry_prosperity || exit $?
