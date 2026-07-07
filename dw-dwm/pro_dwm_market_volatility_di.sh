#!/bin/bash
# =============================================================================
# target_table: dwm_market_volatility_di
# source_table: ods_index_daily_di
# 大盘指数年化波动率：上证综指/沪深300 的 20日、60日年化波动率
#
# 口径：
#   log_ret        = LN(close / lag(close))
#   annual_vol_20d = STDDEV_SAMP(log_ret, 最近20个交易日) * SQRT(252) * 100
#   annual_vol_60d = STDDEV_SAMP(log_ret, 最近60个交易日) * SQRT(252) * 100
#
# 用法（必须用 bash，不要用 sh）:
#   bash dw-dwm/pro_dwm_market_volatility_di.sh
#   bash dw-dwm/pro_dwm_market_volatility_di.sh 20260707
#   bash dw-dwm/pro_dwm_market_volatility_di.sh 20250701 20260707
#   或: run_dwm_market_volatility 20260707
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
exec 1>>"${LOG_PATH}/pro_dwm_market_volatility_di_${n_date}.log"
exec 2>>"${LOG_PATH}/pro_dwm_market_volatility_di_${n_date}.log"

echo "======== $(date '+%F %T') pro_dwm_market_volatility_di ${n_date_s} ~ ${n_date_e} ========"

${data_mysql} -e "
CREATE TABLE IF NOT EXISTS dwm_market_volatility_di (
    id              BIGINT PRIMARY KEY AUTO_INCREMENT,
    trade_date      DATE           NOT NULL COMMENT '交易日期',
    index_code      VARCHAR(16)    NOT NULL COMMENT '指数代码',
    index_name      VARCHAR(64)    NOT NULL COMMENT '指数名称',
    close           DECIMAL(20, 6) NULL COMMENT '收盘点位',
    pct_chg         DECIMAL(20, 6) NULL COMMENT '涨跌幅(%)',
    annual_vol_20d  DECIMAL(20, 6) NULL COMMENT '20日年化波动率(%)',
    annual_vol_60d  DECIMAL(20, 6) NULL COMMENT '60日年化波动率(%)',
    created_at      DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_dwm_market_volatility (trade_date, index_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='大盘指数年化波动率(DWM)';
"

load_market_volatility() {
  local cur_date="$1"
  local v_date v_date_200 ods_cnt
  v_date="$(format_date "${cur_date}")"
  v_date_200="$(date -d "${cur_date} 200 day ago" +%Y-%m-%d)"

  ods_cnt="$(${data_mysql} -N -e "
    SELECT COUNT(*)
    FROM ods_index_daily_di
    WHERE trade_date = '${v_date}'
      AND ts_code IN ('000001.SH', '000300.SH');
  ")"
  if [[ -z "${ods_cnt}" || "${ods_cnt}" -eq 0 ]]; then
    echo "WARN: skip ${v_date}, ods_index_daily_di 无目标指数数据"
    return 1
  fi

  ${data_mysql} -e "
    DELETE FROM dwm_market_volatility_di
    WHERE trade_date = '${v_date}'
      AND index_code IN ('000001.SH', '000300.SH');

    INSERT INTO dwm_market_volatility_di (
        trade_date, index_code, index_name, close, pct_chg, annual_vol_20d, annual_vol_60d
    )
    WITH hist AS (
        SELECT
            d.trade_date,
            d.ts_code AS index_code,
            CASE d.ts_code
                WHEN '000001.SH' THEN '上证综指'
                WHEN '000300.SH' THEN '沪深300'
                ELSE d.ts_code
            END AS index_name,
            d.close,
            d.pct_chg,
            CASE
                WHEN LAG(d.close) OVER (PARTITION BY d.ts_code ORDER BY d.trade_date) IS NOT NULL
                 AND LAG(d.close) OVER (PARTITION BY d.ts_code ORDER BY d.trade_date) > 0
                 AND d.close IS NOT NULL AND d.close > 0
                THEN LN(d.close / LAG(d.close) OVER (PARTITION BY d.ts_code ORDER BY d.trade_date))
                ELSE NULL
            END AS log_ret
        FROM ods_index_daily_di d
        WHERE d.ts_code IN ('000001.SH', '000300.SH')
          AND d.trade_date >= '${v_date_200}'
          AND d.trade_date <= '${v_date}'
    ),
    calc AS (
        SELECT
            h.*,
            CASE
                WHEN COUNT(h.log_ret) OVER (
                    PARTITION BY h.index_code
                    ORDER BY h.trade_date
                    ROWS BETWEEN 19 PRECEDING AND CURRENT ROW
                ) >= 20
                THEN ROUND(
                    STDDEV_SAMP(h.log_ret) OVER (
                        PARTITION BY h.index_code
                        ORDER BY h.trade_date
                        ROWS BETWEEN 19 PRECEDING AND CURRENT ROW
                    ) * SQRT(252) * 100,
                    6
                )
                ELSE NULL
            END AS annual_vol_20d,
            CASE
                WHEN COUNT(h.log_ret) OVER (
                    PARTITION BY h.index_code
                    ORDER BY h.trade_date
                    ROWS BETWEEN 59 PRECEDING AND CURRENT ROW
                ) >= 60
                THEN ROUND(
                    STDDEV_SAMP(h.log_ret) OVER (
                        PARTITION BY h.index_code
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
        trade_date, index_code, index_name, close, pct_chg, annual_vol_20d, annual_vol_60d
    FROM calc
    WHERE trade_date = '${v_date}';
  "

  echo "OK ${v_date} index_cnt=${ods_cnt}"
}

run_dwm_by_trading_day "${n_date_s}" "${n_date_e}" load_market_volatility || exit $?
