"""东财量化主线 FTELP（需求3）查询服务。"""
from __future__ import annotations

from typing import Any

from app.db import fetch_all_stock, fetch_one_stock
from app.dc_query_util import (
    list_trade_dates_from_table,
    latest_trade_date_from_table,
    resolve_trade_date,
    serialize_row,
)
from app.dc_service import parse_csv_list

MAINLINE_TABLE = "dws_dc_industry_quant_mainline_di"
SIGNAL_TABLE = "dws_dc_industry_quant_mainline_signal_di"
CONFIG_TABLE = "quant_mainline_config"
DEFAULT_CONTENT_TYPES = ("行业", "概念")
TOP_BOARD_TYPES = ("行业", "概念")
DEFAULT_TOP_N = 10


def _row_to_top_item(row: dict, ma_col: str) -> dict:
    item = serialize_row(row, keep_detail_json_str=True)
    display = item.get(ma_col) if item.get(ma_col) is not None else item.get("main_score")
    item["display_score"] = display
    item["is_topn"] = bool(item.get("is_top3"))
    return item


def _fetch_top_rows(
    td: str,
    content_type: str,
    *,
    top: int,
    top_only: bool,
    ma_col: str,
) -> list[dict]:
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
      AND m.content_type = :ct
    {top_filter}
    ORDER BY m.rank_no ASC, m.{ma_col} DESC, m.main_score DESC
    LIMIT {top}
    """
    rows = fetch_all_stock(sql, {"td": td, "ct": content_type})
    return [_row_to_top_item(r, ma_col) for r in rows]


def latest_trade_date() -> str | None:
    return latest_trade_date_from_table(MAINLINE_TABLE)


def list_trade_dates(limit: int = 60) -> list[str]:
    return list_trade_dates_from_table(MAINLINE_TABLE, limit)


def _resolve_trade_date(trade_date: str | None) -> str:
    return resolve_trade_date(
        trade_date,
        table=MAINLINE_TABLE,
        empty_msg="暂无量化主线数据，请先运行 run_dws_dc_industry_quant_mainline",
    )


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
    top: int = DEFAULT_TOP_N,
    top_only: bool = True,
    ma_window: int = 5,
) -> dict[str, Any]:
    td = _resolve_trade_date(trade_date)
    top = max(1, min(top, 50))
    ctypes = content_types or list(DEFAULT_CONTENT_TYPES)
    if len(ctypes) != 1:
        raise ValueError("get_top 请指定单一 content_types，或使用 get_top_groups")
    ma_col = {3: "main_score_ma3", 5: "main_score_ma5", 10: "main_score_ma10"}.get(
        ma_window, "main_score_ma5"
    )
    items = _fetch_top_rows(td, ctypes[0], top=top, top_only=top_only, ma_col=ma_col)
    return {
        "trade_date": td,
        "ma_window": ma_window,
        "top": top,
        "content_type": ctypes[0],
        "items": items,
    }


def get_top_groups(
    trade_date: str | None = None,
    content_types: list[str] | None = None,
    top: int = DEFAULT_TOP_N,
    top_only: bool = True,
    ma_window: int = 5,
) -> dict[str, Any]:
    td = _resolve_trade_date(trade_date)
    top = max(1, min(top, 50))
    ctypes = content_types or list(TOP_BOARD_TYPES)
    ma_col = {3: "main_score_ma3", 5: "main_score_ma5", 10: "main_score_ma10"}.get(
        ma_window, "main_score_ma5"
    )
    groups: list[dict[str, Any]] = []
    for ct in TOP_BOARD_TYPES:
        if ct not in ctypes:
            continue
        groups.append(
            {
                "content_type": ct,
                "top": top,
                "items": _fetch_top_rows(td, ct, top=top, top_only=top_only, ma_col=ma_col),
            }
        )
    return {"trade_date": td, "ma_window": ma_window, "top": top, "groups": groups}


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
        "items": [serialize_row(r, keep_detail_json_str=True) for r in rows],
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
    items = [serialize_row(r, keep_detail_json_str=True) for r in rows]
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
    return serialize_row(row, keep_detail_json_str=True)
