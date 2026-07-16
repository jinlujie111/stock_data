"""申万行业轮动回测：等权多头、周/月调仓，支持动量/反转状态机。"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date

import numpy as np
import pandas as pd

from etl.sector_rotation.engine import RegimeMachine, RotationConfig, score_date
from etl.sector_rotation.factors import SectorPanel

logger = logging.getLogger(__name__)
TRADING_DAYS_PER_YEAR = 252


@dataclass
class Position:
    units: float
    entry_px: float
    entry_date: date
    name: str
    hold_days: int = 0


@dataclass
class BacktestResult:
    trades: list[dict] = field(default_factory=list)
    nav: list[dict] = field(default_factory=list)
    holdings: list[dict] = field(default_factory=list)
    regimes: list[dict] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)


def _rebalance_dates(days: list[date], mode: str) -> set[date]:
    if not days:
        return set()
    if mode == "daily":
        return set(days)
    out: set[date] = {days[0]}
    if mode == "weekly":
        prev = days[0].isocalendar()[1]
        for d in days[1:]:
            wk = d.isocalendar()[1]
            if wk != prev:
                out.add(d)
                prev = wk
    elif mode == "monthly":
        prev = (days[0].year, days[0].month)
        for d in days[1:]:
            ym = (d.year, d.month)
            if ym != prev:
                out.add(d)
                prev = ym
    else:
        return set(days)
    return out


def _equal_weight_bench(panel: SectorPanel, days: list[date]) -> dict[date, float]:
    close = panel.close.reindex(days)
    rets = close.pct_change()
    nav = {}
    cur = 1.0
    for i, d in enumerate(days):
        if i == 0:
            nav[d] = 1.0
            continue
        r = rets.loc[d].dropna()
        cur *= 1.0 + float(r.mean()) if len(r) else 1.0
        nav[d] = cur
    return nav


def run_backtest(
    panel: SectorPanel,
    cfg: RotationConfig,
    start: date,
    end: date,
    benchmark: dict[date, float] | None = None,
) -> BacktestResult:
    days = panel.trading_days(start, end)
    if not days:
        raise RuntimeError(f"回测区间无交易日: {start} ~ {end}")
    rebal_set = _rebalance_dates(days, cfg.rebalance)
    rebal_list = [d for d in days if d in rebal_set]
    ew_bench = _equal_weight_bench(panel, days)
    machine = RegimeMachine(cfg)

    cash = float(cfg.init_capital)
    positions: dict[str, Position] = {}
    last_px: dict[str, float] = {}
    result = BacktestResult()
    nav_peak = 1.0
    bench_base: float | None = None
    current_regime = "momentum"

    def _px(d: date, code: str) -> float | None:
        try:
            v = panel.close_on(d).get(code)
            if v is None or (isinstance(v, float) and np.isnan(v)):
                return None
            return float(v)
        except KeyError:
            return None

    def _sell(code: str, price: float, d: date, reason: str):
        nonlocal cash
        pos = positions.pop(code)
        gross = pos.units * price
        cash += gross * (1 - cfg.sell_cost)
        pnl = pos.units * (price - pos.entry_px) - gross * cfg.sell_cost
        ret = (price / pos.entry_px - 1.0) if pos.entry_px else 0.0
        result.trades.append(
            {
                "ts_code": code,
                "name": pos.name,
                "side": "SELL",
                "trade_date": d,
                "price": round(price, 4),
                "units": round(pos.units, 4),
                "shares": None,
                "amount": round(gross, 2),
                "pnl": round(pnl, 2),
                "return_pct": round(ret, 4),
                "hold_days": pos.hold_days,
                "reason": reason,
            }
        )

    def _buy(code: str, name: str, price: float, alloc: float, d: date):
        nonlocal cash
        if price <= 0 or alloc <= 0:
            return
        units = alloc / (price * (1 + cfg.buy_cost))
        cost = units * price
        total = cost * (1 + cfg.buy_cost)
        if total > cash + 1e-6:
            units = cash / (price * (1 + cfg.buy_cost))
            cost = units * price
            total = cost * (1 + cfg.buy_cost)
        if units <= 0 or total > cash + 1e-6:
            return
        cash -= total
        positions[code] = Position(units=units, entry_px=price, entry_date=d, name=name)
        result.trades.append(
            {
                "ts_code": code,
                "name": name,
                "side": "BUY",
                "trade_date": d,
                "price": round(price, 4),
                "units": round(units, 4),
                "shares": None,
                "amount": round(cost, 2),
                "pnl": None,
                "return_pct": None,
                "hold_days": 0,
                "reason": "rebalance",
            }
        )

    rebal_idx_map = {d: i for i, d in enumerate(rebal_list)}

    for d in days:
        for code in panel.close.columns:
            px = _px(d, code)
            if px is not None:
                last_px[code] = px
        for pos in positions.values():
            pos.hold_days += 1

        if d in rebal_set:
            ri = rebal_idx_map[d]
            current_regime = machine.decide(panel, rebal_list, ri, days)
            ranked = score_date(d, panel, cfg, regime=current_regime)
            if not ranked.empty:
                buyable = ranked[ranked["can_buy"]]
                target = list(buyable.head(cfg.top_n)["ts_code"])
                name_map = dict(zip(ranked["ts_code"], ranked["name"]))

                for code in list(positions.keys()):
                    px = _px(d, code) or last_px.get(code)
                    if px:
                        _sell(code, px, d, "rebalance_reset")

                if target:
                    per = cash / len(target)
                    for code in target:
                        px = _px(d, code)
                        if not px:
                            continue
                        _buy(code, name_map.get(code, code), px, per, d)

                result.holdings.append(
                    {
                        "trade_date": d,
                        "regime": current_regime,
                        "codes": target,
                        "names": [name_map.get(c, c) for c in target],
                    }
                )

        pos_value = sum(
            p.units * (_px(d, c) or last_px.get(c, p.entry_px))
            for c, p in positions.items()
        )
        equity = cash + pos_value
        nav = equity / cfg.init_capital
        nav_peak = max(nav_peak, nav)
        dd = nav / nav_peak - 1.0

        bench_nav = None
        if benchmark and d in benchmark:
            if bench_base is None:
                bench_base = benchmark[d]
            if bench_base:
                bench_nav = benchmark[d] / bench_base

        result.nav.append(
            {
                "trade_date": d,
                "nav": round(nav, 6),
                "cash": round(cash, 2),
                "position_value": round(pos_value, 2),
                "bench_nav": round(bench_nav, 6) if bench_nav is not None else None,
                "ew_nav": round(ew_bench.get(d, 1.0), 6),
                "drawdown": round(dd, 6),
                "n_pos": len(positions),
                "regime": current_regime,
            }
        )

    last = days[-1]
    for code in list(positions.keys()):
        px = _px(last, code) or last_px.get(code)
        if px:
            _sell(code, px, last, "final")

    result.regimes = list(machine.history)
    result.metrics = _compute_metrics(result.nav, result.trades, len(days), result.holdings)
    return result


def _compute_metrics(
    nav_rows: list[dict], trades: list[dict], n_days: int, holdings: list[dict]
) -> dict:
    if not nav_rows:
        return {}
    navs = np.array([r["nav"] for r in nav_rows], dtype=float)
    total_return = float(navs[-1] - 1.0)
    years = max(n_days, 1) / TRADING_DAYS_PER_YEAR
    annual = float(navs[-1] ** (1.0 / years) - 1.0) if navs[-1] > 0 and years > 0 else None
    peak = np.maximum.accumulate(navs)
    max_dd = float(np.min(navs / peak - 1.0)) if len(navs) else 0.0
    rets = np.diff(navs) / navs[:-1] if len(navs) > 1 else np.array([])
    sharpe = None
    if rets.size > 1 and rets.std() > 1e-9:
        sharpe = float(rets.mean() / rets.std() * np.sqrt(TRADING_DAYS_PER_YEAR))
    closed = [t for t in trades if t["side"] == "SELL" and t.get("pnl") is not None]
    wins = [t for t in closed if (t.get("pnl") or 0) > 0]
    win_rate = float(len(wins) / len(closed)) if closed else None

    def _series_ret(key: str) -> float | None:
        vals = [r[key] for r in nav_rows if r.get(key) is not None]
        if len(vals) >= 2:
            return float(vals[-1] / vals[0] - 1.0)
        return None

    bench_return = _series_ret("bench_nav")
    ew_return = _series_ret("ew_nav")
    excess_vs_300 = (total_return - bench_return) if bench_return is not None else None
    excess_vs_ew = (total_return - ew_return) if ew_return is not None else None

    n_mom = sum(1 for h in holdings if h.get("regime") == "momentum")
    n_rev = sum(1 for h in holdings if h.get("regime") == "reversal")

    return {
        "total_return": round(total_return, 4),
        "annual_return": round(annual, 4) if annual is not None else None,
        "max_drawdown": round(max_dd, 4),
        "sharpe": round(sharpe, 4) if sharpe is not None else None,
        "win_rate": round(win_rate, 4) if win_rate is not None else None,
        "trade_count": len(closed),
        "bench_return": round(bench_return, 4) if bench_return is not None else None,
        "ew_return": round(ew_return, 4) if ew_return is not None else None,
        "excess_vs_300": round(excess_vs_300, 4) if excess_vs_300 is not None else None,
        "excess_vs_ew": round(excess_vs_ew, 4) if excess_vs_ew is not None else None,
        "n_days": n_days,
        "regime_momentum_weeks": n_mom,
        "regime_reversal_weeks": n_rev,
    }
