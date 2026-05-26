#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""从 db_token 加载 Tushare Pro 客户端（token + 代理 API URL）。"""
from __future__ import annotations

import logging
import os
import socket
from typing import Any
from urllib.parse import urlparse, urlunparse

logger = logging.getLogger(__name__)

_pro_cache: dict[str, Any] = {}
_host_header_patched = False
_proxy_virtual_host: str | None = None


def _normalize_api_url(url: str | None) -> str | None:
    if not url or not str(url).strip():
        return None
    u = str(url).strip()
    if not u.endswith("/"):
        u += "/"
    return u


def _resolve_host_to_ipv4(hostname: str) -> str | None:
    """解析代理域名为 IPv4；失败时用环境变量 TUSHARE_API_FALLBACK_IP。"""
    if not hostname or hostname.replace(".", "").isdigit():
        return hostname

    for family in (socket.AF_INET, socket.AF_INET6):
        try:
            infos = socket.getaddrinfo(hostname, None, family, socket.SOCK_STREAM)
        except OSError as exc:
            logger.debug("getaddrinfo %s family=%s: %s", hostname, family, exc)
            continue
        for info in infos:
            addr = info[4][0]
            if addr.startswith("::ffff:"):
                return addr.split("::ffff:")[-1]
            if family == socket.AF_INET:
                return addr

    fallback = (os.getenv("TUSHARE_API_FALLBACK_IP") or "").strip()
    if fallback:
        logger.warning(
            "域名 %s DNS 解析失败，使用 TUSHARE_API_FALLBACK_IP=%s",
            hostname,
            fallback,
        )
        return fallback
    return None


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
    阿里云 ECS：纯 IPv4 DNS 常失败；解析为 IP 并保留 Host 头访问 Cloudflare。
    设置 TUSHARE_PROXY_USE_DOMAIN=1 可强制不替换为 IP（仅用域名）。
    """
    if os.getenv("TUSHARE_PROXY_USE_DOMAIN", "").lower() in ("1", "true", "yes"):
        return api_url

    parsed = urlparse(api_url)
    hostname = parsed.hostname
    if not hostname:
        return api_url

    ip = _resolve_host_to_ipv4(hostname)
    if not ip or ip == hostname:
        return api_url

    _ensure_requests_host_header_patch(hostname)
    port = parsed.port
    if port and str(port) not in ("80", "443"):
        new_netloc = f"{ip}:{port}"
    else:
        new_netloc = ip
    new_url = urlunparse(parsed._replace(netloc=new_netloc))
    logger.info("Tushare 代理连接: %s -> %s (Host: %s)", hostname, ip, hostname)
    return new_url


def get_tushare_pro(token_type: str = "tushare") -> Any:
    """
    按 token_type 从 db_token 取有效 token，构造 ts.pro_api 并设置代理 URL。
    URL 优先级：db_token.api_url > 环境变量 TUSHARE_HTTP_URL
    """
    if token_type in _pro_cache:
        return _pro_cache[token_type]

    from mysql_config import load_db_token

    row = load_db_token(token_type)
    if not row:
        raise RuntimeError(
            f"db_token 中无有效记录: token_type={token_type!r}（status=1 且在有效期内）"
        )

    import tushare as ts

    token_id = row["token_id"]
    pro = ts.pro_api(token_id)

    api_url = _normalize_api_url(row.get("api_url")) or _normalize_api_url(
        os.getenv("TUSHARE_HTTP_URL")
    )
    if api_url:
        api_url = _configure_proxy_url(api_url)
        pro._DataApi__http_url = api_url
        logger.info("Tushare 使用代理 API: %s (token_type=%s)", api_url, token_type)
    else:
        logger.info("Tushare 使用官方 API (token_type=%s)", token_type)

    _pro_cache[token_type] = pro
    return pro


def clear_tushare_cache() -> None:
    global _host_header_patched, _proxy_virtual_host
    _pro_cache.clear()
    _host_header_patched = False
    _proxy_virtual_host = None
