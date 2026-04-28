"""用途：行业资金流 SQL 查询封装。"""
from datetime import date
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.orm import Session

from app.config import get_settings


def _is_no_such_table(exc: Exception) -> bool:
    orig = getattr(exc, "orig", exc)
    args = getattr(orig, "args", ())
    if args and args[0] == 1146:
        return True
    return "1146" in str(exc) and "doesn't exist" in str(exc)


def latest_trade_date(db: Session, on_or_before: date | None = None) -> date | None:
    s = get_settings()
    q = """
    SELECT MAX(trade_date) FROM industry_fund_flow_di
    WHERE period_type = :p
    """
    params: dict[str, Any] = {"p": s.period_instant}
    if on_or_before:
        q += " AND trade_date <= :d"
        params["d"] = on_or_before
    row = db.execute(text(q), params).fetchone()
    return row[0] if row and row[0] else None


def fund_flow_day(db: Session, trade_date: date) -> list[dict]:
    s = get_settings()
    rows = db.execute(
        text(
            """
            SELECT industry_name, industry_code, ranking_no, main_net_inflow,
                   industry_change_pct, industry_turnover, industry_index_value,
                   top_stock_name, top_stock_change_pct
            FROM industry_fund_flow_di
            WHERE trade_date = :d AND period_type = :p
            ORDER BY main_net_inflow DESC
            """
        ),
        {"d": trade_date, "p": s.period_instant},
    ).mappings().all()
    return [dict(r) for r in rows]


def fund_flow_range(db: Session, start: date, end: date) -> list[dict]:
    s = get_settings()
    rows = db.execute(
        text(
            """
            SELECT trade_date, industry_name, main_net_inflow, industry_change_pct, industry_turnover
            FROM industry_fund_flow_di
            WHERE trade_date BETWEEN :a AND :b AND period_type = :p
            """
        ),
        {"a": start, "b": end, "p": s.period_instant},
    ).mappings().all()
    return [dict(r) for r in rows]


def market_daily(db: Session, trade_date: date) -> dict | None:
    try:
        row = db.execute(
            text("SELECT * FROM market_daily_di WHERE trade_date = :d LIMIT 1"),
            {"d": trade_date},
        ).mappings().first()
        return dict(row) if row else None
    except (ProgrammingError, OperationalError) as exc:
        if _is_no_such_table(exc):
            return None
        raise


def industry_history(db: Session, industry_name: str, end: date, days: int = 20) -> list[dict]:
    s = get_settings()
    rows = db.execute(
        text(
            """
            SELECT trade_date, main_net_inflow, industry_change_pct, industry_turnover, industry_index_value
            FROM industry_fund_flow_di
            WHERE industry_name = :n AND period_type = :p AND trade_date <= :e
            ORDER BY trade_date DESC
            LIMIT :lim
            """
        ),
        {"n": industry_name, "p": s.period_instant, "e": end, "lim": days},
    ).mappings().all()
    return [dict(r) for r in rows][::-1]


def latent_scores(db: Session, trade_date: date, limit: int = 20) -> list[dict]:
    try:
        rows = db.execute(
            text(
                """
                SELECT industry_name, industry_code, total_score, latent_rank,
                       score_rank_today, score_sum5, score_turnover_amp, score_chg_strength,
                       risk_level, detail_json
                FROM industry_score_di
                WHERE trade_date = :d
                ORDER BY latent_rank ASC
                LIMIT :lim
                """
            ),
            {"d": trade_date, "lim": limit},
        ).mappings().all()
        return [dict(r) for r in rows]
    except (ProgrammingError, OperationalError) as exc:
        if _is_no_such_table(exc):
            return []
        raise
