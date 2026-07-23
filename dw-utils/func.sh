#!/bin/bash
# =============================================================================
# 统一配置：MySQL 连接、数据源同步、调度 CLI
# 所有账号密码仅在此文件维护；Python 禁止写死，须 source 本文件后运行。
#
# 用法：source dw-utils/func.sh
# 业务库: mysql -h localhost -P 3306 -u app_user -pjinlujie -D stock_data
# 网站库: mysql -h 127.0.0.1 -P 3306 -u data_industry -p'1qaz!QAZjinlujie' -D data_industry
# 配置库: mysql -h localhost -P 3306 -u data_config -p'1qaz!QAZjinlujie' -D data_config
# =============================================================================

_FUNC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DW_ROOT="$(cd "${_FUNC_DIR}/.." && pwd)"
path_git_utils="${path_git_utils:-${_FUNC_DIR}}"
# 密码含 ! 时避免 bash 历史展开篡改
set +o histexpand 2>/dev/null || true

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

# --- data_industry 网站库（行业资金流 Web 用户等业务，与 stock_data 分离）---
# 用 127.0.0.1 走 TCP，避免 localhost 套接字匹配 @'localhost' 账号不一致
INDUSTRY_MYSQL_HOST="${INDUSTRY_MYSQL_HOST:-127.0.0.1}"
INDUSTRY_MYSQL_PORT="${INDUSTRY_MYSQL_PORT:-3306}"
INDUSTRY_MYSQL_USER="${INDUSTRY_MYSQL_USER:-data_industry}"
INDUSTRY_MYSQL_PASSWORD="${INDUSTRY_MYSQL_PASSWORD:-1qaz!QAZjinlujie}"
INDUSTRY_MYSQL_DATABASE="${INDUSTRY_MYSQL_DATABASE:-data_industry}"

# --- 清除系统 HTTP 代理（避免 requests 误读占位符 http_proxy，影响 Tushare/AkShare）---
unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY ALL_PROXY no_proxy NO_PROXY 2>/dev/null || true

# --- Tushare 代理 API（db_token.api_url 优先；此处为兜底）---
TUSHARE_HTTP_URL="${TUSHARE_HTTP_URL:-http://a.sszhixia.cn/}"
# 代理 IP 兜底（阿里云 DNS 不稳时必配；curl -4 http://a.sszhixia.cn/ 不通则改 IP）
TUSHARE_API_FALLBACK_IP="${TUSHARE_API_FALLBACK_IP:-104.21.96.101}"
# 1=优先用 FALLBACK_IP，不走系统 DNS（批量补数推荐）
TUSHARE_USE_FALLBACK_IP="${TUSHARE_USE_FALLBACK_IP:-1}"
# 1=强制仅用域名（不推荐）
TUSHARE_PROXY_USE_DOMAIN="${TUSHARE_PROXY_USE_DOMAIN:-0}"
# trade_cal 全量区间（sync_mode=full 时生效）
TUSHARE_TRADE_CAL_START_DATE="${TUSHARE_TRADE_CAL_START_DATE:-20200101}"
TUSHARE_TRADE_CAL_END_DATE="${TUSHARE_TRADE_CAL_END_DATE:-}"
# 历史补数：HTTP 读超时与失败重试（dc_index/dc_daily 等较慢）
TUSHARE_HTTP_TIMEOUT="${TUSHARE_HTTP_TIMEOUT:-15}"
TUSHARE_FETCH_RETRIES="${TUSHARE_FETCH_RETRIES:-3}"
TUSHARE_FETCH_RETRY_SLEEP="${TUSHARE_FETCH_RETRY_SLEEP:-5}"

# --- stock_data Python 项目根 ---
STOCK_DATA_ROOT="${STOCK_DATA_ROOT:-${DW_ROOT}}"

