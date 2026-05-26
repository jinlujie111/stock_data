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


def _normalize_api_url(url: str | None) -> str | None:
    if not url or not str(url).strip():
        return None
    u = str(url).strip()
    if not u.endswith("/"):
        u += "/"
    return u


def _maybe_force_ipv4_url(url: str) -> str:
    """
    阿里云 ECS 常见：DNS 优先解析 IPv6，VPC 无 IPv6 路由 → Network is unreachable。
    设置 TUSHARE_FORCE_IPV4=1 时将域名替换为 IPv4 地址。
    """
    if os.getenv("TUSHARE_FORCE_IPV4", "").lower() not in ("1", "true", "yes"):
        return url
    parsed = urlparse(url)
    host = parsed.hostname
    if not host or host.replace(".", "").isdigit():
        return url
    try:
        infos = socket.getaddrinfo(host, None, socket.AF_INET, socket.SOCK_STREAM)
        ipv4 = infos[0][4][0]
    except OSError as exc:
        logger.warning("TUSHARE_FORCE_IPV4: 无法解析 %s 的 IPv4: %s", host, exc)
        return url
    new_netloc = parsed.netloc.replace(host, ipv4, 1)
    forced = urlunparse(parsed._replace(netloc=new_netloc))
    logger.info("Tushare 代理强制 IPv4: %s -> %s", host, ipv4)
    return forced


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
        api_url = _maybe_force_ipv4_url(api_url)
        pro._DataApi__http_url = api_url
        logger.info("Tushare 使用代理 API: %s (token_type=%s)", api_url, token_type)
    else:
        logger.info("Tushare 使用官方 API (token_type=%s)", token_type)

    _pro_cache[token_type] = pro
    return pro


def clear_tushare_cache() -> None:
    _pro_cache.clear()
