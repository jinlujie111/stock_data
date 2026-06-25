"""东财主线板块：监控榜与历史得分查询（需求1）。"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from app.db import fetch_all_stock, fetch_one_stock
from app.dc_service import parse_csv_list, parse_trade_date

MONITOR_TABLE = "dws_dc_industry_mainline_monitor_di"
SCORE_TABLE = "dws_dc_industry_mainline_score_di"
DEFAULT_CONTENT_TYPES = ("行业", "概念")
MAINLINE_LEVELS = ("超级主线", "主线", "轮动热点", "跟风")
MA_COLUMNS = {3: "total_score_ma3", 5: "total_score_ma5", 10: "total_score_ma10"}


def _serialize(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()[:10]
    if isinstance(value, Decimal):
        return float(value)
    return value


def _serialize_row(row: dict) -> dict:
    return {k: _serialize(v) for k, v in row.items()}


def _ma_column(ma_window: int) -> str:
    return MA_COLUMNS.get(ma_window, "total_score_ma5")


def latest_trade_date() -> str | None:
    row = fetch_one_stock(f"SELECT MAX(trade_date) AS d FROM {MONITOR_TABLE}")
    if row and row.get("d"):
        return _serialize(row["d"])
    row = fetch_one_stock(f"SELECT MAX(trade_date) AS d FROM {SCORE_TABLE}")
    return _serialize(row["d"]) if row and row.get("d") else None


def list_trade_dates(limit: int = 60) -> list[str]:
    limit = max(1, min(limit, 365))
    rows = fetch_all_stock(
        f"""
        SELECT DISTINCT trade_date AS d
        FROM {MONITOR_TABLE}
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
        raise ValueError("暂无主线监控数据，请先运行 run_dws_dc_industry_mainline_monitor")
    return latest


def _content_type_filter(content_types: list[str] | None) -> tuple[str, dict]:
    ctypes = content_types or list(DEFAULT_CONTENT_TYPES)
    if not ctypes:
        return "", {}
    placeholders = ", ".join(f":ct{i}" for i in range(len(ctypes)))
    params = {f"ct{i}": ct for i, ct in enumerate(ctypes)}
    return f" AND content_type IN ({placeholders})", params


def _level_filter(levels: list[str] | None) -> tuple[str, dict]:
    if not levels:
        return "", {}
    valid = [lv for lv in levels if lv in MAINLINE_LEVELS]
    if not valid:
        return "", {}
    placeholders = ", ".join(f":lv{i}" for i in range(len(valid)))
    params = {f"lv{i}": lv for i, lv in enumerate(valid)}
    return f" AND mainline_level IN ({placeholders})", params


def _row_to_rank_item(row: dict, ma_window: int) -> dict:
    item = _serialize_row(row)
    ma_col = _ma_column(ma_window)
    display_score = item.get(ma_col) if item.get(ma_col) is not None else item.get("main_score")
    if display_score is None:
        display_score = item.get("total_score")
    return {
        "rank": item.get("rank_no"),
        "industry_code": item.get("industry_code"),
        "industry_name": item.get("industry_name"),
        "content_type": item.get("content_type"),
        "total_score": item.get("total_score"),
        "main_score": display_score,
        "total_score_ma3": item.get("total_score_ma3"),
        "total_score_ma5": item.get("total_score_ma5"),
        "total_score_ma10": item.get("total_score_ma10"),
        "mainline_level": item.get("mainline_level"),
        "stage": item.get("mainline_stage"),
        "fund_cont_days": item.get("fund_cont_days"),
        "rs_5d": item.get("rs_5d"),
        "limit_up_cnt": item.get("limit_up_cnt"),
        "profit_yoy": item.get("profit_yoy"),
        "amount_ratio": item.get("amount_ratio"),
        "limit_up_ratio": item.get("limit_up_ratio"),
        "up_ratio": item.get("up_ratio"),
        "score_fund": item.get("score_fund"),
        "score_trend": item.get("score_trend"),
        "score_heat": item.get("score_heat"),
        "score_prosperity": item.get("score_prosperity"),
        "score_diffusion": item.get("score_diffusion"),
        "is_top20": bool(item.get("is_top20")),
    }


