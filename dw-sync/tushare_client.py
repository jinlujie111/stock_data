#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""从 db_token 加载 Tushare Pro 客户端（token + 代理 API URL）。"""
from __future__ import annotations

import logging
import os
import socket
import subprocess
from typing import Any
from urllib.parse import urlparse, urlunparse

logger = logging.getLogger(__name__)

_pro_cache: dict[str, Any] = {}
_host_header_patched = False
_proxy_virtual_host: str | None = None
_host_ip_cache: dict[str, str] = {}


def _normalize_api_url(url: str | None) -> str | None:
    if not url or not str(url).strip():
        return None
    u = str(url).strip()
    if not u.endswith("/"):
        u += "/"
    return u


def _fallback_ip() -> str:
    return (os.getenv("TUSHARE_API_FALLBACK_IP") or "").strip()


def _use_fallback_ip_first() -> bool:
    return os.getenv("TUSHARE_USE_FALLBACK_IP", "1").lower() in ("1", "true", "yes")


def _resolve_via_getent(hostname: str) -> str | None:
    try:
        out = subprocess.check_output(
            ["getent", "ahostsv4", hostname],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=5,
        )
        for line in out.splitlines():
            parts = line.split()
            if len(parts) >= 1 and parts[0].count(".") == 3:
                return parts[0]
    except (OSError, subprocess.SubprocessError):
        pass
    return None


def _resolve_host_to_ipv4(hostname: str) -> str | None:
    """解析代理域名为 IPv4；阿里云建议配置 TUSHARE_API_FALLBACK_IP 直连。"""
    if not hostname or hostname.replace(".", "").isdigit():
        return hostname

    if hostname in _host_ip_cache:
        return _host_ip_cache[hostname]

    fallback = _fallback_ip()
    if _use_fallback_ip_first() and fallback:
        _host_ip_cache[hostname] = fallback
        return fallback

    for family in (socket.AF_INET, socket.AF_INET6):
        try:
            infos = socket.getaddrinfo(hostname, None, family, socket.SOCK_STREAM)
        except OSError as exc:
            logger.debug("getaddrinfo %s family=%s: %s", hostname, family, exc)
            continue
        for info in infos:
            addr = info[4][0]
            if addr.startswith("::ffff:"):
                ip = addr.split("::ffff:")[-1]
                _host_ip_cache[hostname] = ip
                return ip
            if family == socket.AF_INET:
                _host_ip_cache[hostname] = addr
                return addr

    ip = _resolve_via_getent(hostname)
    if ip:
        _host_ip_cache[hostname] = ip
        return ip

    if fallback:
        logger.warning("域名 %s DNS 失败，使用 TUSHARE_API_FALLBACK_IP=%s", hostname, fallback)
        _host_ip_cache[hostname] = fallback
        return fallback

    return None


def prime_proxy_host(hostname: str = "a.sszhixia.cn") -> str | None:
    """补数脚本启动时预解析并缓存 IP。"""
    ip = _resolve_host_to_ipv4(hostname)
    if ip:
        logger.info("代理域名 %s 已缓存为 IP %s", hostname, ip)
    return ip


def _ensure_requests_host_header_patch(virtual_host: str) -> None:
    """请求走 IP 时补上 Host 头（Cloudflare 代理需要）。"""
    global _host_header_patched, _proxy_virtual_host
    if _host_header_patched and _proxy_virtual_host == virtual_host:
        return

    import requests

    _proxy_virtual_host = virtual_host
    _orig_request = requests.Session.request

    def _request_with_host(self, method, url, *args, **kwargs):
        parsed = urlparse(url)
        host = parsed.hostname or ""
        if (
            _proxy_virtual_host
            and host.replace(".", "").isdigit()
            and host != _proxy_virtual_host
        ):
            headers = dict(kwargs.get("headers") or {})
            headers.setdefault("Host", _proxy_virtual_host)
            kwargs["headers"] = headers
        return _orig_request(self, method, url, *args, **kwargs)

    requests.Session.request = _request_with_host  # type: ignore[method-assign]
    _host_header_patched = True


def _configure_proxy_url(api_url: str) -> str:
    """
    阿里云 ECS：DNS 不稳定时用 IP + Host 头访问 Cloudflare。
    TUSHARE_PROXY_USE_DOMAIN=1 时强制仅用域名（不推荐）。
    """
    if os.getenv("TUSHARE_PROXY_USE_DOMAIN", "").lower() in ("1", "true", "yes"):
        return api_url

    parsed = urlparse(api_url)
    hostname = parsed.hostname
    if not hostname:
        return api_url

    ip = _resolve_host_to_ipv4(hostname)
    if not ip or ip == hostname:
        raise RuntimeError(
            f"无法解析 Tushare 代理域名 {hostname!r}。"
            f"请在 func.sh 设置 TUSHARE_API_FALLBACK_IP（Cloudflare IPv4），"
            f"或 /etc/hosts 添加: <IP> {hostname}"
        )

    _ensure_requests_host_header_patch(hostname)
    port = parsed.port
    new_netloc = f"{ip}:{port}" if port and str(port) not in ("80", "443") else ip
    new_url = urlunparse(parsed._replace(netloc=new_netloc))
    logger.info("Tushare 代理: %s -> %s (Host: %s)", hostname, ip, hostname)
    return new_url


def _apply_proxy_to_pro(pro: Any, api_url: str | None, token_type: str) -> None:
    if api_url:
        configured = _configure_proxy_url(api_url)
        pro._DataApi__http_url = configured
        logger.info("Tushare 使用代理 API: %s (token_type=%s)", configured, token_type)
    else:
        logger.info("Tushare 使用官方 API (token_type=%s)", token_type)


def get_tushare_pro(token_type: str = "tushare") -> Any:
    """
    按 token_type 从 db_token 取有效 token，构造 ts.pro_api 并设置代理 URL。
    URL 优先级：db_token.api_url > 环境变量 TUSHARE_HTTP_URL
    """
    from mysql_config import load_db_token

    row = load_db_token(token_type)
    if not row:
        raise RuntimeError(
            f"db_token 中无有效记录: token_type={token_type!r}（status=1 且在有效期内）"
        )

    api_url = _normalize_api_url(row.get("api_url")) or _normalize_api_url(
        os.getenv("TUSHARE_HTTP_URL")
    )

    if token_type in _pro_cache:
        pro = _pro_cache[token_type]
        _apply_proxy_to_pro(pro, api_url, token_type)
        return pro

    import tushare as ts

    pro = ts.pro_api(row["token_id"])
    _apply_proxy_to_pro(pro, api_url, token_type)
    _pro_cache[token_type] = pro
    return pro


def clear_tushare_cache() -> None:
    global _host_header_patched, _proxy_virtual_host
    _pro_cache.clear()
    _host_ip_cache.clear()
    _host_header_patched = False
    _proxy_virtual_host = None
