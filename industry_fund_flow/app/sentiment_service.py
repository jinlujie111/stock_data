"""市场/板块情绪评分与历史曲线。"""
from __future__ import annotations

from typing import Any

from app.db import fetch_all_stock, fetch_one_stock
from app.dc_query_util import (
    latest_trade_date_from_table,
    list_trade_dates_from_table,
    resolve_trade_date,
    serialize_row,
)

MARKET_TABLE = "dwm_market_breadth_di"
FUND_TABLE = "dwm_dc_industry_fund_flow_di"
HEAT_TABLE = "dwm_dc_industry_market_heat_di"
MONITOR_TABLE = "dws_dc_industry_mainline_monitor_di"
DRAGON_TABLE = "dwm_sector_dragon_summary_di"

DEFAULT_CONTENT_TYPES = ("行业", "概念")


def latest_trade_date() -> str | None:
    return latest_trade_date_from_table(FUND_TABLE, fallback_table=MARKET_TABLE)


def list_trade_dates(limit: int = 90) -> list[str]:
    dates = list_trade_dates_from_table(FUND_TABLE, limit)
    if dates:
        return dates
    return list_trade_dates_from_table(MARKET_TABLE, limit)


def _resolve_trade_date(trade_date: str | None) -> str:
    return resolve_trade_date(
        trade_date,
        table=FUND_TABLE,
        fallback_table=MARKET_TABLE,
        empty_msg="暂无情绪数据，请先准备市场广度与板块行情数据",
    )


def _num(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, value))


def _scale(value: float | None, lo: float, hi: float) -> float:
    if value is None:
        return 50.0
    if hi <= lo:
        return 50.0
    return _clamp((value - lo) * 100.0 / (hi - lo))


def _market_sentiment_score(row: dict[str, Any]) -> tuple[float, dict[str, float]]:
    total_cnt = max(_num(row.get("total_cnt")) or 0.0, 1.0)
    advance_ratio = _num(row.get("advance_ratio"))
    if advance_ratio is None:
        advance_cnt = _num(row.get("advance_cnt")) or 0.0
        advance_ratio = advance_cnt / total_cnt
    elif advance_ratio > 1:
        advance_ratio = advance_ratio / 100.0

    limit_up_cnt = _num(row.get("limit_up_cnt")) or 0.0
    limit_down_cnt = _num(row.get("limit_down_cnt")) or 0.0

    breadth_score = _clamp((advance_ratio or 0.5) * 100.0)
    limit_balance_score = ((limit_up_cnt - limit_down_cnt) / (limit_up_cnt + limit_down_cnt + 1.0) + 1.0) * 50.0
    limit_activity_score = _scale(limit_up_cnt / total_cnt, 0.0, 0.03)
    risk_score = 100.0 - _scale(limit_down_cnt / total_cnt, 0.0, 0.02)

    score = round(
        breadth_score * 0.45
        + limit_balance_score * 0.25
        + limit_activity_score * 0.15
        + risk_score * 0.15,
        2,
    )
    return score, {
        "breadth_score": round(breadth_score, 2),
        "limit_balance_score": round(limit_balance_score, 2),
        "limit_activity_score": round(limit_activity_score, 2),
        "risk_score": round(risk_score, 2),
    }


def _sector_sentiment_score(row: dict[str, Any]) -> tuple[float, dict[str, float]]:
    pct_change = _num(row.get("pct_change"))
    up_ratio = _num(row.get("up_ratio"))
    if up_ratio is not None and up_ratio > 1:
        up_ratio = up_ratio / 100.0
    limit_up_ratio = _num(row.get("limit_up_ratio"))
    if limit_up_ratio is not None and limit_up_ratio > 1:
        limit_up_ratio = limit_up_ratio / 100.0
    net_amount_rate = _num(row.get("net_amount_rate"))
    turnover_rate = _num(row.get("turnover_rate"))
    main_score = _num(row.get("main_score"))
    leader_name = (row.get("leader_composite_name") or "").strip()

    price_score = _scale(pct_change, -6.0, 6.0)
    breadth_score = _clamp((up_ratio or 0.5) * 100.0)
    limit_score = _scale(limit_up_ratio, 0.0, 0.08)
    fund_score = _scale(net_amount_rate, -5.0, 5.0)
    turnover_score = _scale(turnover_rate, 1.0, 8.0)

    if main_score is None:
        mainline_score = 50.0
    else:
        mainline_score = _scale(main_score, 20.0, 100.0)

    leader_score = 100.0 if leader_name else 40.0

    score = round(
        price_score * 0.20
        + breadth_score * 0.20
        + limit_score * 0.15
        + fund_score * 0.15
        + turnover_score * 0.10
        + mainline_score * 0.12
        + leader_score * 0.08,
        2,
    )
    return score, {
        "price_score": round(price_score, 2),
        "breadth_score": round(breadth_score, 2),
        "limit_score": round(limit_score, 2),
        "fund_score": round(fund_score, 2),
        "turnover_score": round(turnover_score, 2),
        "mainline_score": round(mainline_score, 2),
        "leader_score": round(leader_score, 2),
    }


