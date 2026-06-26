#!/usr/bin/env python3
"""需求3 量化主线 — API 验收（需 Web 已启动且带 Cookie）。"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from etl.quant_mainline.db_util import parse_trade_date

DEFAULT_BASE = "http://127.0.0.1:8082/api/v1/quant-mainline"
TOP_TYPES = ("行业", "概念")
DEFAULT_TOP = 10


def _fetch(base: str, path: str, cookie: str) -> tuple[int, dict]:
    url = f"{base.rstrip('/')}{path}"
    req = urllib.request.Request(url)
    if cookie:
        req.add_header("Cookie", cookie)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = resp.read().decode("utf-8")
            return resp.status, json.loads(body) if body else {}
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        try:
            data = json.loads(body) if body else {}
        except json.JSONDecodeError:
            data = {"detail": body}
        return e.code, data


def _check_top_groups(data: dict, top: int) -> list[str]:
    issues: list[str] = []
    groups = data.get("groups") or []
    got_types = {g.get("content_type") for g in groups}
    for ct in TOP_TYPES:
        if ct not in got_types:
            issues.append(f"top-groups 缺少分组: {ct}")
    for g in groups:
        ct = g.get("content_type")
        items = g.get("items") or []
        if len(items) > top:
            issues.append(f"{ct} 返回超过 Top{top}: {len(items)}")
        ranks = [it.get("rank_no") for it in items]
        if ranks != list(range(1, len(ranks) + 1)):
            issues.append(f"{ct} rank_no 不连续: {ranks}")
        for it in items:
            if it.get("content_type") != ct:
                issues.append(f"{ct} 分组内 content_type 不一致: {it.get('content_type')}")
            if not (it.get("is_topn") or it.get("is_top3")):
                issues.append(f"{ct} #{it.get('rank_no')} 未标记 is_topn")
    return issues


def _check_top_single(data: dict, content_type: str, top: int) -> list[str]:
    issues: list[str] = []
    if data.get("content_type") != content_type:
        issues.append(f"top 响应 content_type 期望 {content_type} 实际 {data.get('content_type')}")
    items = data.get("items") or []
    if len(items) > top:
        issues.append(f"top 返回超过 {top} 条")
    for it in items:
        if it.get("content_type") != content_type:
            issues.append(f"top 单类型接口含其他类型: {it.get('content_type')}")
    return issues


def run_api_tests(base: str, trade_date: str, cookie: str, top: int) -> list[str]:
    issues: list[str] = []
    td = parse_trade_date(trade_date)
    td_s = td.isoformat()

    code, data = _fetch(base, "/trade-dates?limit=5", cookie)
    if code != 200:
        issues.append(f"trade-dates HTTP {code}: {data.get('detail')}")
    elif not data.get("dates"):
        issues.append("trade-dates 无 dates")

    q_groups = urllib.parse.urlencode(
        {"trade_date": trade_date, "content_types": "行业,概念", "top": str(top), "top_only": "true"}
    )
    code, data = _fetch(base, f"/top-groups?{q_groups}", cookie)
    if code != 200:
        issues.append(f"top-groups HTTP {code}: {data.get('detail')}")
    else:
        if data.get("trade_date") != td_s:
            issues.append(f"top-groups trade_date 期望 {td_s} 实际 {data.get('trade_date')}")
        issues.extend(_check_top_groups(data, top))

    for ct in TOP_TYPES:
        q = urllib.parse.urlencode(
            {"trade_date": trade_date, "content_types": ct, "top": str(top), "top_only": "true"}
        )
        code, data = _fetch(base, f"/top?{q}", cookie)
        if code != 200:
            issues.append(f"top/{ct} HTTP {code}: {data.get('detail')}")
        else:
            issues.extend(_check_top_single(data, ct, top))

    q_sig = urllib.parse.urlencode(
        {"trade_date": trade_date, "content_types": "行业,概念", "limit": "50"}
    )
    code, data = _fetch(base, f"/signals?{q_sig}", cookie)
    if code != 200:
        issues.append(f"signals HTTP {code}: {data.get('detail')}")
    elif not isinstance(data.get("items"), list):
        issues.append("signals 无 items 列表")

    code, data = _fetch(base, "/config", cookie)
    if code != 200:
        issues.append(f"config HTTP {code}: {data.get('detail')}")
    elif "概念" not in str(data.get("content_types", "")):
        issues.append(f"config content_types 未含概念: {data.get('content_types')}")

    return issues


def main() -> int:
    parser = argparse.ArgumentParser(description="需求3 量化主线 API 测试")
    parser.add_argument("trade_date", help="YYYYMMDD")
    parser.add_argument("--base", default=os.getenv("QM_API_BASE", DEFAULT_BASE))
    parser.add_argument("--top", type=int, default=DEFAULT_TOP)
    parser.add_argument(
        "--cookie",
        default=os.getenv("IFF_TOKEN_COOKIE", ""),
        help="完整 Cookie，如 iff_token=xxx",
    )
    args = parser.parse_args()

    if not args.cookie:
        print("WARN: 未设置 IFF_TOKEN_COOKIE / --cookie，API 可能返回 401")

    print(f"=== API 测试 base={args.base} trade_date={args.trade_date} ===\n")
    issues = run_api_tests(args.base, args.trade_date, args.cookie, args.top)
    if issues:
        print("FAIL:")
        for i in issues:
            print(f"  - {i}")
        return 1
    print("PASS: API 验收通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
