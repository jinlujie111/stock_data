"""资金强度：近30日趋势与板块解析。"""
from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from app.db import fetch_all_stock, fetch_one_stock
from app.dc_registry import CONTENT_TYPES
from app.dc_service import parse_trade_date

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
    return [p.strip() for p in re.split(r"[,，]", raw) if p.strip()]


def _resolve_trade_date(trade_date: str | None) -> str | None:
    td = parse_trade_date(trade_date) if trade_date else None
    if not td:
        row = fetch_one_stock(f"SELECT MAX(trade_date) AS d FROM {TABLE}")
        td = _serialize(row["d"]) if row and row.get("d") else None
    return td


def _content_type_clause(content_types: list[str] | None) -> tuple[str, dict]:
    if not content_types:
        return "", {}
    valid = [ct for ct in content_types if ct in CONTENT_TYPES]
    if not valid:
        return "", {}
    params = {f"ct{i}": ct for i, ct in enumerate(valid)}
    placeholders = ", ".join(f":ct{i}" for i in range(len(valid)))
    return f" AND content_type IN ({placeholders})", params


def _net_amount_expr() -> str:
    return "COALESCE(net_amount, net_amount_wan * 10000)"


def _board_flow_row(row: dict) -> dict:
    item = _serialize_row(row)
    net = item.get("net_amount")
    if net is None and item.get("net_amount_wan") is not None:
        net = float(item["net_amount_wan"]) * 10000
    yi = round(float(net) / 1e8, 2) if net is not None else None
    return {
        "industry_code": item.get("industry_code"),
        "industry_name": item.get("industry_name"),
        "content_type": item.get("content_type"),
        "pct_change": item.get("pct_change"),
        "net_amount_yi": yi,
        "net_amount_yi_abs": round(abs(yi), 2) if yi is not None else None,
    }


def get_board_flow_top5(
    trade_date: str | None = None,
    content_types: list[str] | None = None,
) -> dict:
    td = _resolve_trade_date(trade_date)
    if not td:
        return {"trade_date": None, "inflow": [], "outflow": []}

    ct_sql, ct_params = _content_type_clause(content_types)
    base_params = {"trade_date": td, **ct_params}
    net_expr = _net_amount_expr()

    def _query_top5(order: str) -> list[dict]:
        return fetch_all_stock(
            f"""
            SELECT industry_code, industry_name, content_type, pct_change,
                   net_amount, net_amount_wan
            FROM {TABLE}
            WHERE trade_date = :trade_date
              AND ({net_expr}) IS NOT NULL
              {ct_sql}
            ORDER BY {net_expr} {order}
            LIMIT 5
            """,
            base_params,
        )

    inflow_rows = _query_top5("DESC")
    outflow_rows = _query_top5("ASC")

    if not inflow_rows and not outflow_rows and trade_date:
        td = _resolve_trade_date(None)
        if td and td != base_params["trade_date"]:
            base_params["trade_date"] = td
            inflow_rows = _query_top5("DESC")
            outflow_rows = _query_top5("ASC")

    return {
        "trade_date": base_params["trade_date"],
        "inflow": [_board_flow_row(r) for r in inflow_rows],
        "outflow": [_board_flow_row(r) for r in outflow_rows],
    }


def _stock_flow_row(row: dict) -> dict:
    item = _serialize_row(row)
    net_wan = item.get("net_mf_amount")
    amount_qian = item.get("amount")
    total_qian = item.get("total_amount")
    net_yi = round(float(net_wan) / 10000, 2) if net_wan is not None else None
    amount_yi = round(float(amount_qian) / 100000, 2) if amount_qian is not None else None
    ratio = None
    if amount_qian is not None and total_qian:
        ratio = round(float(amount_qian) / float(total_qian) * 100, 2)
    return {
        "ts_code": item.get("ts_code"),
        "stock_name": item.get("stock_name") or item.get("ts_code"),
        "net_mf_yi": net_yi,
        "net_mf_yi_abs": round(abs(net_yi), 2) if net_yi is not None else None,
        "pct_chg": item.get("pct_chg"),
        "amount_yi": amount_yi,
        "amount_ratio": ratio,
    }


def _resolve_stock_trade_date(trade_date: str | None) -> str | None:
    td = parse_trade_date(trade_date) if trade_date else None
    if td:
        row = fetch_one_stock(
            """
            SELECT COUNT(*) AS cnt
            FROM ods_stock_fund_flow_di
            WHERE trade_date = :trade_date
            """,
            {"trade_date": td},
        )
        if row and int(row.get("cnt") or 0) > 0:
            return td
    row = fetch_one_stock("SELECT MAX(trade_date) AS d FROM ods_stock_fund_flow_di")
    return _serialize(row["d"]) if row and row.get("d") else td


def get_stock_flow_top10(
    trade_date: str | None = None,
    direction: str = "in",
) -> dict:
    td = _resolve_stock_trade_date(trade_date)
    if not td:
        return {"trade_date": None, "direction": direction, "items": []}

    direction = (direction or "in").strip().lower()
    if direction not in ("in", "out"):
        raise ValueError("direction 应为 in 或 out")
    order = "DESC" if direction == "in" else "ASC"

    rows = fetch_all_stock(
        f"""
        SELECT
            f.ts_code,
            COALESCE(ll.name, tmn.name, f.ts_code) AS stock_name,
            f.net_mf_amount,
            d.pct_chg,
            d.amount,
            (
                SELECT SUM(amount)
                FROM ods_stock_detail_di
                WHERE trade_date = :trade_date
                  AND (
                    ts_code LIKE '%.SH'
                    OR ts_code LIKE '%.SZ'
                    OR ts_code LIKE '%.BJ'
                  )
            ) AS total_amount
        FROM ods_stock_fund_flow_di f
        INNER JOIN ods_stock_detail_di d
            ON f.trade_date = d.trade_date AND f.ts_code = d.ts_code
        LEFT JOIN (
            SELECT ts_code, MAX(name) AS name
            FROM ods_limit_list_di
            WHERE trade_date = :trade_date
            GROUP BY ts_code
        ) ll ON ll.ts_code = f.ts_code
        LEFT JOIN (
            SELECT con_code, MAX(name) AS name
            FROM ods_ths_member_di
            GROUP BY con_code
        ) tmn ON tmn.con_code = f.ts_code
        WHERE f.trade_date = :trade_date
          AND f.net_mf_amount IS NOT NULL
          AND (
            f.ts_code LIKE '%.SH'
            OR f.ts_code LIKE '%.SZ'
            OR f.ts_code LIKE '%.BJ'
          )
        ORDER BY f.net_mf_amount {order}
        LIMIT 10
        """,
        {"trade_date": td},
    )
    return {
        "trade_date": td,
        "direction": direction,
        "items": [_stock_flow_row(r) for r in rows],
    }
