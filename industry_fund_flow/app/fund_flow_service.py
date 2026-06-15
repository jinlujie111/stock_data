"""资金强度：近30日趋势与板块解析。"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from app.db import fetch_all_stock, fetch_one_stock
from app.dc_service import parse_csv_list, parse_trade_date

TABLE = "dwm_dc_industry_fund_flow_di"

DEFAULT_CHART_BOARDS = ["半导体", "通信", "有色", "化工", "创新药", "机器人"]


def _serialize(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()[:10]
    if isinstance(value, Decimal):
        return float(value)
    return value


def _serialize_row(row: dict) -> dict:
    return {k: _serialize(v) for k, v in row.items()}


def _trading_dates_up_to(end_date: str, limit: int = 30) -> list[str]:
    limit = max(1, min(limit, 120))
    rows = fetch_all_stock(
        f"""
        SELECT DISTINCT trade_date AS d
        FROM {TABLE}
        WHERE trade_date <= :end_date
        ORDER BY trade_date DESC
        LIMIT {limit}
        """,
        {"end_date": end_date},
    )
    return sorted(_serialize(r["d"]) for r in rows)


def resolve_boards_by_names(trade_date: str, names: list[str]) -> list[dict]:
    resolved: list[dict] = []
    seen: set[str] = set()
    for name in names:
        name = name.strip()
        if not name:
            continue
        row = fetch_one_stock(
            f"""
            SELECT industry_code, industry_name, content_type
            FROM {TABLE}
            WHERE trade_date = :trade_date
              AND industry_name LIKE :kw
            ORDER BY
              CASE WHEN industry_name = :exact THEN 0 ELSE 1 END,
              CHAR_LENGTH(industry_name) ASC
            LIMIT 1
            """,
            {"trade_date": trade_date, "kw": f"%{name}%", "exact": name},
        )
        if row and row["industry_code"] not in seen:
            item = _serialize_row(row)
            resolved.append(item)
            seen.add(item["industry_code"])
    return resolved


def get_fund_flow_trends(
    end_date: str | None = None,
    industry_codes: list[str] | None = None,
    board_keywords: list[str] | None = None,
    days: int = 30,
) -> dict:
    td = parse_trade_date(end_date) if end_date else None
    if not td:
        row = fetch_one_stock(f"SELECT MAX(trade_date) AS d FROM {TABLE}")
        td = _serialize(row["d"]) if row and row.get("d") else None
    if not td:
        return {
            "end_date": None,
            "dates": [],
            "boards": [],
            "series": [],
            "default_board_names": DEFAULT_CHART_BOARDS,
        }

    if industry_codes:
        boards = [
            _serialize_row(r)
            for r in fetch_all_stock(
                f"""
                SELECT DISTINCT industry_code, industry_name, content_type
                FROM {TABLE}
                WHERE trade_date = :trade_date
                  AND industry_code IN ({", ".join(f":c{i}" for i in range(len(industry_codes)))})
                """,
                {"trade_date": td, **{f"c{i}": c for i, c in enumerate(industry_codes)}},
            )
        ]
    elif board_keywords:
        boards = resolve_boards_by_names(td, board_keywords)
    else:
        boards = resolve_boards_by_names(td, DEFAULT_CHART_BOARDS)

    if not boards:
        return {
            "end_date": td,
            "dates": [],
            "boards": [],
            "series": [],
            "default_board_names": DEFAULT_CHART_BOARDS,
        }

    dates = _trading_dates_up_to(td, days)
    if not dates:
        return {
            "end_date": td,
            "dates": [],
            "boards": boards,
            "series": [],
            "default_board_names": DEFAULT_CHART_BOARDS,
        }

    codes = [b["industry_code"] for b in boards]
    code_params = {f"ic{i}": c for i, c in enumerate(codes)}
    date_params = {f"d{i}": d for i, d in enumerate(dates)}
    in_codes = ", ".join(f":ic{i}" for i in range(len(codes)))
    in_dates = ", ".join(f":d{i}" for i in range(len(dates)))

    rows = fetch_all_stock(
        f"""
        SELECT trade_date, industry_code, industry_name,
               net_amount_wan, net_amount_rate, dc_rank
        FROM {TABLE}
        WHERE industry_code IN ({in_codes})
          AND trade_date IN ({in_dates})
        ORDER BY trade_date ASC, industry_name ASC
        """,
        {**code_params, **date_params},
    )

    by_code: dict[str, dict] = {
        b["industry_code"]: {
            "industry_code": b["industry_code"],
            "industry_name": b["industry_name"],
            "content_type": b.get("content_type"),
            "points": [],
        }
        for b in boards
    }
    for row in rows:
        item = _serialize_row(row)
        code = item["industry_code"]
        if code not in by_code:
            continue
        wan = item.get("net_amount_wan")
        by_code[code]["points"].append(
            {
                "trade_date": item["trade_date"],
                "net_amount_yi": round(float(wan) / 10000, 4) if wan is not None else None,
                "net_amount_rate": item.get("net_amount_rate"),
                "dc_rank": item.get("dc_rank"),
            }
        )

    series = []
    for code in codes:
        s = by_code[code]
        point_map = {p["trade_date"]: p for p in s["points"]}
        s["points"] = [
            point_map.get(
                d,
                {
                    "trade_date": d,
                    "net_amount_yi": None,
                    "net_amount_rate": None,
                    "dc_rank": None,
                },
            )
            for d in dates
        ]
        series.append(s)

    return {
        "end_date": td,
        "dates": dates,
        "boards": boards,
        "series": series,
        "default_board_names": DEFAULT_CHART_BOARDS,
    }


def parse_board_keywords(raw: str | None) -> list[str] | None:
    if not raw:
        return None
    return [p.strip() for p in raw.split(",") if p.strip()]
