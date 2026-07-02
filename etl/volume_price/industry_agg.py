"""东财板块量价聚合。"""
from __future__ import annotations

import logging
from datetime import date
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine

from etl.sector_dragon.db_util import list_boards, load_members
from etl.volume_price.db_util import VpConfig, list_trading_days

logger = logging.getLogger(__name__)


def _amount_metrics(
    engine: Engine,
    industry_code: str,
    trade_date: date,
    today_amount: float,
    window: int,
) -> tuple[float | None, int]:
    """返回 (industry_vol_ratio_20, amount_streak_days)。"""
    days = list_trading_days(engine, trade_date, window + 5)
    if not days:
        return None, 0
    start = days[0]
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT trade_date, total_amount
                FROM dwm_industry_vp_agg_di
                WHERE industry_code = :ic
                  AND trade_date BETWEEN :start AND :end
                  AND vp_window = :w
                ORDER BY trade_date
                """
            ),
            {"ic": industry_code, "start": start, "end": trade_date, "w": window},
        ).mappings().all()

    hist = {r["trade_date"]: float(r["total_amount"] or 0) for r in rows}
    hist[trade_date] = today_amount
    series_days = [d for d in days if d in hist]
    if not series_days:
        return None, 0
    amounts = [hist[d] for d in series_days]
    tail = amounts[-window:] if len(amounts) >= window else amounts
    ma = sum(tail) / len(tail) if tail else None
    vol_ratio = today_amount / ma if ma and ma > 0 else None

    streak = 0
    for d in reversed(series_days):
        amt = hist[d]
        prev_days = [x for x in series_days if x <= d][-window:]
        prev_amts = [hist[x] for x in prev_days]
        ma_d = sum(prev_amts) / len(prev_amts) if prev_amts else 0
        if ma_d > 0 and amt > ma_d:
            streak += 1
        else:
            break
    return vol_ratio, streak


def aggregate_board(
    engine: Engine,
    trade_date: date,
    board: dict[str, Any],
    factors: dict[str, dict[str, Any]],
    mv_map: dict[str, float],
    cfg: VpConfig,
) -> dict[str, Any] | None:
    member_date = board.get("member_date") or trade_date
    members = load_members(
        engine, trade_date, board["industry_code"], member_date=member_date
    )
    if not members:
        return None

    total_mv = 0.0
    total_amount = 0.0
    weighted_pct = 0.0
    rising = 0
    vol_expand = 0
    breakout = 0
    valid = 0
    weight_mode = "mv_weight"

    for m in members:
        f = factors.get(m["ts_code"])
        if not f:
            continue
        mv = mv_map.get(m["ts_code"])
        w = float(mv) if mv and mv > 0 else 1.0
        if not mv or mv <= 0:
            weight_mode = "equal"
        valid += 1
        amt = float(f.get("amount") or 0)
        pct = float(f.get("pct_chg") or 0)
        total_amount += amt
        total_mv += w
        weighted_pct += pct * w
        if pct > 0:
            rising += 1
        vr = f.get("vol_ratio_20")
        if vr is not None and float(vr) > 1.2:
            vol_expand += 1
        if int(f.get("is_breakout_60") or 0) == 1:
            breakout += 1

    if valid < cfg.min_member_cnt:
        return None

    avg_pct = weighted_pct / total_mv if total_mv > 0 else 0.0
    vol_ratio, streak = _amount_metrics(
        engine, board["industry_code"], trade_date, total_amount, cfg.window_default
    )
    return {
        "trade_date": trade_date,
        "industry_code": board["industry_code"],
        "industry_name": board.get("industry_name"),
        "content_type": board.get("content_type"),
        "member_cnt": valid,
        "total_amount": round(total_amount, 4),
        "avg_pct_chg": round(avg_pct, 6),
        "rising_ratio": round(rising / valid, 6),
        "vol_expand_ratio": round(vol_expand / valid, 6),
        "breakout_ratio": round(breakout / valid, 6),
        "industry_vol_ratio_20": round(vol_ratio, 6) if vol_ratio is not None else None,
        "amount_streak_days": streak,
        "weight_mode": weight_mode,
        "vp_window": cfg.window_default,
    }


def load_mv_map(engine: Engine, trade_date: date) -> dict[str, float]:
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT ts_code, circ_mv
                FROM ods_daily_basic_di
                WHERE trade_date = :td AND circ_mv IS NOT NULL
                """
            ),
            {"td": trade_date},
        ).mappings().all()
    return {r["ts_code"]: float(r["circ_mv"]) for r in rows}


def aggregate_industries(
    engine: Engine,
    trade_date: date,
    boards: list[dict[str, Any]],
    factors: list[dict[str, Any]],
    cfg: VpConfig,
) -> list[dict[str, Any]]:
    factor_map = {f["ts_code"]: f for f in factors}
    mv_map = load_mv_map(engine, trade_date)
    out: list[dict[str, Any]] = []
    skipped = 0
    for board in boards:
        row = aggregate_board(engine, trade_date, board, factor_map, mv_map, cfg)
        if row:
            out.append(row)
        else:
            skipped += 1
    logger.info(
        "industry_agg trade_date=%s ok=%d skipped=%d",
        trade_date,
        len(out),
        skipped,
    )
    return out


def list_target_boards(
    engine: Engine,
    trade_date: date,
    content_types: list[str],
    min_member_cnt: int,
) -> list[dict[str, Any]]:
    return list_boards(engine, trade_date, content_types, min_constituents=min_member_cnt)
