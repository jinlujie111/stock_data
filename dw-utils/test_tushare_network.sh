#!/bin/bash
# Tushare 中转域名连通性诊断（在阿里云 ECS 上执行）
# 用法: source dw-utils/func.sh && bash dw-utils/test_tushare_network.sh [host]
set -euo pipefail

HOST="${1:-a.sszhixia.cn}"
echo "=== 诊断目标: ${HOST} ==="

echo "--- 1. 本机路由 / 默认网关 ---"
ip route 2>/dev/null | head -5 || route -n 2>/dev/null | head -5 || true

echo "--- 2. DNS 解析 (A / AAAA) ---"
getent ahostsv4 "${HOST}" 2>/dev/null | head -3 || echo "(无 IPv4 记录或 getent 不可用)"
getent ahostsv6 "${HOST}" 2>/dev/null | head -3 || echo "(无 IPv6 记录)"

echo "--- 3. curl IPv4 HTTP :80（404/405 亦表示已连通，仅根路径 / 常无页面）---"
if curl -4 -sS -o /dev/null -w "http_code=%{http_code} time=%{time_total}s\n" \
  --connect-timeout 8 "http://${HOST}/" 2>&1; then
  echo "    → TCP 连通（Tushare 代理请用 POST /trade_cal 等，不要用 GET /）"
else
  echo "IPv4:80 失败"
fi

echo "--- 4. curl IPv4 HTTPS :443 ---"
if curl -4 -sS -o /dev/null -w "http_code=%{http_code} time=%{time_total}s\n" \
  --connect-timeout 8 "https://${HOST}/" 2>&1; then
  echo "    → TCP 连通"
else
  echo "IPv4:443 失败"
fi

echo "--- 5. curl 默认（可能走 IPv6）---"
if curl -sS -o /dev/null -w "http_code=%{http_code}\n" \
  --connect-timeout 8 "http://${HOST}/" 2>&1; then
  true
else
  echo "默认栈失败 → 请 export TUSHARE_FORCE_IPV4=1（func.sh 已默认开启）"
fi

echo "--- 6. 出站公网（对比）---"
curl -4 -sS -o /dev/null -w "baidu http_code=%{http_code}\n" \
  --connect-timeout 8 "http://www.baidu.com/" 2>&1 || echo "无法访问外网，请检查 ECS 公网/NAT/安全组出站"

echo "=== 结束 ==="
echo "结论: http_code=404 且 baidu=200 → 外网与中转域名均正常，可执行 run_data_sync"
echo "若 Python 仍 Network unreachable: TUSHARE_FORCE_IPV4=1（保留域名，勿改 URL 为 IP）"
echo "可选: db_token.api_url 使用 https://${HOST}/ （与 http 二选一，以代理商为准）"
