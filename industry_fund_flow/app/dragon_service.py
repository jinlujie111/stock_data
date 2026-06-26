"""板块龙头：查询服务。"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from app.db import fetch_all_stock, fetch_one_stock
from app.dc_service import parse_csv_list, parse_trade_date

SCORE_TABLE = "dwm_sector_stock_dragon_score_di"
SUMMARY_TABLE = "dwm_sector_dragon_summary_di"
DEFAULT_CONTENT_TYPES = ("行业", "概念")


def _serialize(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()[:10]
    if isinstance(value, Decimal):
        return float(value)
    return value


def _serialize_row(row: dict) -> dict:
    return {k: _serialize(v) for k, v in row.items()}


def latest_trade_date() -> str | None:
    row = fetch_one_stock(f"SELECT MAX(trade_date) AS d FROM {SUMMARY_TABLE}")
    if row and row.get("d"):
        return _serialize(row["d"])
    row = fetch_one_stock(f"SELECT MAX(trade_date) AS d FROM {SCORE_TABLE}")
    return _serialize(row["d"]) if row and row.get("d") else None


def list_trade_dates(limit: int = 60) -> list[str]:
    limit = max(1, min(limit, 365))
    rows = fetch_all_stock(
        f"""
        SELECT DISTINCT trade_date AS d
        FROM {SUMMARY_TABLE}
        ORDER BY trade_date DESC
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
        raise ValueError("暂无龙头评分数据，请先运行 run_sector_dragon_batch")
    return latest


def _content_type_filter(content_types: list[str] | None) -> tuple[str, dict]:
    ctypes = content_types or list(DEFAULT_CONTENT_TYPES)
    if not ctypes:
        return "", {}
    placeholders = ", ".join(f":ct{i}" for i in range(len(ctypes)))
    params = {f"ct{i}": ct for i, ct in enumerate(ctypes)}
    return f" AND content_type IN ({placeholders})", params


def list_boards(
    trade_date: str | None = None,
    content_types: list[str] | None = None,
    keyword: str | None = None,
) -> list[dict]:
    td = _resolve_trade_date(trade_date)
    ct_sql, ct_params = _content_type_filter(content_types)
    params: dict[str, Any] = {"td": td, **ct_params}
    kw_sql = ""
    if keyword and keyword.strip():
        kw_sql = " AND (industry_name LIKE :kw OR industry_code LIKE :kw)"
        params["kw"] = f"%{keyword.strip()}%"
    rows = fetch_all_stock(
        f"""
        SELECT trade_date, industry_code, industry_name, content_type,
               leader_composite_name, leader_fund_name, leader_trend_name,
               leader_composite_ts, score_mode
        FROM {SUMMARY_TABLE}
        WHERE trade_date = :td {ct_sql} {kw_sql}
        ORDER BY content_type, industry_name
        """,
        params,
    )
    board_codes = [r["industry_code"] for r in rows]
    scores: dict[str, float | None] = {}
    if board_codes:
        placeholders = ", ".join(f":b{i}" for i in range(len(board_codes)))
        sp = {"td": td, **{f"b{i}": c for i, c in enumerate(board_codes)}}
        score_rows = fetch_all_stock(
            f"""
            SELECT industry_code, score_composite
            FROM {SCORE_TABLE}
            WHERE trade_date = :td AND is_composite_leader = 1
              AND industry_code IN ({placeholders})
            """,
            sp,
        )
        scores = {r["industry_code"]: _serialize(r["score_composite"]) for r in score_rows}
    out = []
    for r in rows:
        item = _serialize_row(r)
        item["score_composite"] = scores.get(r["industry_code"])
        out.append(item)
    return out