# --- ETL 日志目录（XXL 非 root 时请 export 为 ${DW_ROOT}/log/stock_log）---
STOCK_LOG_DIR="${STOCK_LOG_DIR:-/root/log/stock_log}"

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
export INDUSTRY_MYSQL_HOST INDUSTRY_MYSQL_PORT INDUSTRY_MYSQL_USER INDUSTRY_MYSQL_PASSWORD INDUSTRY_MYSQL_DATABASE
export IFF_MYSQL_HOST="${INDUSTRY_MYSQL_HOST}"
export IFF_MYSQL_PORT="${INDUSTRY_MYSQL_PORT}"
export IFF_MYSQL_USER="${INDUSTRY_MYSQL_USER}"
export IFF_MYSQL_PASSWORD="${INDUSTRY_MYSQL_PASSWORD}"
export IFF_MYSQL_DATABASE="${INDUSTRY_MYSQL_DATABASE}"
export TUSHARE_HTTP_URL TUSHARE_API_FALLBACK_IP TUSHARE_USE_FALLBACK_IP TUSHARE_PROXY_USE_DOMAIN
export TUSHARE_TRADE_CAL_START_DATE TUSHARE_TRADE_CAL_END_DATE
export TUSHARE_HTTP_TIMEOUT TUSHARE_FETCH_RETRIES TUSHARE_FETCH_RETRY_SLEEP
export STOCK_DATA_ROOT
export STOCK_LOG_DIR
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
data_industry="mysql -h ${INDUSTRY_MYSQL_HOST} -P ${INDUSTRY_MYSQL_PORT} -u ${INDUSTRY_MYSQL_USER} -p'${INDUSTRY_MYSQL_PASSWORD}' -D ${INDUSTRY_MYSQL_DATABASE}"

show_dw_env() {
    echo "  配置库: ${CONFIG_MYSQL_USER}@${CONFIG_MYSQL_HOST}:${CONFIG_MYSQL_PORT}/${CONFIG_MYSQL_DATABASE}"
    echo "  业务库: ${STOCK_MYSQL_USER}@${STOCK_MYSQL_HOST}:${STOCK_MYSQL_PORT}/${STOCK_MYSQL_DATABASE}"
    echo "  网站库: ${INDUSTRY_MYSQL_USER}@${INDUSTRY_MYSQL_HOST}:${INDUSTRY_MYSQL_PORT}/${INDUSTRY_MYSQL_DATABASE}"
    echo "  CLI: data_config | data_mysql | data_industry"
}

_run_industry_mysql() {
  MYSQL_PWD="${INDUSTRY_MYSQL_PASSWORD}" mysql \
    -h "${INDUSTRY_MYSQL_HOST}" -P "${INDUSTRY_MYSQL_PORT}" \
    -u "${INDUSTRY_MYSQL_USER}" "$@"
}

