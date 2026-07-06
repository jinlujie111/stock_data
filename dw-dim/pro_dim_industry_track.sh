#!/bin/bash
# =============================================================================
# target_table: dim_industry_track, dim_industry_track_stock
# source_table: dwm_dc_industry_market_heat_di, ods_dc_member_di
#
# 需求4 AI核心池 DIM 刷新：
#   1) dim_industry_track  — 东财热度最高的 TopN 板块（概念+行业）
#   2) dim_industry_track_stock — 上述板块在 ods_dc_member_di 的当日成分股
#
# 热度口径（与 dwm_dc_industry_market_heat 对齐）：
#   主排序 amount_ratio DESC（板块成交额占全A）
#   次排序 dc_hot_rank ASC（成分股东财 App 人气榜最佳排名，越小越热）
#   再次 pct_change DESC
#
# 用法（必须用 bash，不要用 sh）:
#   bash dw-dim/pro_dim_industry_track.sh
#   bash dw-dim/pro_dim_industry_track.sh 20260616
#   或: run_dim_industry_track  （先 source dw-utils/func.sh）
#
# 环境变量:
#   AI_CORE_TRACK_TOP_N=50          入选赛道数量（默认 50）
#   AI_CORE_TRACK_MIN_CONST=3       最少成分股数（默认 3）
#   AI_CORE_TRACK_CONTENT_TYPES=概念,行业   板块类型（逗号分隔）
#
# 前置依赖（同日）:
#   run_data_sync → dc_daily, dc_member, dc_hot, daily
#   run_dwm_dc_industry_market_heat
# =============================================================================
if [ -z "${BASH_VERSION:-}" ]; then
  exec bash "$0" "$@"
fi

set -euo pipefail

SCRIPT_PATH="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DW_ROOT="$(cd "${SCRIPT_PATH}/.." && pwd)"
# shellcheck source=/dev/null
source "${DW_ROOT}/dw-utils/func.sh"

AI_CORE_TRACK_TOP_N="${AI_CORE_TRACK_TOP_N:-50}"
AI_CORE_TRACK_MIN_CONST="${AI_CORE_TRACK_MIN_CONST:-3}"
AI_CORE_TRACK_CONTENT_TYPES="${AI_CORE_TRACK_CONTENT_TYPES:-概念,行业}"

n_date="$(get_date "${1:-}")"
v_date="$(format_date "${n_date}")"

LOG_PATH="${STOCK_LOG_DIR:-/root/log/stock_log}/${n_date}"
mkdir -p "${LOG_PATH}"
exec 1>>"${LOG_PATH}/pro_dim_industry_track_${n_date}.log"
exec 2>>"${LOG_PATH}/pro_dim_industry_track_${n_date}.log"

echo "======== $(date '+%F %T') pro_dim_industry_track as_of=${v_date} top_n=${AI_CORE_TRACK_TOP_N} ========"

# 解析 content_type IN 列表
ct_in=""
IFS=',' read -r -a _ct_arr <<< "${AI_CORE_TRACK_CONTENT_TYPES}"
for i in "${!_ct_arr[@]}"; do
  ct="$(echo "${_ct_arr[$i]}" | xargs)"
  [[ -z "${ct}" ]] && continue
  if [[ -n "${ct_in}" ]]; then
    ct_in="${ct_in},'${ct}'"
  else
    ct_in="'${ct}'"
  fi
done
if [[ -z "${ct_in}" ]]; then
  ct_in="'概念','行业'"
fi

