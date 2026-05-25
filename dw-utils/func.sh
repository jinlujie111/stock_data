#!/bin/bash
# =============================================================================
# 统一配置：MySQL 连接、数据源同步、调度 CLI
# 所有账号密码仅在此文件维护；Python 禁止写死，须 source 本文件后运行。
#
# 用法：source dw-utils/func.sh
# 业务库: mysql -h localhost -P 3306 -u app_user -pjinlujie -D stock_data
# 配置库: mysql -h localhost -P 3306 -u data_config -p'1qaz!QAZjinlujie' -D data_config
# =============================================================================

_FUNC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DW_ROOT="$(cd "${_FUNC_DIR}/.." && pwd)"
path_git_utils="${path_git_utils:-${_FUNC_DIR}}"

# --- data_config 库（Token、db_sync_task）---
CONFIG_MYSQL_HOST="${CONFIG_MYSQL_HOST:-localhost}"
CONFIG_MYSQL_PORT="${CONFIG_MYSQL_PORT:-3306}"
CONFIG_MYSQL_USER="${CONFIG_MYSQL_USER:-data_config}"
CONFIG_MYSQL_PASSWORD="${CONFIG_MYSQL_PASSWORD:-1qaz!QAZjinlujie}"
CONFIG_MYSQL_DATABASE="${CONFIG_MYSQL_DATABASE:-data_config}"

# --- stock_data 业务库（ETL 写入目标）---
STOCK_MYSQL_HOST="${STOCK_MYSQL_HOST:-localhost}"
STOCK_MYSQL_PORT="${STOCK_MYSQL_PORT:-3306}"
STOCK_MYSQL_USER="${STOCK_MYSQL_USER:-app_user}"
STOCK_MYSQL_PASSWORD="${STOCK_MYSQL_PASSWORD:-jinlujie}"
STOCK_MYSQL_DATABASE="${STOCK_MYSQL_DATABASE:-stock_data}"

# --- stock_data Python 项目根 ---
STOCK_DATA_ROOT="${STOCK_DATA_ROOT:-${DW_ROOT}}"

# --- Python 解释器 ---
if [[ -z "${PYTHON_BIN:-}" ]]; then
    if [[ -x /usr/local/bin/python3.11 ]]; then
        PYTHON_BIN="/usr/local/bin/python3.11"
    elif command -v python3.11 &>/dev/null; then
        PYTHON_BIN="$(command -v python3.11)"
    else
        PYTHON_BIN="python3"
    fi
fi

export CONFIG_MYSQL_HOST CONFIG_MYSQL_PORT CONFIG_MYSQL_USER CONFIG_MYSQL_PASSWORD CONFIG_MYSQL_DATABASE
export STOCK_MYSQL_HOST STOCK_MYSQL_PORT STOCK_MYSQL_USER STOCK_MYSQL_PASSWORD STOCK_MYSQL_DATABASE
export STOCK_DATA_ROOT
export PYTHON_BIN
export MYSQL_HOST="${STOCK_MYSQL_HOST}"
export MYSQL_PORT="${STOCK_MYSQL_PORT}"
export MYSQL_USER="${STOCK_MYSQL_USER}"
export MYSQL_PASSWORD="${STOCK_MYSQL_PASSWORD}"
export MYSQL_DATABASE="${STOCK_MYSQL_DATABASE}"
export DW_FUNC_LOADED=1

# --- mysql CLI ---
data_config="mysql -h ${CONFIG_MYSQL_HOST} -P ${CONFIG_MYSQL_PORT} -u ${CONFIG_MYSQL_USER} -p'${CONFIG_MYSQL_PASSWORD}' -D ${CONFIG_MYSQL_DATABASE}"
data_mysql="mysql -h ${STOCK_MYSQL_HOST} -P ${STOCK_MYSQL_PORT} -u ${STOCK_MYSQL_USER} -p${STOCK_MYSQL_PASSWORD} -D ${STOCK_MYSQL_DATABASE}"

show_dw_env() {
    echo "  配置库: ${CONFIG_MYSQL_USER}@${CONFIG_MYSQL_HOST}:${CONFIG_MYSQL_PORT}/${CONFIG_MYSQL_DATABASE}"
    echo "  业务库: ${STOCK_MYSQL_USER}@${STOCK_MYSQL_HOST}:${STOCK_MYSQL_PORT}/${STOCK_MYSQL_DATABASE}"
    echo "  CLI: data_config | data_mysql"
}

init_data_config_schema() {
    local sql_file="${1:-${DW_ROOT}/mysql_tables/data_config.sql}"
    if [[ ! -f "${sql_file}" ]]; then
        echo "ERROR: 未找到 ${sql_file}" >&2
        return 1
    fi
    echo "初始化 data_config: ${sql_file}"
    ${data_config} < "${sql_file}"
}

install_sync_deps() {
    local req="${1:-${DW_ROOT}/requirements.txt}"
    if [[ ! -f "${req}" ]]; then
        echo "ERROR: 未找到 ${req}" >&2
        return 1
    fi
    echo "安装依赖: ${PYTHON_BIN} -m pip install -r ${req}"
    "${PYTHON_BIN}" -m pip install -r "${req}" -i https://pypi.tuna.tsinghua.edu.cn/simple
}

run_data_sync() {
    local runner="${DW_ROOT}/dw-sync/sync_runner.sh"
    if [[ ! -f "${runner}" ]]; then
        echo "ERROR: 未找到 ${runner}" >&2
        return 1
    fi
    bash "${runner}" "$@"
}
