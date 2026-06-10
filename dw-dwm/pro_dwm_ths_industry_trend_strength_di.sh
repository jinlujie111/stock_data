#!/bin/bash
# =============================================================================
# target_table: dwm_ths_industry_trend_strength_di
# source_table: ods_ths_daily_di, ods_ths_index_di, ods_index_daily_di
# 同花顺板块趋势强度：RS、均线多头、60日新高、回撤修复（结构对齐东财 DWM）
#
# 指标口径（基准=沪深300 000300.SH）：
#   rs_5d / rs_20d     = 板块 N 日涨跌幅累计 − 沪深300 N 日涨跌幅累计(%)
#   ma_bullish         = MA5 > MA10 > MA20 → 1
#   is_new_high_60d    = close 创近60交易日新高 → 1
#   drawdown_pct       = (close − high_60d) / high_60d × 100
#   recovery_days      = 回撤≥3%时距最近一次60日高点的交易日数，否则 0
#   rs_rank            = 当日 rs_5d 降序排名（同 content_type 内）
#
# 要点：
#   - 板块范围 index_type I/N/R（行业/概念/地域），与资金强度 DWM 对齐
#   - 回看窗口 120 自然日（≈85 交易日）
#
# 用法（必须用 bash，不要用 sh）:
#   bash dw-dwm/pro_dwm_ths_industry_trend_strength_di.sh              # 默认昨日
#   bash dw-dwm/pro_dwm_ths_industry_trend_strength_di.sh 20260527
#   bash dw-dwm/pro_dwm_ths_industry_trend_strength_di.sh 20260501 20260527
#   或: run_dwm_ths_industry_trend_strength 20260527  （先 source dw-utils/func.sh）
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
exec 1>>"${LOG_PATH}/pro_dwm_ths_industry_trend_strength_di_${n_date}.log"
exec 2>>"${LOG_PATH}/pro_dwm_ths_industry_trend_strength_di_${n_date}.log"

echo "======== $(date '+%F %T') pro_dwm_ths_industry_trend_strength_di ${n_date_s} ~ ${n_date_e} ========"