init_data_industry_schema() {
    local sql_file="${1:-${DW_ROOT}/mysql_tables/data_industry.sql}"
    if [[ ! -f "${sql_file}" ]]; then
        echo "ERROR: 未找到 ${sql_file}" >&2
        return 1
    fi
    echo "初始化 data_industry: ${sql_file}"
    _run_industry_mysql -D "${INDUSTRY_MYSQL_DATABASE}" < "${sql_file}"
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

trade_day_flag() {
    export PYTHONPATH="${DW_ROOT}/dw-utils:${DW_ROOT}/dw-sync:${PYTHONPATH:-}"
    "${PYTHON_BIN}" "${DW_ROOT}/dw-sync/trade_data_flag.py" "$@"
}

run_data_sync() {
    local runner="${DW_ROOT}/dw-sync/sync_runner.sh"
    if [[ ! -f "${runner}" ]]; then
        echo "ERROR: 未找到 ${runner}" >&2
        return 1
    fi
    bash "${runner}" "$@"
}

# 按交易日区间逐日调用 run_data_sync（等价于 sync_data.py --end-date）
run_data_sync_range() {
    local start end runner
    if [[ $# -lt 2 ]]; then
        echo "用法: run_data_sync_range START_YYYYMMDD END_YYYYMMDD [--source-table NAME] [--force] ..." >&2
        return 1
    fi
    start="$(get_date "$1")"
    end="$(get_date "$2" "$1")"
    shift 2
    runner="${DW_ROOT}/dw-sync/sync_runner.sh"
    bash "${runner}" "${start}" --end-date "${end}" "$@"
}

run_dwm_market_breadth() {
    local runner="${DW_ROOT}/dw-dwm/pro_dwm_market_breadth_di.sh"
    if [[ ! -f "${runner}" ]]; then
        echo "ERROR: 未找到 ${runner}" >&2
        return 1
    fi
    bash "${runner}" "$@"
}

run_dwm_dc_industry_fund_flow() {
    local runner="${DW_ROOT}/dw-dwm/pro_dwm_dc_industry_fund_flow_di.sh"
    if [[ ! -f "${runner}" ]]; then
        echo "ERROR: 未找到 ${runner}" >&2
        return 1
    fi
    bash "${runner}" "$@"
}

run_dwm_dc_industry_trend_strength() {
    local runner="${DW_ROOT}/dw-dwm/pro_dwm_dc_industry_trend_strength_di.sh"
    if [[ ! -f "${runner}" ]]; then
        echo "ERROR: 未找到 ${runner}" >&2
        return 1
    fi
    bash "${runner}" "$@"
}

run_dwm_dc_industry_prosperity() {
    local runner="${DW_ROOT}/dw-dwm/pro_dwm_dc_industry_prosperity_di.sh"
    if [[ ! -f "${runner}" ]]; then
        echo "ERROR: 未找到 ${runner}" >&2
        return 1
    fi
    bash "${runner}" "$@"
}

run_dwm_dc_industry_market_heat() {
    local runner="${DW_ROOT}/dw-dwm/pro_dwm_dc_industry_market_heat_di.sh"
    if [[ ! -f "${runner}" ]]; then
        echo "ERROR: 未找到 ${runner}" >&2
        return 1
    fi
    bash "${runner}" "$@"
}

run_dwm_dc_industry_diffusion() {
    local runner="${DW_ROOT}/dw-dwm/pro_dwm_dc_industry_diffusion_di.sh"
    if [[ ! -f "${runner}" ]]; then
        echo "ERROR: 未找到 ${runner}" >&2
        return 1
    fi
    bash "${runner}" "$@"
}

run_dws_dc_industry_mainline_score() {
    local runner="${DW_ROOT}/dw-dws/pro_dws_dc_industry_mainline_score_di.sh"
    if [[ ! -f "${runner}" ]]; then
        echo "ERROR: 未找到 ${runner}" >&2
        return 1
    fi
    bash "${runner}" "$@"
}

run_dws_dc_industry_mainline_monitor() {
    local runner="${DW_ROOT}/dw-dws/pro_dws_dc_industry_mainline_monitor_di.sh"
    if [[ ! -f "${runner}" ]]; then
        echo "ERROR: 未找到 ${runner}" >&2
        return 1
    fi
    bash "${runner}" "$@"
}

run_dwd_market_breadth() {
    run_dwm_market_breadth "$@"
}

run_dim_industry_etf_map() {
    local runner="${DW_ROOT}/dw-dim/pro_dim_industry_etf_map.sh"
    if [[ ! -f "${runner}" ]]; then
        echo "ERROR: 未找到 ${runner}" >&2
        return 1
    fi
    bash "${runner}" "$@"
}

run_vp_batch() {
    local runner="${DW_ROOT}/dw-dwm/pro_dwm_industry_vp_score.sh"
    if [[ ! -f "${runner}" ]]; then
        echo "ERROR: 未找到 ${runner}" >&2
        return 1
    fi
    bash "${runner}" "$@"
}

run_board_timing_batch() {
    local runner="${DW_ROOT}/dw-dwm/pro_dwm_board_timing_signal_di.sh"
    if [[ ! -f "${runner}" ]]; then
        echo "ERROR: 未找到 ${runner}" >&2
        return 1
    fi
    bash "${runner}" "$@"
}

run_vp_backfill() {
    local runner="${DW_ROOT}/dw-dwm/backfill_vp_batch.sh"
    if [[ ! -f "${runner}" ]]; then
        echo "ERROR: 未找到 ${runner}" >&2
        return 1
    fi
    bash "${runner}" "$@"
}

run_sector_dragon_batch() {
    local runner="${DW_ROOT}/dw-dwm/pro_dwm_sector_dragon_score.sh"
    if [[ ! -f "${runner}" ]]; then
        echo "ERROR: 未找到 ${runner}" >&2
        return 1
    fi
    bash "${runner}" "$@"
}

run_ods_completeness_monitor() {
    local runner="${DW_ROOT}/dw-monitor/pro_ods_completeness.sh"
    if [[ ! -f "${runner}" ]]; then
        echo "ERROR: 未找到 ${runner}" >&2
        return 1
    fi
    bash "${runner}" "$@"
}

#得到统计日期：YYYYMMDD（无参或全空时默认昨日；多参时取第一个非空）
get_date()
{
  local d="" arg
  for arg in "$@"; do
    if [ -n "$arg" ]; then
      d="$arg"
      break
    fi
  done
  if [ -n "$d" ]; then
      n_date=$(date -d "$d" +"%Y%m%d" 2>/dev/null) || n_date=$(date -d yesterday +"%Y%m%d")
  else
      n_date=$(date -d yesterday +"%Y%m%d")
  fi
  echo "${n_date}"
}

#格式化日期：YYYY-MM-DD
format_date()
{
  Y=`expr substr $1 1 4`
  M=`expr substr $1 5 2`
  D=`expr substr $1 7 2`
  echo $Y"-"$M"-"$D
}

#获得当前月第一天
get_first_day()
{
  Y=`expr substr $1 1 4`
  M=`expr substr $1 5 2`
  echo $Y$M"01"
}

#获得当前月最后一天
get_last_day()
{

  Y=`expr substr $1 1 4`
  M=`expr substr $1 5 2`

  days=`get_mon_days $Y$M`
  D=$days
  echo $Y$M$D
}

#得到对应月份
get_month()
{
  if [ $# -ge 1 ];then
    Y=`expr substr $1 1 4`
    M=`expr substr $1 5 2`
    echo $Y$M
  else
    echo `date -d "today -1 month" +%Y%m`
  fi
}

#得到days天后数据：days为正数则days天后日期，days为负数则days天前日期，默认days=1
add_date()
{
  if [ $# -eq 1 ] ; then
    days=1
  else
    days=$2
  fi
  timestamp_date=`date -d $1 +%s`
  timestamp_nextdate=`expr ${timestamp_date} '+' $days '*' 86400`
  next_date=`date -d @${timestamp_nextdate} +%Y%m%d`
  echo $next_date
}

# 两个日期相减,获取对应的天数
date_sub(){
  # 参数不足
  if [ $# -lt 2 ] ; then
    return
  fi
  # 默认返回间隔天数
  if [ "$3" = "" ];then
    d_type="d"
  else
    d_type="$3"
  fi
  # 暂时先不考虑不到1天的情况
  diff_second=$((`date -d "$1" +%s`-`date -d "$2" +%s`))
  if [ "$d_type" = "s" ];then
    let diff_out=$diff_second
  elif [ "$d_type" = "m" ];then
    let diff_out=$diff_second/60
  elif [ "$d_type" = "h" ];then
    let diff_out=$diff_second/3600
  elif [ "$d_type" = "d" ];then
    let diff_out=$diff_second/86400
  fi
  echo $diff_out
}

#得到上个月对应月份
get_last_month() {
  Y_M=`expr substr $1 1 6`
  M=`date -d "${Y_M}01 last month" +%Y%m`
  echo $M
}

#得到下个月对应月份
get_next_month(){
  Y_M=`expr substr $1 1 6`
  M=`date -d "${Y_M}01 next month" +%Y%m`
  echo $M
}

#得到当前季度
get_quarter(){
  Y=`expr substr $1 1 4`
  M=`expr substr $1 5 2`

 case $M in
  01|02|03) quar=01;;
  04|05|06) quar=02;;
  07|08|09) quar=03;;
  10|11|12) quar=04;;
 esac

 echo $Y$quar
}

#得到当前季度第一天
get_quarter_first_day(){
  quarter_day=`get_quarter $1`
  Y=`expr substr $quarter_day 1 4`
  M=`expr substr $quarter_day 5 2`

  case $M in
    01) res=$Y"0101";;
    02) res=$Y"0401";;
    03) res=$Y"0701";;
    04) res=$Y"1001";;
  esac

  echo $res
}

