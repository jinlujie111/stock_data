"""用户板块/股票自选（data_industry 库）。"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from app.db import execute, fetch_all, fetch_all_stock, fetch_one

BOARD_TABLE = "app_user_board_favorite"
STOCK_TABLE = "app_user_stock_favorite"


def _serialize(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()[:10]
    if isinstance(value, Decimal):
        return float(value)
    return value


def _serialize_row(row: dict) -> dict:
    return {k: _serialize(v) for k, v in row.items()}


def list_board_favorites(user_id: int, trade_date: str | None = None) -> list[dict]:
    rows = fetch_all(
        f"""
        SELECT id, industry_code, industry_name, content_type, created_at
        FROM {BOARD_TABLE}
        WHERE user_id = :uid
        ORDER BY created_at DESC
        """,
        {"uid": user_id},
    )
    if not rows or not trade_date:
        return [_serialize_row(r) for r in rows]

    codes = [r["industry_code"] for r in rows]
    placeholders = ", ".join(f":c{i}" for i in range(len(codes)))
    params = {"td": trade_date, **{f"c{i}": c for i, c in enumerate(codes)}}
    quotes = fetch_all_stock(
        f"""
        SELECT industry_code, industry_name, content_type, pct_change, net_amount
        FROM dwm_dc_industry_fund_flow_di
        WHERE trade_date = :td AND industry_code IN ({placeholders})
        """,
        params,
    )
    qmap = {r["industry_code"]: _serialize_row(r) for r in quotes}
    out = []
    for r in rows:
        item = _serialize_row(r)
        q = qmap.get(r["industry_code"], {})
        item["pct_change"] = q.get("pct_change")
        net = q.get("net_amount")
        item["net_amount_yi"] = round(float(net) / 1e8, 2) if net is not None else None
        if q.get("industry_name"):
            item["industry_name"] = q["industry_name"]
        if q.get("content_type"):
            item["content_type"] = q["content_type"]
        out.append(item)
    return out


def add_board_favorite(
    user_id: int,
    industry_code: str,
    industry_name: str | None = None,
    content_type: str | None = None,
) -> dict:
    if not industry_code or not industry_code.strip():
        raise ValueError("industry_code 必填")
    code = industry_code.strip()
    execute(
        f"""
        INSERT INTO {BOARD_TABLE} (user_id, industry_code, industry_name, content_type)
        VALUES (:uid, :ic, :name, :ct)
        ON DUPLICATE KEY UPDATE
            industry_name = COALESCE(VALUES(industry_name), industry_name),
            content_type = COALESCE(VALUES(content_type), content_type)
        """,
        {
            "uid": user_id,
            "ic": code,
            "name": industry_name,
            "ct": content_type,
        },
    )
    row = fetch_one(
        f"SELECT * FROM {BOARD_TABLE} WHERE user_id = :uid AND industry_code = :ic",
        {"uid": user_id, "ic": code},
    )
    return _serialize_row(row) if row else {"industry_code": code}


def remove_board_favorite(user_id: int, industry_code: str) -> bool:
    n = execute(
        f"DELETE FROM {BOARD_TABLE} WHERE user_id = :uid AND industry_code = :ic",
        {"uid": user_id, "ic": industry_code.strip()},
    )
    return n > 0


def list_stock_favorites(user_id: int, trade_date: str | None = None) -> list[dict]:
    rows = fetch_all(
        f"""
        SELECT id, ts_code, stock_name, created_at
        FROM {STOCK_TABLE}
        WHERE user_id = :uid
        ORDER BY created_at DESC
        """,
        {"uid": user_id},
    )
    if not rows or not trade_date:
        return [_serialize_row(r) for r in rows]

    codes = [r["ts_code"] for r in rows]
    placeholders = ", ".join(f":c{i}" for i in range(len(codes)))
    params = {"td": trade_date, **{f"c{i}": c for i, c in enumerate(codes)}}
    quotes = fetch_all_stock(
        f"""
        SELECT ts_code, pct_chg, close, amount
        FROM ods_stock_detail_di
        WHERE trade_date = :td AND ts_code IN ({placeholders})
        """,
        params,
    )
    qmap = {r["ts_code"]: _serialize_row(r) for r in quotes}
    out = []
    for r in rows:
        item = _serialize_row(r)
        q = qmap.get(r["ts_code"], {})
        item["pct_chg"] = q.get("pct_chg")
        item["close"] = q.get("close")
        out.append(item)
    return out


def add_stock_favorite(user_id: int, ts_code: str, stock_name: str | None = None) -> dict:
    if not ts_code or not ts_code.strip():
        raise ValueError("ts_code 必填")
    code = ts_code.strip()
    execute(
        f"""
        INSERT INTO {STOCK_TABLE} (user_id, ts_code, stock_name)
        VALUES (:uid, :tc, :name)
        ON DUPLICATE KEY UPDATE stock_name = COALESCE(VALUES(stock_name), stock_name)
        """,
        {"uid": user_id, "tc": code, "name": stock_name},
    )
    row = fetch_one(
        f"SELECT * FROM {STOCK_TABLE} WHERE user_id = :uid AND ts_code = :tc",
        {"uid": user_id, "tc": code},
    )
    return _serialize_row(row) if row else {"ts_code": code}


def remove_stock_favorite(user_id: int, ts_code: str) -> bool:
    n = execute(
        f"DELETE FROM {STOCK_TABLE} WHERE user_id = :uid AND ts_code = :tc",
        {"uid": user_id, "tc": ts_code.strip()},
    )
    return n > 0
