"""东财板块四因子择时（K 线买卖点）查询服务。"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from app.db import fetch_all_stock, fetch_one_stock
from app.dc_query_util import resolve_trade_date
from app import chart_service as chart_svc
from app.sector_service import _board_code_variants

SIGNAL_TABLE = "dwm_board_timing_signal_di"
RETENTION_DAYS = 183

_SCORE_COLS = """
    industry_code, industry_name, content_type, close, ma20, ma60,
    score, score_trend, score_fund, score_vp, score_sentiment,
    signal_type, signal_reason, position_state,
    mom20, flow5, net_inflow_days, amount_ratio20, up_ratio, limit_up_ratio,
    sentiment_overheat, last_buy_close, rank_score
"""


def _serialize(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()[:10]
    if isinstance(value, Decimal):
        return float(value)
    return value


def _serialize_row(row: dict | None) -> dict | None:
    if not row:
        return None
    return {k: _serialize(v) for k, v in dict(row).items()}


def _resolve_trade_date(trade_date: str | None) -> str:
    return resolve_trade_date(
        trade_date,
        table=SIGNAL_TABLE,
        empty_msg="暂无择时信号，请先运行 run_board_timing_batch",
    )


def latest_trade_date() -> str | None:
    row = fetch_one_stock(
        f"SELECT MAX(trade_date) AS d FROM {SIGNAL_TABLE}"
    )
    if not row or not row.get("d"):
        return None
    return _serialize(row["d"])


def list_trade_dates(limit: int = 120) -> list[str]:
    rows = fetch_all_stock(
        f"""
        SELECT DISTINCT trade_date
        FROM {SIGNAL_TABLE}
        ORDER BY trade_date DESC
        LIMIT :lim
        """,
        {"lim": limit},
    )
    return [_serialize(r["trade_date"]) for r in rows]


def rank_boards(
    trade_date: str | None = None,
    *,
    content_types: str = "行业,概念",
    signal_type: str | None = None,
    top: int = 50,
    sort: str = "score",
) -> dict:
    td = _resolve_trade_date(trade_date)
    types = [x.strip() for x in content_types.split(",") if x.strip()] or ["行业", "概念"]
    ph = ", ".join(f":t{i}" for i in range(len(types)))
    params: dict[str, Any] = {"td": td, "top": top, **{f"t{i}": t for i, t in enumerate(types)}}

    sort_key = sort if sort in {"score", "score_trend", "score_fund", "score_vp", "score_sentiment", "rank_score"} else "score"
    order = "rank_score ASC, score DESC" if sort_key == "rank_score" else f"{sort_key} DESC, industry_code ASC"

    where_sig = ""
    if signal_type and signal_type in {"buy", "sell", "none"}:
        where_sig = " AND signal_type = :sig"
        params["sig"] = signal_type

    rows = fetch_all_stock(
        f"""
        SELECT {_SCORE_COLS}
        FROM {SIGNAL_TABLE}
        WHERE trade_date = :td
          AND content_type IN ({ph})
          {where_sig}
        ORDER BY {order}
        LIMIT :top
        """,
        params,
    )
    return {
        "trade_date": td,
        "items": [_serialize_row(r) for r in rows],
        "count": len(rows),
    }


def list_signals(
    trade_date: str | None = None,
    *,
    signal_type: str | None = None,
    content_types: str = "行业,概念",
    top: int = 100,
) -> dict:
    td = _resolve_trade_date(trade_date)
    types = [x.strip() for x in content_types.split(",") if x.strip()] or ["行业", "概念"]
    ph = ", ".join(f":t{i}" for i in range(len(types)))
    params: dict[str, Any] = {"td": td, "top": top, **{f"t{i}": t for i, t in enumerate(types)}}

    if signal_type in {"buy", "sell"}:
        where_sig = "AND signal_type = :sig"
        params["sig"] = signal_type
    else:
        where_sig = "AND signal_type IN ('buy', 'sell')"

    rows = fetch_all_stock(
        f"""
        SELECT {_SCORE_COLS}
        FROM {SIGNAL_TABLE}
        WHERE trade_date = :td
          AND content_type IN ({ph})
          {where_sig}
        ORDER BY
          CASE signal_type WHEN 'buy' THEN 0 WHEN 'sell' THEN 1 ELSE 2 END,
          score DESC
        LIMIT :top
        """,
        params,
    )
    return {
        "trade_date": td,
        "items": [_serialize_row(r) for r in rows],
        "count": len(rows),
    }


def search_boards(
    trade_date: str | None = None,
    *,
    content_types: str = "行业,概念",
    keyword: str | None = None,
    limit: int = 50,
) -> dict:
    td = _resolve_trade_date(trade_date)
    types = [x.strip() for x in content_types.split(",") if x.strip()] or ["行业", "概念"]
    ph = ", ".join(f":t{i}" for i in range(len(types)))
    params: dict[str, Any] = {"td": td, "lim": limit, **{f"t{i}": t for i, t in enumerate(types)}}
    kw_sql = ""
    if keyword and keyword.strip():
        kw_sql = " AND (industry_name LIKE :kw OR industry_code LIKE :kw)"
        params["kw"] = f"%{keyword.strip()}%"

    rows = fetch_all_stock(
        f"""
        SELECT industry_code, industry_name, content_type, score, signal_type, position_state
        FROM {SIGNAL_TABLE}
        WHERE trade_date = :td AND content_type IN ({ph}) {kw_sql}
        ORDER BY score DESC
        LIMIT :lim
        """,
        params,
    )
    return {"trade_date": td, "items": [_serialize_row(r) for r in rows]}


def get_board_detail(industry_code: str, trade_date: str | None = None) -> dict:
    td = _resolve_trade_date(trade_date)
    codes = _board_code_variants(industry_code)
    ph = ", ".join(f":c{i}" for i in range(len(codes)))
    params = {"td": td, **{f"c{i}": c for i, c in enumerate(codes)}}
    row = fetch_one_stock(
        f"""
        SELECT {_SCORE_COLS}
        FROM {SIGNAL_TABLE}
        WHERE trade_date = :td AND industry_code IN ({ph})
        LIMIT 1
        """,
        params,
    )
    if not row:
        raise ValueError(f"未找到板块择时数据: {industry_code} @ {td}")
    return {"trade_date": td, "item": _serialize_row(row)}


def get_board_kline(
    industry_code: str,
    trade_date: str | None = None,
    *,
    start_date: str | None = None,
    days: int = 60,
) -> dict:
    td = _resolve_trade_date(trade_date)
    code = industry_code.strip()
    codes = _board_code_variants(code)
    chart = chart_svc.get_board_kline(code, td, days=days, start_date=start_date)
    bars = chart.get("bars") or []
    if not bars:
        raise ValueError(f"板块 {code} 暂无 K 线")

    start = bars[0].get("trade_date") or td
    end = bars[-1].get("trade_date") or td
    ph = ", ".join(f":c{i}" for i in range(len(codes)))
    params: dict[str, Any] = {
        "start": start,
        "end": end,
        **{f"c{i}": c for i, c in enumerate(codes)},
    }
    sig_rows = fetch_all_stock(
        f"""
        SELECT trade_date, score, score_trend, score_fund, score_vp, score_sentiment,
               signal_type, signal_reason, position_state, flow5, amount_ratio20,
               ma20, ma60, close
        FROM {SIGNAL_TABLE}
        WHERE industry_code IN ({ph})
          AND trade_date BETWEEN :start AND :end
        ORDER BY trade_date ASC
        """,
        params,
    )
    by_date = {_serialize(r["trade_date"]): _serialize_row(r) for r in sig_rows}
    series = []
    for b in bars:
        d = b.get("trade_date")
        row = by_date.get(d)
        series.append(row if row else {"trade_date": d})

    return {
        **chart,
        "trade_date": td,
        "industry_code": code,
        "start_date": start,
        "end_date": end,
        "timing": series,
        "signals": [
            _serialize_row(r)
            for r in sig_rows
            if (r.get("signal_type") or "none") in ("buy", "sell")
        ],
    }