#得到当前季度最后一天
get_quarter_last_day(){
  quarter_day=`get_quarter $1`
  Y=`expr substr $quarter_day 1 4`
  M=`expr substr $quarter_day 5 2`
  #echo $quarter_day"季度"
  #echo $M"月份哦”"

  case $M in
    01) res=$Y"0331";;
    02) res=$Y"0630";;
    03) res=$Y"0930";;
    04) res=$Y"1231";;
  esac

  echo $res
}

# 得到上月最后1天
get_date_m()
{
  # 如果有参数则使用传入的参数,否则赋值为上月最后1天
  if [ $# -ge 1 ];then
      n_date=`get_last_day $1`
      if [ $? -ne 0 ];then
        v_tmp_date=`date -d today +"%Y%m01"`
        n_date=`date -d "${v_tmp_date} -1 day" +"%Y%m%d"`
      fi
  else
      v_tmp_date=`date -d today +"%Y%m01"`
      n_date=`date -d "${v_tmp_date} -1 day" +"%Y%m%d"`
  fi
  echo ${n_date}
}

# 获取秒数的时分秒
swap_seconds (){
    seconds=$1
    hour=$(echo "${seconds}/3600" | bc)
    minute=$(echo "${seconds}/60%60" | bc)
    sec=$(echo "${seconds}%60" | bc)
    printf "%02d:%02d:%02d" ${hour} ${minute} ${sec}
}

#得到连续的统计日期：YYYYMMDD ： 20200101 20200102
get_continuous_date(){
  startdate=$(get_date $1)
  enddate=$(get_date $2 $1)
  while [[ $startdate -le $enddate ]]
    do
      n_date_list=(${n_date_list[*]} $startdate)
       startdate=$(date -d "${startdate} +1 day" +%Y%m%d)
    done
  echo "${n_date_list[*]}"
}

# 区间内 A 股交易日（ods_trading_day）；无日历时 fallback 自然日
get_trading_dates() {
  local startdate enddate v_start v_end cnt
  startdate=$(get_date "$1")
  enddate=$(get_date "$2" "$1")
  v_start=$(format_date "${startdate}")
  v_end=$(format_date "${enddate}")
  cnt="$(${data_mysql} -N -e "
    SELECT COUNT(*)
    FROM ods_trading_day
    WHERE trade_date >= '${v_start}' AND trade_date <= '${v_end}';
  " 2>/dev/null || echo 0)"
  if [[ -z "${cnt}" || "${cnt}" -eq 0 ]]; then
    echo "WARN: ods_trading_day ${v_start}~${v_end} 无记录，fallback get_continuous_date" >&2
    get_continuous_date "$1" "$2"
    return
  fi
  ${data_mysql} -N -e "
    SELECT DATE_FORMAT(trade_date, '%Y%m%d')
    FROM ods_trading_day
    WHERE trade_date >= '${v_start}' AND trade_date <= '${v_end}'
    ORDER BY trade_date;
  "
}

# DWM 按交易日循环：loader 返回非 0 视为 skip（ODS 无数据），仅全无成功时 exit 1
run_dwm_by_trading_day() {
  local n_date_s="$1" n_date_e="$2" loader="$3"
  local ok_cnt=0 skip_cnt=0 cur_date
  if [[ -z "${loader}" ]] || ! declare -f "${loader}" >/dev/null 2>&1; then
    echo "ERROR: run_dwm_by_trading_day 未找到函数 ${loader}" >&2
    return 1
  fi
  for cur_date in $(get_trading_dates "${n_date_s}" "${n_date_e}"); do
    if "${loader}" "${cur_date}"; then
      ok_cnt=$((ok_cnt + 1))
    else
      skip_cnt=$((skip_cnt + 1))
    fi
  done
  echo "SUMMARY ${loader}: ok=${ok_cnt} skipped=${skip_cnt} total=$((ok_cnt + skip_cnt))"
  if [[ "${ok_cnt}" -eq 0 ]]; then
    echo "ERROR: 区间内无任何交易日写入成功" >&2
    return 1
  fi
  if [[ "${skip_cnt}" -gt 0 ]]; then
    echo "WARN: ${skip_cnt} 个交易日 skip（多为 ODS 无数据）"
  else
    echo "DONE all trading days"
  fi
  return 0
}

#得到连续的统计月：YYYYMM ： 202001 202002
get_continuous_month(){
  startdate=$(get_date $1)
  enddate=$(get_date $2 $1)
  startmonth=${startdate:0:6}
  endmonth=${enddate:0:6}
  while [[ $startmonth -le $endmonth ]]
    do
      month_list=(${month_list[*]} $startmonth)
      startmonth=$(date -d "${startmonth}01 +1 month" +%Y%m)
    done
    echo "${month_list[*]}"
}

#设置并发,入参为文件描述符+并发数
set_parallel(){
  tmp_fifofile="/tmp/$1.fifo"     # 脚本运行的当前进程ID号作为文件名
  mkfifo "$tmp_fifofile"          # 新建一个随机fifo管道文件
  eval "exec $1<>$tmp_fifofile"   # 定义文件描述符$1指向这个fifo管道文件
  rm -rf "$tmp_fifofile"
  for ((i=1;i<=$2;i++))
  do
    echo >& $1                    #&$1代表引用文件描述符$1，这条命令代表往管道里面放入了一个"令牌"
  done
}

# 级联删除指定的进程和子进程,暂时只遍历1层,不做递归
kill_process(){
    # 列出当前进程信息
    ps -ef | grep $1
    pid=`ps -ef | grep $1 | grep -v "grep" | awk '{print $2}'`
    if [ "$pid" = "" ];then
        return 0
    fi

    # 遍历kill子进程
    echo '----------------`date -d now +"%Y-%m-%d %H:%M:%S" kill当前进程和子进程:$pid`---------------------'
    if [ $? -eq 0 ];then echo "kill $pid is ok!";else echo "kill $pid is error!";fi
    ps -ef | grep $pid | awk '{if($3=='$pid') print}'
    p_cnt=`ps -ef | grep $pid | awk '{if($3=='$pid') print}' | wc -l`
    if [ $p_cnt -gt 0 ];then
        ps -ef | grep $pid | awk '{if($3=='$pid') print $2}' | xargs kill -9
    fi
    kill -9 $pid
    return 0
}
