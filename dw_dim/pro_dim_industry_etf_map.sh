#!/bin/bash
# =============================================================================
# target_table: dim_industry_etf_map
# source_table: ods_etf_basic_di, ods_industry_classify
# 行业 ↔ ETF 映射维表：自动段=ETF 跟踪指数对齐申万行业指数；manual 段保留不删
#
# 用法（必须用 bash，不要用 sh）:
#   bash dw_dim/pro_dim_industry_etf_map.sh              # 默认昨日为生效日
#   bash dw_dim/pro_dim_industry_etf_map.sh 20260527
#   或: run_dim_industry_etf_map  （先 source dw-utils/func.sh）
#
# 环境变量:
#   SW_SRC=SW2021   申万分类版本（与 sw_daily / 主线口径一致）
# =============================================================================
if [ -z "${BASH_VERSION:-}" ]; then
  exec bash "$0" "$@"
fi

set -euo pipefail

SCRIPT_PATH="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DW_ROOT="$(cd "${SCRIPT_PATH}/.." && pwd)"
# shellcheck source=/dev/null
source "${DW_ROOT}/dw-utils/func.sh"

SW_SRC="${SW_SRC:-SW2021}"

n_date="$(get_date "${1:-}")"
v_date="$(format_date "${n_date}")"

LOG_PATH="/root/log/stock_log/${n_date}"
mkdir -p "${LOG_PATH}"
exec 1>>"${LOG_PATH}/pro_dim_industry_etf_map_${n_date}.log"
exec 2>>"${LOG_PATH}/pro_dim_industry_etf_map_${n_date}.log"

echo "======== $(date '+%F %T') pro_dim_industry_etf_map effective=${v_date} sw_src=${SW_SRC} ========"

${data_mysql} -e "
CREATE TABLE IF NOT EXISTS dim_industry_etf_map (
    id              BIGINT PRIMARY KEY AUTO_INCREMENT,
    industry_code   VARCHAR(32)    NOT NULL COMMENT '申万行业代码',
    industry_name   VARCHAR(128)   NULL COMMENT '申万行业名称',
    industry_level  VARCHAR(8)     NULL COMMENT '行业层级 L1/L2/L3',
    index_code      VARCHAR(32)    NULL COMMENT 'ETF跟踪指数代码',
    index_name      VARCHAR(128)   NULL COMMENT 'ETF跟踪指数名称',
    etf_code        VARCHAR(16)    NOT NULL COMMENT 'ETF代码 ts_code',
    etf_name        VARCHAR(128)   NULL COMMENT 'ETF简称',
    exchange        VARCHAR(8)     NULL COMMENT '交易所 SH/SZ',
    weight          DECIMAL(5, 4)  NOT NULL DEFAULT 1.0000 COMMENT '映射权重',
    map_type        VARCHAR(16)    NOT NULL DEFAULT 'index_match' COMMENT 'index_match=自动对齐申万指数 manual=人工维护',
    sw_src          VARCHAR(16)    NULL COMMENT '申万分类版本 SW2014/SW2021',
    effective_date  DATE           NOT NULL COMMENT '映射生效日(本批次)',
    remark          VARCHAR(256)   NULL COMMENT '备注',
    is_active       TINYINT        NOT NULL DEFAULT 1 COMMENT '1有效 0停用',
    created_at      DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_dim_industry_etf (etf_code, industry_code, map_type),
    KEY idx_dim_industry_etf_industry (industry_code, is_active),
    KEY idx_dim_industry_etf_index (index_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='行业-ETF映射维表';
"

etf_cnt="$(${data_mysql} -N -e "SELECT COUNT(*) FROM ods_etf_basic_di WHERE list_status = 'L';")"
classify_cnt="$(${data_mysql} -N -e "
  SELECT COUNT(*) FROM ods_industry_classify WHERE src = '${SW_SRC}';
")"

if [[ -z "${etf_cnt}" || "${etf_cnt}" -eq 0 ]]; then
  echo "ERROR: ods_etf_basic_di is empty, run: run_data_sync --source-table etf_basic" >&2
  exit 1
fi
if [[ -z "${classify_cnt}" || "${classify_cnt}" -eq 0 ]]; then
  echo "ERROR: ods_industry_classify is empty for src=${SW_SRC}, run: run_data_sync --source-table index_classify" >&2
  exit 1
fi

${data_mysql} -e "
DELETE FROM dim_industry_etf_map WHERE map_type = 'index_match';

INSERT INTO dim_industry_etf_map (
    industry_code,
    industry_name,
    industry_level,
    index_code,
    index_name,
    etf_code,
    etf_name,
    exchange,
    weight,
    map_type,
    sw_src,
    effective_date,
    remark,
    is_active
)
SELECT
    c.industry_code,
    c.industry_name,
    c.level AS industry_level,
    e.index_code,
    e.index_name,
    e.ts_code AS etf_code,
    COALESCE(e.csname, e.extname, e.cname) AS etf_name,
    e.exchange,
    1.0000 AS weight,
    'index_match' AS map_type,
    c.src AS sw_src,
    '${v_date}' AS effective_date,
    CONCAT('ETF跟踪申万指数 ', e.index_code) AS remark,
    1 AS is_active
FROM ods_etf_basic_di e
INNER JOIN ods_industry_classify c
    ON e.index_code = c.index_code
   AND c.src = '${SW_SRC}'
WHERE e.list_status = 'L'
  AND e.index_code IS NOT NULL
  AND TRIM(e.index_code) <> '';
"

echo "--- 映射统计 ---"
${data_mysql} -e "
SELECT
    map_type,
    COUNT(*) AS map_cnt,
    COUNT(DISTINCT etf_code) AS etf_cnt,
    COUNT(DISTINCT industry_code) AS industry_cnt
FROM dim_industry_etf_map
WHERE is_active = 1
GROUP BY map_type;

SELECT
    COUNT(*) AS listed_etf,
    SUM(CASE WHEN m.etf_code IS NOT NULL THEN 1 ELSE 0 END) AS etf_matched_sw,
    SUM(CASE WHEN m.etf_code IS NULL THEN 1 ELSE 0 END) AS etf_unmatched
FROM ods_etf_basic_di e
LEFT JOIN (
    SELECT DISTINCT etf_code
    FROM dim_industry_etf_map
    WHERE map_type = 'index_match' AND is_active = 1
) m ON e.ts_code = m.etf_code
WHERE e.list_status = 'L';
"

echo "DONE dim_industry_etf_map"