def get_rank(
    trade_date: str | None = None,
    content_types: list[str] | None = None,
    levels: list[str] | None = None,
    top: int = 20,
    ma_window: int = 5,
    top20_only: bool = False,
) -> dict:
    td = _resolve_trade_date(trade_date)
    ma_window = ma_window if ma_window in MA_COLUMNS else 5
    top = max(1, min(top, 200))
    ct_sql, ct_params = _content_type_filter(content_types)
    lv_sql, lv_params = _level_filter(levels)
    top20_sql = " AND is_top20 = 1" if top20_only else ""
    ma_col = _ma_column(ma_window)
    params: dict[str, Any] = {"td": td, **ct_params, **lv_params}
    rows = fetch_all_stock(
        f"""
        SELECT
            trade_date, content_type, industry_code, industry_name, rank_no,
            main_score, total_score, total_score_ma3, total_score_ma5, total_score_ma10,
            mainline_level, mainline_stage, fund_cont_days, rs_5d, limit_up_cnt, profit_yoy,
            amount_ratio, limit_up_ratio, up_ratio,
            score_fund, score_trend, score_heat, score_prosperity, score_diffusion,
            is_top20
        FROM {MONITOR_TABLE}
        WHERE trade_date = :td {ct_sql} {lv_sql} {top20_sql}
        ORDER BY {ma_col} IS NULL, {ma_col} DESC, rank_no ASC
        LIMIT {top}
        """,
        params,
    )
    return {
        "trade_date": td,
        "ma_window": ma_window,
        "items": [_row_to_rank_item(r, ma_window) for r in rows],
    }


def get_industry_history(
    industry_code: str,
    trade_date: str | None = None,
    days: int = 60,
) -> dict:
    if not industry_code or not industry_code.strip():
        raise ValueError("industry_code 必填")
    code = industry_code.strip()
    end_date = _resolve_trade_date(trade_date)
    days = max(1, min(days, 365))
    header = fetch_one_stock(
        f"""
        SELECT industry_name, content_type
        FROM {MONITOR_TABLE}
        WHERE industry_code = :ic
        ORDER BY trade_date DESC
        LIMIT 1
        """,
        {"ic": code},
    )
    rows = fetch_all_stock(
        f"""
        SELECT
            trade_date, total_score, total_score_ma3, total_score_ma5, total_score_ma10,
            mainline_level, rank_no,
            score_fund, score_trend, score_heat, score_prosperity, score_diffusion
        FROM {SCORE_TABLE}
        WHERE industry_code = :ic AND trade_date <= :end
        ORDER BY trade_date DESC
        LIMIT {days}
        """,
        {"ic": code, "end": end_date},
    )
    if not rows and not header:
        raise ValueError(f"板块 {code} 暂无主线得分历史")
    history = list(reversed([_serialize_row(r) for r in rows]))
    stage_rows = fetch_all_stock(
        f"""
        SELECT trade_date, mainline_stage, main_score, fund_cont_days, rs_5d, limit_up_cnt
        FROM {MONITOR_TABLE}
        WHERE industry_code = :ic AND trade_date <= :end
        ORDER BY trade_date DESC
        LIMIT {days}
        """,
        {"ic": code, "end": end_date},
    )
    stages = {str(_serialize(r["trade_date"])): _serialize_row(r) for r in stage_rows}
    for pt in history:
        td = pt["trade_date"]
        if td in stages:
            pt["stage"] = stages[td].get("mainline_stage")
            pt["main_score"] = stages[td].get("main_score")
    return {
        "industry_code": code,
        "industry_name": header["industry_name"] if header else None,
        "content_type": header.get("content_type") if header else None,
        "end_date": end_date,
        "items": history,
    }


def parse_levels_param(raw: str | None) -> list[str] | None:
    items = parse_csv_list(raw)
    return items if items else None