def _latest_board_header(industry_code: str, end_trade_date: str) -> dict[str, Any] | None:
    row = fetch_one_stock(
        f"""
        SELECT industry_code, industry_name, content_type
        FROM {FUND_TABLE}
        WHERE industry_code = :industry_code
          AND trade_date <= :trade_date
        ORDER BY trade_date DESC
        LIMIT 1
        """,
        {"industry_code": industry_code, "trade_date": end_trade_date},
    )
    return serialize_row(row) if row else None


def resolve_board(industry_code: str | None, keyword: str | None, trade_date: str | None = None) -> dict[str, Any] | None:
    td = _resolve_trade_date(trade_date)
    if industry_code and industry_code.strip():
        return _latest_board_header(industry_code.strip(), td)

    kw = (keyword or "").strip()
    if kw:
        row = fetch_one_stock(
            f"""
            SELECT industry_code, industry_name, content_type
            FROM {FUND_TABLE}
            WHERE trade_date = :trade_date
              AND content_type IN ('行业', '概念')
              AND (industry_name LIKE :kw OR industry_code LIKE :kw)
            ORDER BY pct_change DESC, industry_name
            LIMIT 1
            """,
            {"trade_date": td, "kw": f"%{kw}%"},
        )
        return serialize_row(row) if row else None

    row = fetch_one_stock(
        f"""
        SELECT industry_code, industry_name, content_type
        FROM {FUND_TABLE}
        WHERE trade_date = :trade_date
          AND content_type IN ('行业', '概念')
        ORDER BY pct_change DESC, net_amount DESC, industry_name
        LIMIT 1
        """,
        {"trade_date": td},
    )
    return serialize_row(row) if row else None


def get_sentiment_history(
    industry_code: str | None = None,
    *,
    keyword: str | None = None,
    trade_date: str | None = None,
    days: int = 365,
) -> dict[str, Any]:
    td = _resolve_trade_date(trade_date)
    days = max(30, min(days, 365))
    board = resolve_board(industry_code, keyword, td)

    market_rows = fetch_all_stock(
        f"""
        SELECT trade_date, total_cnt, advance_cnt, decline_cnt, flat_cnt, advance_ratio,
               limit_up_cnt, limit_down_cnt
        FROM {MARKET_TABLE}
        WHERE trade_date <= :trade_date
        ORDER BY trade_date DESC
        LIMIT {days}
        """,
        {"trade_date": td},
    )
    market_items = []
    for raw in reversed(market_rows):
        row = serialize_row(raw)
        score, detail = _market_sentiment_score(row)
        market_items.append({**row, "score": score, "detail": detail})

    sector_items: list[dict[str, Any]] = []
    if board:
        sector_rows = fetch_all_stock(
            f"""
            SELECT
                ff.trade_date, ff.industry_code, ff.industry_name, ff.content_type,
                ff.pct_change, ff.net_amount, ff.net_amount_rate, ff.board_amount,
                COALESCE(mh.up_ratio, 0) AS up_ratio,
                COALESCE(mh.limit_up_ratio, 0) AS limit_up_ratio,
                COALESCE(mh.limit_up_cnt, 0) AS limit_up_cnt,
                COALESCE(daily.turnover_rate, idx.turnover_rate, mh.turnover_rate) AS turnover_rate,
                m.main_score,
                d.leader_composite_name
            FROM {FUND_TABLE} ff
            LEFT JOIN {HEAT_TABLE} mh
              ON mh.trade_date = ff.trade_date AND mh.industry_code = ff.industry_code
            LEFT JOIN ods_dc_daily_di daily
              ON daily.trade_date = ff.trade_date AND daily.ts_code = ff.industry_code
            LEFT JOIN ods_dc_index_di idx
              ON idx.trade_date = ff.trade_date AND idx.ts_code = ff.industry_code
            LEFT JOIN {MONITOR_TABLE} m
              ON m.trade_date = ff.trade_date AND m.industry_code = ff.industry_code
            LEFT JOIN {DRAGON_TABLE} d
              ON d.trade_date = ff.trade_date
             AND d.industry_code = ff.industry_code
             AND d.score_mode = 'mvp'
            WHERE ff.industry_code = :industry_code
              AND ff.trade_date <= :trade_date
            ORDER BY ff.trade_date DESC
            LIMIT {days}
            """,
            {"industry_code": board["industry_code"], "trade_date": td},
        )
        for raw in reversed(sector_rows):
            row = serialize_row(raw)
            score, detail = _sector_sentiment_score(row)
            sector_items.append({**row, "score": score, "detail": detail})

    latest_market = market_items[-1] if market_items else None
    latest_sector = sector_items[-1] if sector_items else None
    return {
        "trade_date": td,
        "days": days,
        "board": board,
        "market": {
            "label": "大盘情绪",
            "latest_score": latest_market["score"] if latest_market else None,
            "items": market_items,
        },
        "sector": {
            "label": "板块情绪",
            "latest_score": latest_sector["score"] if latest_sector else None,
            "items": sector_items,
        },
    }
