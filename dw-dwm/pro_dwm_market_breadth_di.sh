#!/bin/bash
# =============================================================================
# target_table: dwm_market_breadth_di
# source_table: ods_stock_detail_di, ods_limit_list_di
# 全市场广度：涨/跌/平家数、涨跌停家数、上涨占比
#
# 用法（必须用 bash，不要用 sh）:
#   bash dw-dwm/pro_dwm_market_breadth_di.sh              # 默认昨日
#   bash dw-dwm/pro_dwm_market_breadth_di.sh 20260527
#   bash dw-dwm/pro_dwm_market_breadth_di.sh 20260501 20260527
#   或: run_dwm_market_breadth 20260527  （先 source dw-utils/func.sh）
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
exec 1>>"${LOG_PATH}/pro_dwm_market_breadth_di_${n_date}.log"
exec 2>>"${LOG_PATH}/pro_dwm_market_breadth_di_${n_date}.log"

echo "======== $(date '+%F %T') pro_dwm_market_breadth_di ${n_date_s} ~ ${n_date_e} ========"

${data_mysql} -e "
CREATE TABLE IF NOT EXISTS dwm_market_breadth_di (
    id              BIGINT PRIMARY KEY AUTO_INCREMENT,
    trade_date      DATE           NOT NULL COMMENT '交易日期',
    advance_cnt     INT            NOT NULL DEFAULT 0 COMMENT '上涨家数(pct_chg>0)',
    decline_cnt     INT            NOT NULL DEFAULT 0 COMMENT '下跌家数(pct_chg<0)',
    flat_cnt        INT            NOT NULL DEFAULT 0 COMMENT '平盘家数(pct_chg=0或NULL)',
    limit_up_cnt    INT            NOT NULL DEFAULT 0 COMMENT '涨停家数(limit=U)',
    limit_down_cnt  INT            NOT NULL DEFAULT 0 COMMENT '跌停家数(limit=D)',
    advance_ratio   DECIMAL(10, 6) NULL COMMENT '上涨占比=advance_cnt/total_cnt',
    total_cnt       INT            NOT NULL DEFAULT 0 COMMENT '参与统计家数(沪深A股)',
    created_at      DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_dwm_market_breadth (trade_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='全市场广度(DWM,来源ods_stock_detail_di+ods_limit_list_di)';
"

load_market_breadth() {
  local n_date="$1"
  local v_date
  v_date="$(format_date "${n_date}")"

  local ods_cnt
  ods_cnt="$(${data_mysql} -N -e "
    SELECT COUNT(*)
    FROM ods_stock_detail_di
    WHERE trade_date = '${v_date}'
      AND ts_code REGEXP '\\.(SH|SZ)$';
  ")"
  if [[ -z "${ods_cnt}" || "${ods_cnt}" -eq 0 ]]; then
    echo "WARN: skip ${v_date}, ods_stock_detail_di has no SH/SZ rows"
    return 1
  fi

  ${data_mysql} -e "
    DELETE FROM dwm_market_breadth_di WHERE trade_date = '${v_date}';

    INSERT INTO dwm_market_breadth_di (
        trade_date,
        advance_cnt,
        decline_cnt,
        flat_cnt,
        limit_up_cnt,
        limit_down_cnt,
        advance_ratio,
        total_cnt
    )
    SELECT
        '${v_date}' AS trade_date,
        s.advance_cnt,
        s.decline_cnt,
        s.flat_cnt,
        COALESCE(l.limit_up_cnt, 0) AS limit_up_cnt,
        COALESCE(l.limit_down_cnt, 0) AS limit_down_cnt,
        CASE
            WHEN s.total_cnt > 0 THEN ROUND(s.advance_cnt / s.total_cnt, 6)
            ELSE NULL
        END AS advance_ratio,
        s.total_cnt
    FROM (
        -- 口径说明#9：
        --   1) 仅统计以 .SH/.SZ 结尾的沪深A股，不含北交所(.BJ)，与全站保守口径保持一致；
        --   2) pct_chg IS NULL 暂计入 flat_cnt(平盘)——受既有表结构限制无独立 NULL 列，故沿用并注释；
        --   3) 新增按 ods_stock_basic_di.list_status 过滤退市/暂停(仅排除已知 D/P，未匹配到基础表则保留)，
        --      降低退市股干扰；ST/新股首日因无逐日状态列，未做剔除。
        SELECT
            SUM(CASE WHEN d.pct_chg > 0 THEN 1 ELSE 0 END) AS advance_cnt,
            SUM(CASE WHEN d.pct_chg < 0 THEN 1 ELSE 0 END) AS decline_cnt,
            SUM(CASE WHEN d.pct_chg = 0 OR d.pct_chg IS NULL THEN 1 ELSE 0 END) AS flat_cnt,
            COUNT(*) AS total_cnt
        FROM ods_stock_detail_di d
        LEFT JOIN ods_stock_basic_di b ON b.ts_code = d.ts_code
        WHERE d.trade_date = '${v_date}'
          AND d.ts_code REGEXP '\\.(SH|SZ)$'
          AND (b.list_status = 'L' OR b.list_status IS NULL)
    ) s
    CROSS JOIN (
        -- 口径说明#9：涨跌停家数取自 ods_limit_list_di 全量(未按 SH/SZ 过滤，可能含 .BJ)，
        --   与上方沪深广度口径略有差异，保留现状不改。
        SELECT
            COUNT(DISTINCT CASE WHEN \`limit\` = 'U' THEN ts_code END) AS limit_up_cnt,
            COUNT(DISTINCT CASE WHEN \`limit\` = 'D' THEN ts_code END) AS limit_down_cnt
        FROM ods_limit_list_di
        WHERE trade_date = '${v_date}'
    ) l;
  "

  echo "OK ${v_date} ods_rows=${ods_cnt}"
  ${data_mysql} -e "
    SELECT trade_date, advance_cnt, decline_cnt, flat_cnt,
           limit_up_cnt, limit_down_cnt, advance_ratio, total_cnt
    FROM dwm_market_breadth_di
    WHERE trade_date = '${v_date}';
  "
}

run_dwm_by_trading_day "${n_date_s}" "${n_date_e}" load_market_breadth || exit $?
