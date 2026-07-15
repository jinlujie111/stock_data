"""东财板块量价聚合。"""
from __future__ import annotations

import logging
import statistics
from collections import defaultdict
from datetime import date
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine

from etl.sector_dragon.db_util import list_boards, load_members
from etl.volume_price.db_util import VpConfig, list_trading_days

logger = logging.getLogger(__name__)


def _code_variants(industry_code: str) -> list[str]:
    code = industry_code.strip()
    if code.endswith(".DC"):
        return [code, code[:-3]]
    return [code, f"{code}.DC"]


def load_board_close_map(
    engine: Engine,
    boards: list[dict[str, Any]],
    trade_date: date,
    window: int,
) -> dict[str, dict[date, float]]:
    """板块指数 close 序列，key=industry_code。"""
    days = list_trading_days(engine, trade_date, window + 1)
    if not days:
        return {}
    variant_to_ic: dict[str, str] = {}
    variants: set[str] = set()
    for board in boards:
        ic = board["industry_code"]
        for v in _code_variants(ic):
            variants.add(v)
            variant_to_ic[v] = ic
    if not variants:
        return {}
    placeholders = ", ".join(f":c{i}" for i in range(len(variants)))
    params: dict[str, Any] = {
        "start": days[0],
        "end": trade_date,
        **{f"c{i}": c for i, c in enumerate(sorted(variants))},
    }
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                f"""
                SELECT ts_code, trade_date, close
                FROM ods_dc_daily_di
                WHERE trade_date BETWEEN :start AND :end
                  AND ts_code IN ({placeholders})
                """
            ),
            params,
        ).mappings().all()
    out: dict[str, dict[date, float]] = defaultdict(dict)
    for r in rows:
        ic = variant_to_ic.get(str(r["ts_code"]))
        if not ic or r["close"] is None:
            continue
        out[ic][r["trade_date"]] = float(r["close"])
    return out


def _board_trend_return_20d(
    close_map: dict[date, float],
    trade_date: date,
    lag_date: date | None,
) -> float | None:
    if not lag_date:
        return None
    c0 = close_map.get(lag_date)
    c1 = close_map.get(trade_date)
    if c0 is None or c1 is None or c0 <= 0:
        return None
    return round((c1 / c0 - 1) * 100.0, 6)


def _amount_metrics(
    engine: Engine,
    industry_code: str,
    trade_date: date,
    today_amount: float,
    window: int,
) -> tuple[float | None, int, float]:
    """返回 (industry_vol_ratio_20, amount_streak_days, continuity_strength)。"""
    days = list_trading_days(engine, trade_date, window + 30)
    if not days:
        return None, 0, 0.0
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
        return None, 0, 0.0

    # 成交额比(industry_vol_ratio_20)基准均线排除当日：只用 T-1..T-N 的历史成交额均值，
    # 避免把当日 today_amount 算进分母自我参照压低比值。
    prior_days = [d for d in series_days if d < trade_date]
    tail = prior_days[-window:] if len(prior_days) >= window else prior_days
    prior_amounts = [hist[d] for d in tail]
    ma = sum(prior_amounts) / len(prior_amounts) if prior_amounts else None
    vol_ratio = today_amount / ma if ma and ma > 0 else None

    streak = 0
    strength = 0.0
    streak_day = 0
    for d in reversed(series_days):
        amt = hist[d]
        # 断裂判定的基准均线排除当日 d 自身（用 x < d），口径与成交额比一致，
        # 避免 ma_d 含 amt 造成自我参照。
        prev_days = [x for x in series_days if x < d][-window:]
        prev_amts = [hist[x] for x in prev_days]
        ma_d = sum(prev_amts) / len(prev_amts) if prev_amts else 0
        if ma_d <= 0 or amt <= ma_d:
            break
        streak += 1
        streak_day += 1
        excess = amt / ma_d - 1
        decay = 1.0 if streak_day <= 5 else 0.8 ** (streak_day - 5)
        strength += streak_day * excess * decay

    return vol_ratio, streak, round(strength, 6)


