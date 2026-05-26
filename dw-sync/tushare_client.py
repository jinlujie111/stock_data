#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""从 db_token 加载 Tushare Pro 客户端（token + 代理 API URL）。"""
from __future__ import annotations

import logging
import os
import socket
from typing import Any

logger = logging.getLogger(__name__)

_pro_cache: dict[str, Any] = {}
_ipv4_patched = False


def _normalize_api_url(url: str | None) -> str | None:
    if not url or not str(url).strip():
        return None
    u = str(url).strip()
    if not u.endswith("/"):
        u += "/"
    return u


def _ensure_ipv4_requests() -> None:
    """
    阿里云 ECS：优先 IPv6 且无路由时会 Network unreachable。
    仅让 requests/urllib3 解析 A 记录，**不把 URL 换成 IP**（Cloudflare 代理需保留 Host 头）。
    """
    global _ipv4_patched
    if _ipv4_patched:
        return
    if os.getenv("TUSHARE_FORCE_IPV4", "").lower() not in ("1", "true", "yes"):
        return
    try:
        import urllib3.util.connection as urllib3_connection

        urllib3_connection.allowed_gai_family = lambda: socket.AF_INET
        _ipv4_patched = True
        logger.info(
            "Tushare 请求强制 IPv4（保留代理域名，避免 Cloudflare 因无 Host 返回空数据）"
        )
    except Exception as exc:
        logger.warning("Tushare 强制 IPv4 补丁未生效: %s", exc)


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

    _ensure_ipv4_requests()

    import tushare as ts

    token_id = row["token_id"]
    pro = ts.pro_api(token_id)

    api_url = _normalize_api_url(row.get("api_url")) or _normalize_api_url(
        os.getenv("TUSHARE_HTTP_URL")
    )
    if api_url:
        pro._DataApi__http_url = api_url
        logger.info("Tushare 使用代理 API: %s (token_type=%s)", api_url, token_type)
    else:
        logger.info("Tushare 使用官方 API (token_type=%s)", token_type)

    _pro_cache[token_type] = pro
    return pro


def clear_tushare_cache() -> None:
    _pro_cache.clear()