def get_leaders(
    trade_date: str | None = None,
    content_types: list[str] | None = None,
    industry_codes: list[str] | None = None,
    top: int = 50,
    sort: str = "composite",
    keyword: str | None = None,
) -> list[dict]:
    td = _resolve_trade_date(trade_date)
    ct_sql, ct_params = _content_type_filter(content_types)
    ct_sql = ct_sql.replace("content_type", "m.content_type")
    top = max(1, min(top, 200))
    order_col = {
        "composite": "s.score_composite",
        "fund": "s.score_fund",
        "trend": "s.score_trend",
    }.get(sort, "s.score_composite")
    kw_sql = ""
    code_sql = ""
    params: dict[str, Any] = {"td": td, **ct_params}
    if industry_codes:
        placeholders = ", ".join(f":ic{i}" for i in range(len(industry_codes)))
        code_sql = f" AND m.industry_code IN ({placeholders})"
        params.update({f"ic{i}": c for i, c in enumerate(industry_codes)})
    if keyword and keyword.strip():
        kw_sql = " AND (m.industry_name LIKE :kw OR m.industry_code LIKE :kw)"
        params["kw"] = f"%{keyword.strip()}%"
    rows = fetch_all_stock(
        f"""
        SELECT
            m.trade_date, m.industry_code, m.industry_name, m.content_type,
            m.leader_composite_name, m.leader_fund_name, m.leader_trend_name,
            m.leader_composite_ts, m.leader_fund_ts, m.leader_trend_ts,
            s.score_composite, s.score_fund, s.score_trend
        FROM {SUMMARY_TABLE} m
        LEFT JOIN {SCORE_TABLE} s
          ON s.trade_date = m.trade_date
         AND s.industry_code = m.industry_code
         AND s.ts_code = m.leader_composite_ts
         AND s.score_mode = m.score_mode
        WHERE m.trade_date = :td {ct_sql} {code_sql} {kw_sql}
        ORDER BY {order_col} IS NULL, {order_col} DESC, m.industry_name
        LIMIT {top}
        """,
        params,
    )
    return [_serialize_row(r) for r in rows]


def get_board_scores(
    industry_code: str,
    trade_date: str | None = None,
    mode: str = "mvp",
    top: int = 10,
    sort: str = "composite",
    order: str = "desc",
) -> dict:
    td = _resolve_trade_date(trade_date)
    header = fetch_one_stock(
        f"""
        SELECT trade_date, industry_code, industry_name, content_type, score_mode
        FROM {SCORE_TABLE}
        WHERE trade_date = :td AND industry_code = :ic AND score_mode = :mode
        LIMIT 1
        """,
        {"td": td, "ic": industry_code, "mode": mode},
    )
    if not header:
        raise ValueError(f"板块 {industry_code} 在 {td} 无评分数据")
    top = max(1, min(top, 200))
    sort_col = {
        "composite": "score_composite",
        "fund": "score_fund",
        "trend": "score_trend",
        "inst": "score_inst",
    }.get(sort, "score_composite")
    order_sql = "ASC" if str(order).lower() == "asc" else "DESC"
    rows = fetch_all_stock(
        f"""
        SELECT ts_code, stock_name,
               score_industry, score_fund, score_trend, score_inst, score_composite,
               rank_composite, rank_fund, rank_trend, rank_inst,
               is_composite_leader, is_fund_leader, is_trend_leader, is_inst_leader,
               detail_json
        FROM {SCORE_TABLE}
        WHERE trade_date = :td AND industry_code = :ic AND score_mode = :mode
        ORDER BY {sort_col} IS NULL, {sort_col} {order_sql}, rank_composite ASC
        LIMIT {top}
        """,
        {"td": td, "ic": industry_code, "mode": mode},
    )
    return {
        "trade_date": td,
        "industry_code": industry_code,
        "industry_name": header["industry_name"],
        "content_type": header.get("content_type"),
        "score_mode": mode,
        "items": [_serialize_row(r) for r in rows],
    }


def get_board_summary(
    industry_code: str,
    trade_date: str | None = None,
) -> dict:
    td = _resolve_trade_date(trade_date)
    row = fetch_one_stock(
        f"""
        SELECT *
        FROM {SUMMARY_TABLE}
        WHERE trade_date = :td AND industry_code = :ic
        ORDER BY score_mode DESC
        LIMIT 1
        """,
        {"td": td, "ic": industry_code},
    )
    if not row:
        raise ValueError(f"板块 {industry_code} 在 {td} 无摘要数据")
    return _serialize_row(row)


def parse_content_types_param(raw: str | None) -> list[str] | None:
    return parse_csv_list(raw) if raw else None
