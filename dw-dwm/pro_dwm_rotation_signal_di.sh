#!/usr/bin/env bash
# 板块轮动每日信号（申万一级）
# XXL: 在 sw_daily / moneyflow_ind_dc 同步完成后执行
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck disable=SC1091
source "${ROOT}/dw-utils/func.sh"
cd "${ROOT}"
export PYTHONPATH="${ROOT}:${ROOT}/dw-utils:${PYTHONPATH:-}"
python -m etl.sector_rotation.signal_batch "$@"
