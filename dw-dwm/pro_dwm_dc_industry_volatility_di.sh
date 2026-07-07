#!/bin/bash
# =============================================================================
# target_table: dwm_dc_industry_volatility_di
# source_table: ods_dc_daily_di, ods_dc_index_di
# 东财板块年化波动率：行业/概念/地域 20日、60日年化波动率
#
# 口径：
#   log_ret        = LN(close / lag(close))
#   annual_vol_20d = STDDEV_SAMP(log_ret, 最近20个交易日) * SQRT(252) * 100
#   annual_vol_60d = STDDEV_SAMP(log_ret, 最近60个交易日) * SQRT(252) * 100
#
# 用法（必须用 bash，不要用 sh）:
#   bash dw-dwm/pro_dwm_dc_industry_volatility_di.sh
#   bash dw-dwm/pro_dwm_dc_industry_volatility_di.sh 20260707
#   bash dw-dwm/pro_dwm_dc_industry_volatility_di.sh 20250701 20260707
#   或: run_dwm_dc_industry_volatility 20260707
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
exec 1>>"${LOG_PATH}/pro_dwm_dc_industry_volatility_di_${n_date}.log"
exec 2>>"${LOG_PATH}/pro_dwm_dc_industry_volatility_di_${n_date}.log"

echo "======== $(date '+%F %T') pro_dwm_dc_industry_volatility_di ${n_date_s} ~ ${n_date_e} ========"

${data_mysql} -e "
CREATE TABLE IF NOT EXISTS dwm_dc_industry_volatility_di (
    id              BIGINT PRIMARY KEY AUTO_INCREMENT,
    trade_date      DATE           NOT NULL COMMENT '交易日期',
    content_type    VARCHAR(32)    NULL COMMENT '板块类型(行业/概念/地域)',
    industry_code   VARCHAR(32)    NOT NULL COMMENT '东财板块代码',
    industry_name   VARCHAR(128)   NULL COMMENT '东财板块名称',
    close           DECIMAL(20, 6) NULL COMMENT '收盘点位',
    pct_change      DECIMAL(20, 6) NULL COMMENT '涨跌幅(%)',
    annual_vol_20d  DECIMAL(20, 6) NULL COMMENT '20日年化波动率(%)',
    annual_vol_60d  DECIMAL(20, 6) NULL COMMENT '60日年化波动率(%)',
    created_at      DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_dwm_dc_industry_volatility (trade_date, industry_code),
    KEY idx_dwm_dc_industry_volatility_td (trade_date, content_type, annual_vol_20d, annual_vol_60d)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='东财板块年化波动率(DWM)';
"

load_dc_industry_volatility() {
  local cur_date="$1"
  local v_date v_date_200 ods_cnt
  v_date="$(format_date "${cur_date}")"
  v_date_200="$(date -d "${cur_date} 200 day ago" +%Y-%m-%d)"

  ods_cnt="$(${data_mysql} -N -e "
    SELECT COUNT(*)
    FROM ods_dc_daily_di d
    JOIN ods_dc_index_di i
      ON i.trade_date = d.trade_date AND i.ts_code = d.ts_code
    WHERE d.trade_date = '${v_date}'
      AND i.idx_type IN ('行业板块', '概念板块', '地域板块');
  ")"
  if [[ -z "${ods_cnt}" || "${ods_cnt}" -eq 0 ]]; then
    echo "WARN: skip ${v_date}, ods_dc_daily_di 无板块数据"
    return 1
  fi

  ${data_mysql} -e "
    DELETE FROM dwm_dc_industry_volatility_di WHERE trade_date = '${v_date}';

    INSERT INTO dwm_dc_industry_volatility_di (
        trade_date, content_type, industry_code, industry_name, close, pct_change, annual_vol_20d, annual_vol_60d
    )
    WITH hist AS (
        SELECT
            d.trade_date,
            d.ts_code AS industry_code,
            COALESCE(i.dc_name, d.ts_code) AS industry_name,
            CASE i.idx_type
                WHEN '行业板块' THEN '行业'
                WHEN '概念板块' THEN '概念'
                WHEN '地域板块' THEN '地域'
                ELSE i.idx_type
            END AS content_type,
            d.close,
            d.pct_change,
            CASE
                WHEN LAG(d.close) OVER (PARTITION BY d.ts_code ORDER BY d.trade_date) IS NOT NULL
                 AND LAG(d.close) OVER (PARTITION BY d.ts_code ORDER BY d.trade_date) > 0
                 AND d.close IS NOT NULL AND d.close > 0
                THEN LN(d.close / LAG(d.close) OVER (PARTITION BY d.ts_code ORDER BY d.trade_date))
                ELSE NULL
            END AS log_ret
        FROM ods_dc_daily_di d
        JOIN ods_dc_index_di i
          ON i.trade_date = d.trade_date AND i.ts_code = d.ts_code
        WHERE d.trade_date >= '${v_date_200}'
          AND d.trade_date <= '${v_date}'
          AND i.idx_type IN ('行业板块', '概念板块', '地域板块')
    ),
    calc AS (
        SELECT
            h.*,
            CASE
                WHEN COUNT(h.log_ret) OVER (
                    PARTITION BY h.industry_code
                    ORDER BY h.trade_date
                    ROWS BETWEEN 19 PRECEDING AND CURRENT ROW
                ) >= 20
                THEN ROUND(
                    STDDEV_SAMP(h.log_ret) OVER (
                        PARTITION BY h.industry_code
                        ORDER BY h.trade_date
                        ROWS BETWEEN 19 PRECEDING AND CURRENT ROW
                    ) * SQRT(252) * 100,
                    6
                )
                ELSE NULL
            END AS annual_vol_20d,
            CASE
                WHEN COUNT(h.log_ret) OVER (
                    PARTITION BY h.industry_code
                    ORDER BY h.trade_date
                    ROWS BETWEEN 59 PRECEDING AND CURRENT ROW
                ) >= 60
                THEN ROUND(
                    STDDEV_SAMP(h.log_ret) OVER (
                        PARTITION BY h.industry_code
                        ORDER BY h.trade_date
                        ROWS BETWEEN 59 PRECEDING AND CURRENT ROW
                    ) * SQRT(252) * 100,
                    6
                )
                ELSE NULL
            END AS annual_vol_60d
        FROM hist h
    )
    SELECT
        trade_date, content_type, industry_code, industry_name, close, pct_change, annual_vol_20d, annual_vol_60d
    FROM calc
    WHERE trade_date = '${v_date}';
  "

  echo "OK ${v_date} board_cnt=${ods_cnt}"
}

run_dwm_by_trading_day "${n_date_s}" "${n_date_e}" load_dc_industry_volatility || exit $?