def aggregate_board(
    engine: Engine,
    trade_date: date,
    board: dict[str, Any],
    factors: dict[str, dict[str, Any]],
    mv_map: dict[str, float],
    cfg: VpConfig,
    board_closes: dict[str, dict[date, float]],
    lag_date: date | None,
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
    rising_mv = 0.0
    vol_expand = 0
    breakout_amount = 0.0
    valid = 0
    # 权重策略先判定：仅当全部成分都缺流通市值时才等权，否则统一按市值加权，
    # 避免“部分缺 mv 就整体标 equal 却仍混用 mv 与 w=1”。
    has_any_mv = any(
        (mv_map.get(m["ts_code"]) or 0) > 0
        for m in members
        if factors.get(m["ts_code"])
    )
    weight_mode = "mv_weight" if has_any_mv else "equal"
    # member_stats: (mv_value, mv_present, pct_chg, vol_ratio_or_None)，用于龙头强度计算。
    member_stats: list[tuple[float, bool, float, float | None]] = []

    for m in members:
        f = factors.get(m["ts_code"])
        if not f:
            continue
        valid += 1
        amt = float(f.get("amount") or 0)
        pct = float(f.get("pct_chg") or 0)
        total_amount += amt
        if f.get("vol_ratio_20") is not None and float(f["vol_ratio_20"]) > 1.2:
            vol_expand += 1
        if int(f.get("is_breakout_strict") or 0) == 1:
            breakout_amount += amt

        mv = mv_map.get(m["ts_code"])
        mv_present = bool(mv and mv > 0)
        if weight_mode == "equal":
            w = 1.0
        else:
            # mv 加权模式下缺市值成分权重记 0（不计入加权聚合），不再用 w=1 混入 mv 量纲。
            w = float(mv) if mv_present else 0.0
        if w > 0:
            total_mv += w
            weighted_pct += pct * w
            if pct > 0:
                rising_mv += w

        vr_val = float(f["vol_ratio_20"]) if f.get("vol_ratio_20") is not None else None
        member_stats.append((float(mv) if mv_present else 0.0, mv_present, pct, vr_val))

    if valid < cfg.min_member_cnt:
        return None

    avg_pct = weighted_pct / total_mv if total_mv > 0 else 0.0
    # rising_ratio 实为“市值加权（或等权）上涨权重占比”，非简单上涨家数占比，字段名保留、口径见此注释。
    rising_ratio = rising_mv / total_mv if total_mv > 0 else 0.0
    breakout_ratio = breakout_amount / total_amount if total_amount > 0 else 0.0

    vol_ratio, streak, continuity_strength = _amount_metrics(
        engine, board["industry_code"], trade_date, total_amount, cfg.window_default
    )

    ic = board["industry_code"]
    close_map = board_closes.get(ic, {})
    trend_return_20d = _board_trend_return_20d(close_map, trade_date, lag_date)

    # 龙头强度：涨跌幅(%)与量比(~1.x)量纲不同，不能直接平均。改为：
    # 1) top3 只在“有真实市值”的成分里按 mv 取（缺 mv 者不进 top3）；
    # 2) 涨跌幅、量比各自按板块内 z-score 标准化后再合成，消除量纲差异；
    # 3) 量比缺失的成分按中性 0（z-score 0）处理，不再当 0 拉低。
    def _zscore(x: float | None, arr: list[float]) -> float:
        if x is None or len(arr) < 2:
            return 0.0
        sd = statistics.pstdev(arr)
        return (x - statistics.mean(arr)) / sd if sd > 0 else 0.0

    leader_strength = None
    mv_members = [s for s in member_stats if s[1]]
    if mv_members:
        pcts = [s[2] for s in member_stats]
        vrs = [s[3] for s in member_stats if s[3] is not None]
        mv_members.sort(key=lambda s: s[0], reverse=True)
        top3 = mv_members[:3]
        z_list = []
        for s in top3:
            z_pct = _zscore(s[2], pcts)
            z_vr = _zscore(s[3], vrs) if s[3] is not None else 0.0
            z_list.append((z_pct + z_vr) / 2.0)
        leader_strength = round(sum(z_list) / len(z_list), 6)

    return {
        "trade_date": trade_date,
        "industry_code": ic,
        "industry_name": board.get("industry_name"),
        "content_type": board.get("content_type"),
        "member_cnt": valid,
        "total_amount": round(total_amount, 4),
        "avg_pct_chg": round(avg_pct, 6),
        "rising_ratio": round(rising_ratio, 6),
        "vol_expand_ratio": round(vol_expand / valid, 6),
        "breakout_ratio": round(breakout_ratio, 6),
        "industry_vol_ratio_20": round(vol_ratio, 6) if vol_ratio is not None else None,
        "amount_streak_days": streak,
        "continuity_strength": continuity_strength,
        "trend_return_20d": trend_return_20d,
        "leader_strength": leader_strength,
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
    window = cfg.window_default
    days = list_trading_days(engine, trade_date, window + 1)
    lag_date = days[0] if len(days) >= window + 1 else (days[0] if days else None)
    board_closes = load_board_close_map(engine, boards, trade_date, window)

    out: list[dict[str, Any]] = []
    skipped = 0
    for board in boards:
        row = aggregate_board(
            engine,
            trade_date,
            board,
            factor_map,
            mv_map,
            cfg,
            board_closes,
            lag_date,
        )
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
