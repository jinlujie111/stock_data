#!/bin/bash
# =============================================================================
# 统一配置：MySQL 连接、数据源同步、调度 CLI
# 所有账号密码按环境维护在 env/*.sh；Python 禁止写死，须 source 本文件后运行。
#
# 环境切换（DW_ENV）：
#   source dw-utils/func.sh              # 默认 prod 生产
#   DW_ENV=pre source dw-utils/func.sh   # 预发
#   use_dw_env pre                       # 当前 shell 内切换
# =============================================================================

_FUNC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DW_ROOT="$(cd "${_FUNC_DIR}/.." && pwd)"
path_git_utils="${path_git_utils:-${_FUNC_DIR}}"

# --- 选择环境：prod | pre（可通过环境变量提前指定）---
DW_ENV="${DW_ENV:-prod}"
_ENV_FILE="${_FUNC_DIR}/env/${DW_ENV}.sh"
if [[ ! -f "${_ENV_FILE}" ]]; then
    echo "ERROR: 未知环境 DW_ENV=${DW_ENV}，可选: prod pre（文件 ${_ENV_FILE} 不存在）" >&2
    return 1 2>/dev/null || exit 1
fi
# shellcheck source=env/prod.sh
source "${_ENV_FILE}"

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

export DW_ENV
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

# --- mysql CLI（与 env 变量一致）---
# 配置库：含特殊字符的密码用单引号包裹 -p
data_config="mysql -h ${CONFIG_MYSQL_HOST} -P ${CONFIG_MYSQL_PORT} -u ${CONFIG_MYSQL_USER} -p'${CONFIG_MYSQL_PASSWORD}' -D ${CONFIG_MYSQL_DATABASE}"
data_mysql="mysql -h ${STOCK_MYSQL_HOST} -P ${STOCK_MYSQL_PORT} -u ${STOCK_MYSQL_USER} -p${STOCK_MYSQL_PASSWORD} -D ${STOCK_MYSQL_DATABASE}"

# --- 当前 shell 切换环境（prod / pre）---
use_dw_env() {
    local target="${1:?用法: use_dw_env prod|pre}"
    export DW_ENV="${target}"
    # shellcheck source=func.sh
    source "${_FUNC_DIR}/func.sh"
    show_dw_env
}

# --- 打印当前连接（不输出密码明文）---
show_dw_env() {
    echo "DW_ENV=${DW_ENV}"
    echo "  配置库: ${CONFIG_MYSQL_USER}@${CONFIG_MYSQL_HOST}:${CONFIG_MYSQL_PORT}/${CONFIG_MYSQL_DATABASE}"
    echo "  业务库: ${STOCK_MYSQL_USER}@${STOCK_MYSQL_HOST}:${STOCK_MYSQL_PORT}/${STOCK_MYSQL_DATABASE}"
    echo "  CLI: data_config | data_mysql"
}

# --- 初始化 data_config 库表结构 ---
init_data_config_schema() {
    local sql_file="${1:-${DW_ROOT}/mysql_tables/data_config.sql}"
    if [[ ! -f "${sql_file}" ]]; then
        echo "ERROR: 未找到 ${sql_file}" >&2
        return 1
    fi
    echo "[${DW_ENV}] 初始化 data_config: ${sql_file}"
    ${data_config} < "${sql_file}"
}

# --- 安装 sync Python 依赖 ---
install_sync_deps() {
    local req="${1:-${DW_ROOT}/requirements.txt}"
    if [[ ! -f "${req}" ]]; then
        echo "ERROR: 未找到 ${req}" >&2
        return 1
    fi
    echo "安装依赖: ${PYTHON_BIN} -m pip install -r ${req}"
    "${PYTHON_BIN}" -m pip install -r "${req}" -i https://pypi.tuna.tsinghua.edu.cn/simple
}

# --- 执行数据源同步 ---
run_data_sync() {
    local runner="${DW_ROOT}/dw-sync/sync_runner.sh"
    if [[ ! -f "${runner}" ]]; then
        echo "ERROR: 未找到 ${runner}" >&2
        return 1
    fi
    bash "${runner}" "$@"
}
