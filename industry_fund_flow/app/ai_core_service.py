"""需求4：AI 核心池查询服务。"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from app.db import fetch_all_stock, fetch_one_stock
from app.dc_service import parse_trade_date

SCORE_TABLE = "dwm_industry_stock_ai_score_di"
CORE_TABLE = "dwm_industry_stock_core_di"
TRACK_TABLE = "dim_industry_track"


def _serialize(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()[:10]
    if isinstance(value, Decimal):
        return float(value)
    return value


def _serialize_row(row: dict) -> dict:
    return {k: _serialize(v) for k, v in row.items()}


def latest_trade_date() -> str | None:
    row = fetch_one_stock(f"SELECT MAX(trade_date) AS d FROM {CORE_TABLE}")
    if row and row.get("d"):
        return _serialize(row["d"])
    row = fetch_one_stock(f"SELECT MAX(trade_date) AS d FROM {SCORE_TABLE}")
    return _serialize(row["d"]) if row and row.get("d") else None


def list_trade_dates(limit: int = 60) -> list[str]:
    limit = max(1, min(limit, 365))
    rows = fetch_all_stock(
        f"""
        SELECT d FROM (
            SELECT DISTINCT trade_date AS d FROM {CORE_TABLE}
            UNION
            SELECT DISTINCT trade_date AS d FROM {SCORE_TABLE}
        ) t
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
        raise ValueError("暂无 AI 核心池数据，请先运行 run_ai_core_pool_batch")
    return latest


def list_tracks(trade_date: str | None = None, keyword: str | None = None) -> list[dict]:
    td = _resolve_trade_date(trade_date)
    params: dict[str, Any] = {"td": td}
    kw_sql = ""
    if keyword and keyword.strip():
        kw_sql = " AND (t.industry_name LIKE :kw OR t.industry_id LIKE :kw)"
        params["kw"] = f"%{keyword.strip()}%"
    rows = fetch_all_stock(
        f"""
        SELECT
            t.industry_id,
            t.industry_name,
            t.content_type,
            t.heat_sort,
            t.amount_ratio,
            COUNT(c.ts_code) AS core_cnt
        FROM {TRACK_TABLE} t
        LEFT JOIN {CORE_TABLE} c
          ON c.industry_id = t.industry_id AND c.trade_date = :td
        WHERE t.as_of_date = :td AND t.status = 1
        {kw_sql}
        GROUP BY t.industry_id, t.industry_name, t.content_type, t.heat_sort, t.amount_ratio
        ORDER BY t.heat_sort
        """,
        params,
    )
    out = []
    for r in rows:
        item = _serialize_row(r)
        item["trade_date"] = td
        out.append(item)
    return out


def get_core_pool(
    industry_id: str,
    trade_date: str | None = None,
    level: str | None = None,
) -> dict:
    td = _resolve_trade_date(trade_date)
    params: dict[str, Any] = {"td": td, "iid": industry_id}
    lvl_sql = ""
    if level and level.upper() in ("S", "A", "B"):
        lvl_sql = " AND level = :lvl"
        params["lvl"] = level.upper()
    track = fetch_one_stock(
        f"""
        SELECT industry_id, industry_name, content_type, heat_sort
        FROM {TRACK_TABLE}
        WHERE as_of_date = :td AND industry_id = :iid AND status = 1
        LIMIT 1
        """,
        params,
    )
    if not track:
        raise ValueError(f"赛道不存在: {industry_id}")
    rows = fetch_all_stock(
        f"""
        SELECT ts_code, stock_name, score, level, weight, segment, reason
        FROM {CORE_TABLE}
        WHERE trade_date = :td AND industry_id = :iid
        {lvl_sql}
        ORDER BY score DESC, ts_code
        """,
        params,
    )
    return {
        "trade_date": td,
        "industry_id": track["industry_id"],
        "industry_name": track["industry_name"],
        "content_type": track.get("content_type"),
        "items": [_serialize_row(r) for r in rows],
    }


def get_scores(
    industry_id: str,
    trade_date: str | None = None,
    include_rejected: bool = False,
) -> dict:
    td = _resolve_trade_date(trade_date)
    params: dict[str, Any] = {"td": td, "iid": industry_id}
    match_sql = "" if include_rejected else " AND industry_match = 1"
    rows = fetch_all_stock(
        f"""
        SELECT ts_code, stock_name, industry_match, segment, core_degree,
               score, level, reason, model_name
        FROM {SCORE_TABLE}
        WHERE trade_date = :td AND industry_id = :iid
        {match_sql}
        ORDER BY score DESC, ts_code
        """,
        params,
    )
    track = fetch_one_stock(
        f"""
        SELECT industry_name FROM {TRACK_TABLE}
        WHERE as_of_date = :td AND industry_id = :iid LIMIT 1
        """,
        params,
    )
    return {
        "trade_date": td,
        "industry_id": industry_id,
        "industry_name": track["industry_name"] if track else industry_id,
        "items": [_serialize_row(r) for r in rows],
    }
