#!/bin/bash
# =============================================================================
# 统一配置：MySQL 连接、数据源同步、调度 CLI
# 所有账号密码仅在此文件维护；Python(dw/sync) 禁止写死配置，须 source 本文件后运行。
# =============================================================================

_FUNC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DW_ROOT="$(cd "${_FUNC_DIR}/.." && pwd)"
path_git_utils="${path_git_utils:-${_FUNC_DIR}}"

# --- data_config 库（Token、db_sync_task 任务配置）---
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

# --- xxl-job 调度库 ---
XXL_MYSQL_HOST="${XXL_MYSQL_HOST:-localhost}"
XXL_MYSQL_PORT="${XXL_MYSQL_PORT:-3306}"
XXL_MYSQL_USER="${XXL_MYSQL_USER:-xxljob}"
XXL_MYSQL_PASSWORD="${XXL_MYSQL_PASSWORD:-1qaz!QAZjinlujie}"
XXL_MYSQL_DATABASE="${XXL_MYSQL_DATABASE:-xxl_job}"

# --- stock_data Python 项目根（默认即本仓库根目录）---
STOCK_DATA_ROOT="${STOCK_DATA_ROOT:-${DW_ROOT}}"

# --- Python 解释器（脚本中 alias 不生效，须用绝对路径）---
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
export XXL_MYSQL_HOST XXL_MYSQL_PORT XXL_MYSQL_USER XXL_MYSQL_PASSWORD XXL_MYSQL_DATABASE
export STOCK_DATA_ROOT
export PYTHON_BIN
export MYSQL_HOST="${STOCK_MYSQL_HOST}"
export MYSQL_PORT="${STOCK_MYSQL_PORT}"
export MYSQL_USER="${STOCK_MYSQL_USER}"
export MYSQL_PASSWORD="${STOCK_MYSQL_PASSWORD}"
export MYSQL_DATABASE="${STOCK_MYSQL_DATABASE}"
# Python 侧校验：仅当通过 func.sh / sync_runner.sh 加载后为 1
export DW_FUNC_LOADED=1

# --- mysql CLI（与上方变量一致）---
data_config="mysql -h ${CONFIG_MYSQL_HOST} -P ${CONFIG_MYSQL_PORT} -u ${CONFIG_MYSQL_USER} -p'${CONFIG_MYSQL_PASSWORD}' -D ${CONFIG_MYSQL_DATABASE}"
data_mysql="mysql -h ${STOCK_MYSQL_HOST} -P ${STOCK_MYSQL_PORT} -u ${STOCK_MYSQL_USER} -p${STOCK_MYSQL_PASSWORD} -D ${STOCK_MYSQL_DATABASE}"
xxl_job="mysql -h ${XXL_MYSQL_HOST} -P ${XXL_MYSQL_PORT} -u ${XXL_MYSQL_USER} -p'${XXL_MYSQL_PASSWORD}' -D ${XXL_MYSQL_DATABASE}"

# --- 初始化 data_config 库表结构 ---
init_data_config_schema() {
    local sql_file="${1:-${DW_ROOT}/mysql_tables/data_config.sql}"
    if [[ ! -f "${sql_file}" ]]; then
        echo "ERROR: 未找到 ${sql_file}" >&2
        return 1
    fi
    echo "初始化 data_config: ${sql_file}"
    ${data_config} < "${sql_file}"
}

# --- 初始化 xxl-job 中 stock_data 同步调度（cron 不再写在 db_sync_task）---
init_xxl_job_stock_sync() {
    local sql_file="${1:-${DW_ROOT}/mysql_tables/xxl_job_stock_sync.sql}"
    if [[ ! -f "${sql_file}" ]]; then
        echo "ERROR: 未找到 ${sql_file}" >&2
        return 1
    fi
    echo "初始化 xxl-job 调度: ${sql_file}"
    ${xxl_job} < "${sql_file}"
}

# --- 安装 sync 所需 Python 依赖（使用 PYTHON_BIN）---
install_sync_deps() {
    local req="${1:-${DW_ROOT}/requirements.txt}"
    if [[ ! -f "${req}" ]]; then
        echo "ERROR: 未找到 ${req}" >&2
        return 1
    fi
    echo "安装依赖: ${PYTHON_BIN} -m pip install -r ${req}"
    "${PYTHON_BIN}" -m pip install -r "${req}" -i https://pypi.tuna.tsinghua.edu.cn/simple
}

# --- 执行数据源同步（封装 dw/sync/sync_runner.sh）---
run_data_sync() {
    local runner="${DW_ROOT}/sync/sync_runner.sh"
    if [[ ! -f "${runner}" ]]; then
        echo "ERROR: 未找到 ${runner}" >&2
        return 1
    fi
    bash "${runner}" "$@"
}