${data_mysql} -e "
CREATE TABLE IF NOT EXISTS dim_industry_track (
    industry_id       VARCHAR(32)  NOT NULL COMMENT '赛道ID(=东财板块代码)',
    industry_name     VARCHAR(128) NOT NULL COMMENT '赛道名称',
    as_of_date        DATE         NOT NULL COMMENT '快照交易日',
    content_type      VARCHAR(16)  NULL COMMENT '概念/行业/地域',
    dc_board_code     VARCHAR(32)  NOT NULL COMMENT '东财板块代码 BKxxxx.DC',
    heat_rank         INT          NULL COMMENT '同类型内成交额占比排名(东财热度)',
    heat_sort         INT          NOT NULL COMMENT '入选赛道总排序1..N',
    amount_ratio      DECIMAL(20, 8) NULL COMMENT '板块成交额占全A比',
    dc_hot_rank       INT          NULL COMMENT '成分股东财人气榜最佳排名',
    dc_hot_rank_soar  INT          NULL COMMENT '成分股东财飙升榜最佳排名',
    pct_change        DECIMAL(20, 6) NULL COMMENT '板块涨跌幅(%)',
    status            TINYINT      NOT NULL DEFAULT 1 COMMENT '1启用 0历史批次',
    source            VARCHAR(32)  NOT NULL DEFAULT 'dc_market_heat' COMMENT 'dc_market_heat|manual',
    remark            VARCHAR(512) NULL,
    created_at        DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at        DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (industry_id, as_of_date),
    KEY idx_track_asof_sort (as_of_date, status, heat_sort),
    KEY idx_track_board (dc_board_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='AI核心池-东财热度赛道维表';

CREATE TABLE IF NOT EXISTS dim_industry_track_stock (
    id            BIGINT PRIMARY KEY AUTO_INCREMENT,
    industry_id   VARCHAR(32)  NOT NULL COMMENT '关联 dim_industry_track.industry_id',
    as_of_date    DATE         NOT NULL COMMENT '快照交易日',
    ts_code       VARCHAR(16)  NOT NULL COMMENT '成分股TS代码',
    stock_name    VARCHAR(64)  NULL COMMENT '成分股简称',
    source        VARCHAR(32)  NOT NULL DEFAULT 'dc_member' COMMENT 'dc_member|manual',
    is_active     TINYINT      NOT NULL DEFAULT 1 COMMENT '1有效 0历史批次',
    created_at    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_track_stock (industry_id, as_of_date, ts_code),
    KEY idx_track_stock_asof (as_of_date, industry_id, is_active)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='AI核心池-东财板块成分候选股';
"

heat_cnt="$(${data_mysql} -N -e "
  SELECT COUNT(*)
  FROM dwm_dc_industry_market_heat_di
  WHERE trade_date = '${v_date}';
")"
mem_cnt="$(${data_mysql} -N -e "
  SELECT COUNT(*)
  FROM ods_dc_member_di
  WHERE trade_date = '${v_date}';
")"

if [[ -z "${heat_cnt}" || "${heat_cnt}" -eq 0 ]]; then
  echo "ERROR: dwm_dc_industry_market_heat_di 无 ${v_date} 数据，请先 run_dwm_dc_industry_market_heat ${n_date}" >&2
  exit 1
fi
if [[ -z "${mem_cnt}" || "${mem_cnt}" -eq 0 ]]; then
  echo "ERROR: ods_dc_member_di 无 ${v_date} 数据，请先 run_data_sync ${n_date} --source-table dc_member" >&2
  exit 1
fi

${data_mysql} -e "
-- 历史批次置失效（保留 manual 来源人工赛道）
UPDATE dim_industry_track
   SET status = 0, updated_at = CURRENT_TIMESTAMP
 WHERE source = 'dc_market_heat'
   AND as_of_date < '${v_date}';

UPDATE dim_industry_track_stock
   SET is_active = 0, updated_at = CURRENT_TIMESTAMP
 WHERE source = 'dc_member'
   AND as_of_date < '${v_date}';

DELETE FROM dim_industry_track_stock
 WHERE source = 'dc_member' AND as_of_date = '${v_date}';

DELETE FROM dim_industry_track
 WHERE source = 'dc_market_heat' AND as_of_date = '${v_date}';

INSERT INTO dim_industry_track (
    industry_id,
    industry_name,
    as_of_date,
    content_type,
    dc_board_code,
    heat_rank,
    heat_sort,
    amount_ratio,
    dc_hot_rank,
    dc_hot_rank_soar,
    pct_change,
    status,
    source,
    remark
)
WITH ranked AS (
    SELECT
        h.industry_code AS industry_id,
        h.industry_name,
        h.trade_date AS as_of_date,
        h.content_type,
        h.industry_code AS dc_board_code,
        h.heat_rank,
        ROW_NUMBER() OVER (
            ORDER BY
                IFNULL(h.amount_ratio, 0) DESC,
                CASE WHEN h.dc_hot_rank IS NULL THEN 9999 ELSE h.dc_hot_rank END ASC,
                IFNULL(h.pct_change, -999) DESC
        ) AS heat_sort,
        h.amount_ratio,
        h.dc_hot_rank,
        h.dc_hot_rank_soar,
        h.pct_change
    FROM dwm_dc_industry_market_heat_di h
    WHERE h.trade_date = '${v_date}'
      AND h.content_type IN (${ct_in})
      AND IFNULL(h.constituent_cnt, 0) >= ${AI_CORE_TRACK_MIN_CONST}
      AND h.industry_code IS NOT NULL
      AND TRIM(h.industry_code) <> ''
)
SELECT
    industry_id,
    industry_name,
    as_of_date,
    content_type,
    dc_board_code,
    heat_rank,
    heat_sort,
    amount_ratio,
    dc_hot_rank,
    dc_hot_rank_soar,
    pct_change,
    1 AS status,
    'dc_market_heat' AS source,
    CONCAT('东财热度Top', heat_sort, '/', ${AI_CORE_TRACK_TOP_N}) AS remark
FROM ranked
WHERE heat_sort <= ${AI_CORE_TRACK_TOP_N};

INSERT INTO dim_industry_track_stock (
    industry_id,
    as_of_date,
    ts_code,
    stock_name,
    source,
    is_active
)
SELECT
    t.industry_id,
    t.as_of_date,
    CASE
        WHEN INSTR(m.con_code, '.') > 0 THEN m.con_code
        WHEN LEFT(m.con_code, 1) IN ('6', '5', '9') THEN CONCAT(m.con_code, '.SH')
        WHEN LEFT(m.con_code, 1) IN ('8', '4') THEN CONCAT(m.con_code, '.BJ')
        ELSE CONCAT(m.con_code, '.SZ')
    END AS ts_code,
    m.name AS stock_name,
    'dc_member' AS source,
    1 AS is_active
FROM dim_industry_track t
INNER JOIN ods_dc_member_di m
    ON m.trade_date = t.as_of_date
   AND m.ts_code = t.dc_board_code
WHERE t.as_of_date = '${v_date}'
  AND t.source = 'dc_market_heat'
  AND t.status = 1;
"

track_cnt="$(${data_mysql} -N -e "
  SELECT COUNT(*) FROM dim_industry_track
  WHERE as_of_date = '${v_date}' AND source = 'dc_market_heat' AND status = 1;
")"
stock_cnt="$(${data_mysql} -N -e "
  SELECT COUNT(*) FROM dim_industry_track_stock
  WHERE as_of_date = '${v_date}' AND source = 'dc_member' AND is_active = 1;
")"

if [[ -z "${track_cnt}" || "${track_cnt}" -eq 0 ]]; then
  echo "ERROR: 未写入任何赛道，请检查 dwm 数据或 AI_CORE_TRACK_CONTENT_TYPES" >&2
  exit 1
fi

echo "--- 赛道 Top10 ---"
${data_mysql} -e "
SELECT heat_sort, content_type, industry_id, industry_name,
       ROUND(amount_ratio * 100, 4) AS amount_pct,
       dc_hot_rank, heat_rank
FROM dim_industry_track
WHERE as_of_date = '${v_date}' AND status = 1
ORDER BY heat_sort
LIMIT 10;
"

echo "--- 统计 ---"
${data_mysql} -e "
SELECT
    t.content_type,
    COUNT(DISTINCT t.industry_id) AS track_cnt,
    COUNT(s.ts_code) AS stock_cnt
FROM dim_industry_track t
LEFT JOIN dim_industry_track_stock s
    ON t.industry_id = s.industry_id
   AND t.as_of_date = s.as_of_date
   AND s.is_active = 1
WHERE t.as_of_date = '${v_date}'
  AND t.status = 1
GROUP BY t.content_type;
"

echo "DONE dim_industry_track tracks=${track_cnt} stocks=${stock_cnt}"
