"""大盘/板块年化波动率查询服务。"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from app.db import fetch_all_stock, fetch_one_stock
from app.dc_service import parse_trade_date

MARKET_TABLE = "dwm_market_volatility_di"
INDUSTRY_TABLE = "dwm_dc_industry_volatility_di"
ALLOWED_CONTENT_TYPES = ("行业", "概念")
DEFAULT_BOARD_NAMES = ["半导体", "通信", "创新药", "机器人"]
MARKET_INDEXES = (
    ("000001.SH", "上证综指"),
    ("000300.SH", "沪深300"),
)


def _serialize(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()[:10]
    if isinstance(value, Decimal):
        return float(value)
    return value


def _serialize_row(row: dict) -> dict:
    return {k: _serialize(v) for k, v in row.items()}


def latest_trade_date() -> str | None:
    row = fetch_one_stock(f"SELECT MAX(trade_date) AS d FROM {INDUSTRY_TABLE}")
    if row and row.get("d"):
        return _serialize(row["d"])
    row = fetch_one_stock(f"SELECT MAX(trade_date) AS d FROM {MARKET_TABLE}")
    return _serialize(row["d"]) if row and row.get("d") else None


def list_trade_dates(limit: int = 60) -> list[str]:
    limit = max(1, min(limit, 365))
    rows = fetch_all_stock(
        f"""
        SELECT DISTINCT trade_date AS d
        FROM {INDUSTRY_TABLE}
        ORDER BY d DESC
        LIMIT {limit}
        """
    )
    dates = [_serialize(r["d"]) for r in rows]
    if dates:
        return dates
    rows = fetch_all_stock(
        f"""
        SELECT DISTINCT trade_date AS d
        FROM {MARKET_TABLE}
        ORDER BY d DESC
        LIMIT {limit}
        """
    )
    return [_serialize(r["d"]) for r in rows]


def _resolve_trade_date(trade_date: str | None) -> str:
    td = parse_trade_date(trade_date) if trade_date else None
    if td:
        return td
    latest = latest_trade_date()
    if not latest:
        raise ValueError("暂无波动率数据，请先运行波动率批处理")
    return latest


def _vol_col(window: int) -> str:
    return "annual_vol_60d" if window == 60 else "annual_vol_20d"


def _parse_content_types(content_types: str | None) -> list[str]:
    if not content_types or not content_types.strip():
        return list(ALLOWED_CONTENT_TYPES)
    items = [x.strip() for x in content_types.split(",") if x.strip()]
    filtered = [x for x in items if x in ALLOWED_CONTENT_TYPES]
    return filtered or list(ALLOWED_CONTENT_TYPES)


def search_boards(
    trade_date: str | None = None,
    *,
    content_types: str | None = "行业,概念",
    keyword: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    td = _resolve_trade_date(trade_date)
    ctypes = _parse_content_types(content_types)
    limit = max(1, min(limit, 200))
    placeholders = ", ".join(f":ct{i}" for i in range(len(ctypes)))
    params: dict[str, Any] = {"td": td, **{f"ct{i}": ct for i, ct in enumerate(ctypes)}}
    kw_sql = ""
    if keyword and keyword.strip():
        kw_sql = " AND (industry_name LIKE :kw OR industry_code LIKE :kw)"
        params["kw"] = f"%{keyword.strip()}%"
    rows = fetch_all_stock(
        f"""
        SELECT DISTINCT industry_code, industry_name, content_type
        FROM {INDUSTRY_TABLE}
        WHERE trade_date = :td
          AND content_type IN ({placeholders})
          {kw_sql}
        ORDER BY industry_name
        LIMIT {limit}
        """,
        params,
    )
    return {
        "trade_date": td,
        "items": [_serialize_row(r) for r in rows],
    }


def resolve_boards_by_names(trade_date: str, names: list[str]) -> list[dict]:
    names = [n.strip() for n in names if n and n.strip()]
    if not names:
        return []
    seen: set[str] = set()
    resolved: list[dict] = []
    for name in names:
        rows = fetch_all_stock(
            f"""
            SELECT industry_code, industry_name, content_type
            FROM {INDUSTRY_TABLE}
            WHERE trade_date = :td
              AND content_type IN ('行业', '概念')
              AND (industry_name = :name OR industry_code = :name
                   OR industry_name LIKE :kw OR industry_code LIKE :kw)
            ORDER BY CASE WHEN industry_name = :name THEN 0 ELSE 1 END, industry_name
            LIMIT 5
            """,
            {"td": trade_date, "name": name, "kw": f"%{name}%"},
        )
        for row in rows:
            item = _serialize_row(row)
            code = item["industry_code"]
            if code in seen:
                continue
            resolved.append(item)
            seen.add(code)
            break
    return resolved


def get_market_history(
    trade_date: str | None = None,
    *,
    window: int = 20,
    days: int = 365,
) -> dict[str, Any]:
    td = _resolve_trade_date(trade_date)
    window = 60 if window == 60 else 20
    days = max(30, min(days, 365))
    col = _vol_col(window)
    rows = fetch_all_stock(
        f"""
        SELECT trade_date, index_code, index_name, close, pct_chg, {col} AS annual_vol
        FROM {MARKET_TABLE}
        WHERE trade_date <= :td
          AND index_code IN ('000001.SH', '000300.SH')
        ORDER BY trade_date DESC, index_code ASC
        LIMIT {days * len(MARKET_INDEXES)}
        """,
        {"td": td},
    )
    rows = list(reversed([_serialize_row(r) for r in rows]))
    dates = sorted({r["trade_date"] for r in rows})
    by_code: dict[str, dict[str, Any]] = {
        code: {"index_code": code, "index_name": name, "points": []}
        for code, name in MARKET_INDEXES
    }
    for row in rows:
        by_code.setdefault(
            row["index_code"],
            {"index_code": row["index_code"], "index_name": row.get("index_name"), "points": []},
        )["points"].append(row)
    for series in by_code.values():
        point_map = {p["trade_date"]: p for p in series["points"]}
        series["points"] = [
            point_map.get(
                d,
                {
                    "trade_date": d,
                    "annual_vol": None,
                    "close": None,
                    "pct_chg": None,
                },
            )
            for d in dates
        ]
    return {
        "trade_date": td,
        "window": window,
        "dates": dates,
        "series": [by_code[code] for code, _ in MARKET_INDEXES],
    }


def get_industry_history(
    trade_date: str | None = None,
    *,
    window: int = 20,
    content_types: str | None = "行业,概念",
    industry_codes: list[str] | None = None,
    board_keywords: list[str] | None = None,
    days: int = 365,
) -> dict[str, Any]:
    td = _resolve_trade_date(trade_date)
    window = 60 if window == 60 else 20
    days = max(30, min(days, 365))
    col = _vol_col(window)
    ctypes = _parse_content_types(content_types)
    boards: list[dict]
    if industry_codes:
        params = {"td": td, **{f"c{i}": c for i, c in enumerate(industry_codes)}}
        boards = [
            _serialize_row(r)
            for r in fetch_all_stock(
                f"""
                SELECT DISTINCT industry_code, industry_name, content_type
                FROM {INDUSTRY_TABLE}
                WHERE trade_date = :td
                  AND industry_code IN ({", ".join(f":c{i}" for i in range(len(industry_codes)))})
                ORDER BY industry_name
                """,
                params,
            )
        ]
    elif board_keywords:
        boards = resolve_boards_by_names(td, board_keywords)
    else:
        boards = resolve_boards_by_names(td, DEFAULT_BOARD_NAMES)
    boards = [b for b in boards if b.get("content_type") in ctypes]
    if not boards:
        return {
            "trade_date": td,
            "window": window,
            "dates": [],
            "boards": [],
            "series": [],
            "default_board_names": DEFAULT_BOARD_NAMES,
        }
    codes = [b["industry_code"] for b in boards]
    rows = fetch_all_stock(
        f"""
        SELECT trade_date, industry_code, industry_name, content_type, close, pct_change,
               {col} AS annual_vol
        FROM {INDUSTRY_TABLE}
        WHERE trade_date <= :td
          AND industry_code IN ({", ".join(f":c{i}" for i in range(len(codes)))})
        ORDER BY trade_date DESC, industry_name ASC
        LIMIT {days * len(codes)}
        """,
        {"td": td, **{f"c{i}": c for i, c in enumerate(codes)}},
    )
    rows = list(reversed([_serialize_row(r) for r in rows]))
    dates = sorted({r["trade_date"] for r in rows})
    by_code: dict[str, dict[str, Any]] = {
        b["industry_code"]: {
            "industry_code": b["industry_code"],
            "industry_name": b["industry_name"],
            "content_type": b.get("content_type"),
            "points": [],
        }
        for b in boards
    }
    for row in rows:
        if row["industry_code"] in by_code:
            by_code[row["industry_code"]]["points"].append(row)
    series = []
    for code in codes:
        item = by_code[code]
        point_map = {p["trade_date"]: p for p in item["points"]}
        item["points"] = [
            point_map.get(
                d,
                {"trade_date": d, "annual_vol": None, "close": None, "pct_change": None},
            )
            for d in dates
        ]
        series.append(item)
    return {
        "trade_date": td,
        "window": window,
        "dates": dates,
        "boards": boards,
        "series": series,
        "default_board_names": DEFAULT_BOARD_NAMES,
    }


def rank_industries(
    trade_date: str | None = None,
    *,
    window: int = 20,
    content_types: str | None = "行业,概念",
    top: int = 50,
) -> dict[str, Any]:
    td = _resolve_trade_date(trade_date)
    window = 60 if window == 60 else 20
    top = max(1, min(top, 200))
    col = _vol_col(window)
    ctypes = _parse_content_types(content_types)
    params = {"td": td, **{f"ct{i}": ct for i, ct in enumerate(ctypes)}}
    rows = fetch_all_stock(
        f"""
        SELECT trade_date, industry_code, industry_name, content_type, close, pct_change,
               annual_vol_20d, annual_vol_60d, {col} AS annual_vol
        FROM {INDUSTRY_TABLE}
        WHERE trade_date = :td
          AND content_type IN ({", ".join(f":ct{i}" for i in range(len(ctypes)))})
        ORDER BY {col} DESC, industry_name ASC
        LIMIT {top}
        """,
        params,
    )
    return {
        "trade_date": td,
        "window": window,
        "items": [_serialize_row(r) for r in rows],
    }