${data_mysql} -e "
CREATE TABLE IF NOT EXISTS dwm_ths_industry_trend_strength_di (
    id                    BIGINT PRIMARY KEY AUTO_INCREMENT,
    trade_date            DATE           NOT NULL COMMENT '交易日期',
    content_type          VARCHAR(32)    NULL COMMENT '板块类型(行业/概念/地域)',
    industry_code         VARCHAR(32)    NOT NULL COMMENT '板块代码(同花顺)',
    industry_name         VARCHAR(128)   NULL COMMENT '板块名称',
    close                 DECIMAL(20, 6) NULL COMMENT '收盘点位',
    pct_change            DECIMAL(20, 6) NULL COMMENT '涨跌幅(%)',
    rs_5d                 DECIMAL(20, 6) NULL COMMENT '5日相对强度=板块5日涨幅累计-沪深300(%)',
    rs_20d                DECIMAL(20, 6) NULL COMMENT '20日相对强度=板块20日涨幅累计-沪深300(%)',
    ma5                   DECIMAL(20, 6) NULL COMMENT '5日均线',
    ma10                  DECIMAL(20, 6) NULL COMMENT '10日均线',
    ma20                  DECIMAL(20, 6) NULL COMMENT '20日均线',
    ma_bullish            TINYINT        NOT NULL DEFAULT 0 COMMENT '均线多头MA5>MA10>MA20(1/0)',
    high_60d              DECIMAL(20, 6) NULL COMMENT '近60交易日最高收盘',
    is_new_high_60d       TINYINT        NOT NULL DEFAULT 0 COMMENT '是否创60日新高(1/0)',
    drawdown_pct          DECIMAL(20, 6) NULL COMMENT '相对60日高点回撤(%)',
    recovery_days         INT            NOT NULL DEFAULT 0 COMMENT '回撤>=3%时距最近高点交易日数否则0',
    rs_rank               INT            NULL COMMENT '当日rs_5d排名(同类型内)',
    created_at            DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at            DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_dwm_ths_industry_trend (trade_date, industry_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='同花顺板块趋势强度(DWM,来源ods_ths_daily_di+ods_index_daily_di)';
"

load_ths_industry_trend_strength() {
  local n_date="$1"
  local v_date v_date_120
  v_date="$(format_date "${n_date}")"
  v_date_120="$(date -d "${n_date} 120 day ago" +%Y-%m-%d)"
  echo "DEBUG load_ths_industry_trend_strength: n_date=${n_date} v_date=${v_date} v_date_120=${v_date_120}"

  local ods_cnt bench_cnt
  ods_cnt="$(${data_mysql} -N -e "
    SELECT COUNT(*)
    FROM ods_ths_daily_di
    WHERE trade_date = '${v_date}';
  ")"
  bench_cnt="$(${data_mysql} -N -e "
    SELECT COUNT(*)
    FROM ods_index_daily_di
    WHERE trade_date = '${v_date}' AND ts_code = '000300.SH';
  ")"
  if [[ -z "${ods_cnt}" || "${ods_cnt}" -eq 0 ]]; then
    echo "WARN: skip ${v_date}, ods_ths_daily_di has no rows"
    return 1
  fi
  if [[ -z "${bench_cnt}" || "${bench_cnt}" -eq 0 ]]; then
    echo "WARN: skip ${v_date}, ods_index_daily_di(000300.SH) has no rows"
    return 1
  fi

  ${data_mysql} -e "
    DELETE FROM dwm_ths_industry_trend_strength_di WHERE trade_date = '${v_date}';

    INSERT INTO dwm_ths_industry_trend_strength_di (
        trade_date,
        content_type,
        industry_code,
        industry_name,
        close,
        pct_change,
        rs_5d,
        rs_20d,
        ma5,
        ma10,
        ma20,
        ma_bullish,
        high_60d,
        is_new_high_60d,
        drawdown_pct,
        recovery_days,
        rs_rank
    )
    WITH bench AS (
        SELECT trade_date, pct_chg AS bench_pct
        FROM ods_index_daily_di
        WHERE ts_code = '000300.SH'
          AND trade_date <= '${v_date}'
          AND trade_date >= '${v_date_120}'
    ),
    daily_base AS (
        SELECT
            d.trade_date,
            d.ts_code AS industry_code,
            i.name AS industry_name,
            CASE i.index_type
                WHEN 'I' THEN '行业'
                WHEN 'N' THEN '概念'
                WHEN 'R' THEN '地域'
            END AS content_type,
            d.close,
            d.pct_change,
            b.bench_pct
        FROM ods_ths_daily_di d
        JOIN ods_ths_index_di i
          ON d.ts_code = i.ts_code
         AND i.index_type IN ('I', 'N', 'R')
        JOIN bench b ON d.trade_date = b.trade_date
        WHERE d.trade_date <= '${v_date}'
          AND d.trade_date >= '${v_date_120}'
    ),
    calc AS (
        SELECT
            db.*,
            SUM(db.pct_change) OVER (
                PARTITION BY db.industry_code
                ORDER BY db.trade_date
                ROWS BETWEEN 4 PRECEDING AND CURRENT ROW
            ) AS ret_5d,
            SUM(db.bench_pct) OVER (
                ORDER BY db.trade_date
                ROWS BETWEEN 4 PRECEDING AND CURRENT ROW
            ) AS bench_ret_5d,
            SUM(db.pct_change) OVER (
                PARTITION BY db.industry_code
                ORDER BY db.trade_date
                ROWS BETWEEN 19 PRECEDING AND CURRENT ROW
            ) AS ret_20d,
            SUM(db.bench_pct) OVER (
                ORDER BY db.trade_date
                ROWS BETWEEN 19 PRECEDING AND CURRENT ROW
            ) AS bench_ret_20d,
            AVG(db.close) OVER (
                PARTITION BY db.industry_code
                ORDER BY db.trade_date
                ROWS BETWEEN 4 PRECEDING AND CURRENT ROW
            ) AS ma5,
            AVG(db.close) OVER (
                PARTITION BY db.industry_code
                ORDER BY db.trade_date
                ROWS BETWEEN 9 PRECEDING AND CURRENT ROW
            ) AS ma10,
            AVG(db.close) OVER (
                PARTITION BY db.industry_code
                ORDER BY db.trade_date
                ROWS BETWEEN 19 PRECEDING AND CURRENT ROW
            ) AS ma20,
            MAX(db.close) OVER (
                PARTITION BY db.industry_code
                ORDER BY db.trade_date
                ROWS BETWEEN 59 PRECEDING AND CURRENT ROW
            ) AS high_60d
        FROM daily_base db
    ),
    enriched AS (
        SELECT
            c.*,
            ROUND(c.ret_5d - c.bench_ret_5d, 6) AS rs_5d,
            ROUND(c.ret_20d - c.bench_ret_20d, 6) AS rs_20d,
            CASE
                WHEN c.ma5 IS NOT NULL AND c.ma10 IS NOT NULL AND c.ma20 IS NOT NULL
                 AND c.ma5 > c.ma10 AND c.ma10 > c.ma20
                THEN 1 ELSE 0
            END AS ma_bullish,
            CASE
                WHEN c.high_60d IS NOT NULL AND c.high_60d <> 0
                 AND c.close >= c.high_60d * 0.999
                THEN 1 ELSE 0
            END AS is_new_high_60d,
            CASE
                WHEN c.high_60d IS NOT NULL AND c.high_60d <> 0
                THEN ROUND((c.close - c.high_60d) / c.high_60d * 100, 6)
                ELSE NULL
            END AS drawdown_pct
        FROM calc c
    ),
    off_high AS (
        SELECT
            e.*,
            SUM(e.is_new_high_60d) OVER (
                PARTITION BY e.industry_code
                ORDER BY e.trade_date
                ROWS UNBOUNDED PRECEDING
            ) AS peak_grp
        FROM enriched e
    ),
    metrics AS (
        SELECT
            o.*,
            CASE
                WHEN o.is_new_high_60d = 1 THEN 0
                ELSE ROW_NUMBER() OVER (
                    PARTITION BY o.industry_code, o.peak_grp
                    ORDER BY o.trade_date
                ) - 1
            END AS days_off_high
        FROM off_high o
    ),
    ranked AS (
        SELECT
            m.*,
            CASE
                WHEN m.drawdown_pct IS NULL OR m.drawdown_pct > -3 THEN 0
                ELSE m.days_off_high
            END AS recovery_days,
            ROW_NUMBER() OVER (
                PARTITION BY m.trade_date, m.content_type
                ORDER BY m.rs_5d DESC
            ) AS rs_rank
        FROM metrics m
        WHERE m.trade_date = '${v_date}'
    )
    SELECT
        r.trade_date,
        r.content_type,
        r.industry_code,
        r.industry_name,
        r.close,
        r.pct_change,
        r.rs_5d,
        r.rs_20d,
        ROUND(r.ma5, 6) AS ma5,
        ROUND(r.ma10, 6) AS ma10,
        ROUND(r.ma20, 6) AS ma20,
        r.ma_bullish,
        ROUND(r.high_60d, 6) AS high_60d,
        r.is_new_high_60d,
        r.drawdown_pct,
        r.recovery_days,
        r.rs_rank
    FROM ranked r;
  "

  echo "OK ${v_date} ths_daily_rows=${ods_cnt} bench_rows=${bench_cnt}"
  ${data_mysql} -e "
    SELECT trade_date, content_type, industry_code, industry_name,
           rs_5d, rs_20d, ma_bullish, is_new_high_60d, drawdown_pct, rs_rank
    FROM dwm_ths_industry_trend_strength_di
    WHERE trade_date = '${v_date}'
    ORDER BY rs_5d DESC
    LIMIT 5;
  "
}

fail_cnt=0
for cur_date in $(get_continuous_date "${n_date_s}" "${n_date_e}"); do
  if ! load_ths_industry_trend_strength "${cur_date}"; then
    fail_cnt=$((fail_cnt + 1))
  fi
done

if [[ "${fail_cnt}" -gt 0 ]]; then
  echo "DONE with ${fail_cnt} skipped day(s)"
  exit 1
fi
echo "DONE all days"
