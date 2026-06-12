"""东财 DWM 查询服务（读 stock_data 库）。"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from app.dc_registry import CONTENT_TYPES, get_dimension
from app.db import fetch_all_stock, fetch_one_stock

_MAX_ROWS = 500


def parse_trade_date(raw: str | None) -> str | None:
    if not raw:
        return None
    s = raw.strip().replace("-", "")
    if len(s) != 8 or not s.isdigit():
        raise ValueError("trade_date 格式应为 YYYY-MM-DD 或 YYYYMMDD")
    return f"{s[0:4]}-{s[4:6]}-{s[6:8]}"


def parse_csv_list(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [p.strip() for p in raw.split(",") if p.strip()]


def _serialize(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()[:10]
    if isinstance(value, Decimal):
        return float(value)
    return value


def _serialize_row(row: dict) -> dict:
    return {k: _serialize(v) for k, v in row.items()}


def _in_clause(field: str, values: list[str], prefix: str) -> tuple[str, dict]:
    params: dict = {}
    parts = []
    for i, val in enumerate(values):
        key = f"{prefix}{i}"
        parts.append(f":{key}")
        params[key] = val
    return f" AND {field} IN ({', '.join(parts)})", params


def latest_trade_date(slug: str) -> str | None:
    dim = get_dimension(slug)
    row = fetch_one_stock(
        f"SELECT MAX(trade_date) AS d FROM {dim['table']}"
    )
    if not row or not row.get("d"):
        return None
    return _serialize(row["d"])


def list_trade_dates(slug: str, limit: int = 60) -> list[str]:
    dim = get_dimension(slug)
    limit = max(1, min(limit, 365))
    rows = fetch_all_stock(
        f"""
        SELECT DISTINCT trade_date AS d
        FROM {dim['table']}
        ORDER BY trade_date DESC
        LIMIT {limit}
        """
    )
    return [_serialize(r["d"]) for r in rows]


def list_boards(
    slug: str,
    trade_date: str,
    content_types: list[str] | None = None,
) -> list[dict]:
    dim = get_dimension(slug)
    sql = f"""
        SELECT industry_code, industry_name, content_type
        FROM {dim['table']}
        WHERE trade_date = :trade_date
    """
    params: dict = {"trade_date": trade_date}
    if content_types:
        clause, extra = _in_clause("content_type", content_types, "ct")
        sql += clause
        params.update(extra)
    sql += " ORDER BY content_type, industry_name"
    rows = fetch_all_stock(sql, params)
    return [_serialize_row(r) for r in rows]


def query_dimension(
    slug: str,
    trade_date: str,
    content_types: list[str] | None = None,
    industry_codes: list[str] | None = None,
) -> dict:
    dim = get_dimension(slug)
    col_keys = [c["key"] for c in dim["columns"]]
    col_sql = ", ".join(col_keys)
    sql = f"""
        SELECT {col_sql}
        FROM {dim['table']}
        WHERE trade_date = :trade_date
    """
    params: dict = {"trade_date": trade_date}
    if content_types:
        valid = [ct for ct in content_types if ct in CONTENT_TYPES]
        if valid:
            clause, extra = _in_clause("content_type", valid, "ct")
            sql += clause
            params.update(extra)
    if industry_codes:
        clause, extra = _in_clause("industry_code", industry_codes, "ic")
        sql += clause
        params.update(extra)
    sql += f" ORDER BY {dim['order_by']} LIMIT {_MAX_ROWS}"
    rows = fetch_all_stock(sql, params)
    return {
        "slug": slug,
        "trade_date": trade_date,
        "total": len(rows),
        "columns": dim["columns"],
        "items": [_serialize_row(r) for r in rows],
    }
