"""东财量化主线 FTELP（需求3）查询服务。"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from app.db import fetch_all_stock, fetch_one_stock
from app.dc_service import parse_csv_list, parse_trade_date

MAINLINE_TABLE = "dws_dc_industry_quant_mainline_di"
SIGNAL_TABLE = "dws_dc_industry_quant_mainline_signal_di"
CONFIG_TABLE = "quant_mainline_config"
DEFAULT_CONTENT_TYPES = ("行业", "概念")


def _serialize(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()[:10]
    if isinstance(value, Decimal):
        return float(value)
    return value


def _serialize_row(row: dict) -> dict:
    out: dict[str, Any] = {}
    for k, v in row.items():
        if k == "detail_json" and isinstance(v, str):
            out[k] = v
            continue
        out[k] = _serialize(v)
    return out


def latest_trade_date() -> str | None:
    row = fetch_one_stock(f"SELECT MAX(trade_date) AS d FROM {MAINLINE_TABLE}")
    return _serialize(row["d"]) if row and row.get("d") else None


def list_trade_dates(limit: int = 60) -> list[str]:
    limit = max(1, min(limit, 365))
    rows = fetch_all_stock(
        f"""
        SELECT DISTINCT trade_date AS d
        FROM {MAINLINE_TABLE}
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
        raise ValueError("暂无量化主线数据，请先运行 run_dws_dc_industry_quant_mainline")
    return latest


def _content_type_filter(content_types: list[str] | None) -> tuple[str, dict]:
    ctypes = content_types or list(DEFAULT_CONTENT_TYPES)
    if not ctypes:
        return "", {}
    placeholders = ", ".join(f":ct{i}" for i in range(len(ctypes)))
    params = {f"ct{i}": ct for i, ct in enumerate(ctypes)}
    return f" AND m.content_type IN ({placeholders})", params


def get_top(
    trade_date: str | None = None,
    content_types: list[str] | None = None,
    top: int = 3,
    top_only: bool = True,
    ma_window: int = 5,
) -> dict[str, Any]:
    td = _resolve_trade_date(trade_date)
    top = max(1, min(top, 50))
    ct_sql, ct_params = _content_type_filter(content_types)
    ma_col = {3: "main_score_ma3", 5: "main_score_ma5", 10: "main_score_ma10"}.get(
        ma_window, "main_score_ma5"
    )
    top_filter = " AND m.is_top3 = 1" if top_only else ""
    sql = f"""
    SELECT
        m.trade_date, m.content_type, m.industry_code, m.industry_name,
        m.score_f, m.score_t, m.score_e, m.score_l, m.score_p,
        m.main_score, m.main_score_ma3, m.main_score_ma5, m.main_score_ma10,
        m.rank_no, m.rank_score, m.is_top3,
        m.amount_ratio, m.rs_ratio, m.limit_up_ratio,
        m.leader_code, m.leader_name, m.leader_pct_chg,
        s.signal_status, s.signal_start, s.signal_exit, s.signal_reason
    FROM {MAINLINE_TABLE} m
    LEFT JOIN {SIGNAL_TABLE} s
        ON s.trade_date = m.trade_date AND s.industry_code = m.industry_code
    WHERE m.trade_date = :td
    {ct_sql}
    {top_filter}
    ORDER BY m.rank_no ASC, m.{ma_col} DESC, m.main_score DESC
    LIMIT {top}
    """
    params: dict[str, Any] = {"td": td, **ct_params}
    rows = fetch_all_stock(sql, params)
    items = []
    for r in rows:
        item = _serialize_row(r)
        display = item.get(ma_col) if item.get(ma_col) is not None else item.get("main_score")
        item["display_score"] = display
        items.append(item)
    return {"trade_date": td, "ma_window": ma_window, "top": top, "items": items}


def get_signals(
    trade_date: str | None = None,
    content_types: list[str] | None = None,
    status: str | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    td = _resolve_trade_date(trade_date)
    ct_sql, ct_params = _content_type_filter(content_types)
    status_sql = ""
    if status in ("启动", "退潮", "观察"):
        status_sql = " AND s.signal_status = :status"
        ct_params["status"] = status
    limit = max(1, min(limit, 500))
    sql = f"""
    SELECT
        s.trade_date, s.industry_code, s.industry_name, s.content_type,
        s.signal_start, s.signal_exit, s.signal_status, s.signal_reason,
        s.leader_code, s.leader_name, s.leader_pct_chg,
        m.main_score, m.main_score_ma5, m.rank_no, m.is_top3,
        m.score_f, m.score_t, m.score_e, m.score_l, m.score_p
    FROM {SIGNAL_TABLE} s
    LEFT JOIN {MAINLINE_TABLE} m
        ON m.trade_date = s.trade_date AND m.industry_code = s.industry_code
    WHERE s.trade_date = :td
    {ct_sql.replace('m.content_type', 's.content_type')}
    {status_sql}
    ORDER BY m.rank_no ASC, m.main_score DESC
    LIMIT {limit}
    """
    params: dict[str, Any] = {"td": td, **ct_params}
    rows = fetch_all_stock(sql, params)
    return {
        "trade_date": td,
        "items": [_serialize_row(r) for r in rows],
    }


def get_history(
    industry_code: str,
    trade_date: str | None = None,
    days: int = 60,
) -> dict[str, Any]:
    if not industry_code or not industry_code.strip():
        raise ValueError("industry_code 必填")
    code = industry_code.strip()
    td = _resolve_trade_date(trade_date)
    days = max(5, min(days, 365))
    sql = f"""
    SELECT
        m.trade_date, m.industry_code, m.industry_name, m.content_type,
        m.main_score, m.main_score_ma3, m.main_score_ma5, m.main_score_ma10,
        m.score_f, m.score_t, m.score_e, m.score_l, m.score_p,
        m.rank_no, m.is_top3,
        s.signal_status, s.signal_start, s.signal_exit
    FROM {MAINLINE_TABLE} m
    LEFT JOIN {SIGNAL_TABLE} s
        ON s.trade_date = m.trade_date AND s.industry_code = m.industry_code
    WHERE m.industry_code = :code
      AND m.trade_date <= :td
    ORDER BY m.trade_date DESC
    LIMIT {days}
    """
    rows = fetch_all_stock(sql, {"code": code, "td": td})
    items = [_serialize_row(r) for r in rows]
    name = items[0].get("industry_name") if items else None
    return {
        "industry_code": code,
        "industry_name": name,
        "trade_date": td,
        "items": list(reversed(items)),
    }


def get_config() -> dict[str, Any]:
    row = fetch_one_stock(
        f"""
        SELECT *
        FROM {CONFIG_TABLE}
        WHERE config_key = '__global__' AND is_active = 1
        ORDER BY effective_date DESC
        LIMIT 1
        """
    )
    if not row:
        return {"config_key": "__global__", "message": "无配置，使用 ETL 内置默认"}
    return _serialize_row(row)
