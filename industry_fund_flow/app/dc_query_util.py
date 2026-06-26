"""东财板块 Web 查询公共服务（序列化、交易日解析）。"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from app.db import fetch_all_stock, fetch_one_stock
from app.dc_service import parse_trade_date


def serialize_value(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()[:10]
    if isinstance(value, Decimal):
        return float(value)
    return value


def serialize_row(row: dict, *, keep_detail_json_str: bool = False) -> dict:
    out: dict[str, Any] = {}
    for k, v in row.items():
        if keep_detail_json_str and k == "detail_json" and isinstance(v, str):
            out[k] = v
            continue
        out[k] = serialize_value(v)
    return out


def latest_trade_date_from_table(
    table: str,
    *,
    fallback_table: str | None = None,
) -> str | None:
    row = fetch_one_stock(f"SELECT MAX(trade_date) AS d FROM {table}")
    if row and row.get("d"):
        return serialize_value(row["d"])
    if fallback_table:
        row = fetch_one_stock(f"SELECT MAX(trade_date) AS d FROM {fallback_table}")
        if row and row.get("d"):
            return serialize_value(row["d"])
    return None


def list_trade_dates_from_table(table: str, limit: int = 60) -> list[str]:
    limit = max(1, min(limit, 365))
    rows = fetch_all_stock(
        f"""
        SELECT DISTINCT trade_date AS d
        FROM {table}
        ORDER BY trade_date DESC
        LIMIT {limit}
        """
    )
    return [serialize_value(r["d"]) for r in rows]


def resolve_trade_date(
    trade_date: str | None,
    *,
    table: str,
    fallback_table: str | None = None,
    empty_msg: str,
) -> str:
    td = parse_trade_date(trade_date) if trade_date else None
    if td:
        return td
    latest = latest_trade_date_from_table(table, fallback_table=fallback_table)
    if not latest:
        raise ValueError(empty_msg)
    return latest
