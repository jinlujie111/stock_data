"""回测引擎：等权多头、复权价空间撮合，支持日/周/月调仓与风控退出。

约定：
- 全程在「后复权价」空间计算，收益率对送转除权一致；展示价即复权价。
- 决策与成交同用当日收盘价（close-to-close），MVP 口径，含轻微同日执行假设。
- 成本：买入佣金 0.0003；卖出佣金 0.0003 + 印花税 0.0005。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date

import numpy as np
import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine

from etl.quant.db_util import iso, list_trading_days, trading_days_before
from etl.quant.engine import StrategyConfig, score_date
from etl.quant.factors import PricePanel, StockMeta, load_fundamental_asof, load_price_panel

logger = logging.getLogger(__name__)

BUY_COST = 0.0003
SELL_COST = 0.0003 + 0.0005
BENCH_CODE = "000300.SH"
TRADING_DAYS_PER_YEAR = 252


@dataclass
class Position:
    shares: float
    entry_adj: float
    entry_date: date
    name: str
    hold_days: int = 0


@dataclass
class BacktestResult:
    trades: list[dict] = field(default_factory=list)
    nav: list[dict] = field(default_factory=list)
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


def _load_benchmark(engine: Engine, start: date, end: date) -> dict[date, float]:
    sql = """
        SELECT trade_date, close FROM ods_index_daily_di
        WHERE ts_code = :c AND trade_date BETWEEN :s AND :e
        ORDER BY trade_date ASC
    """
    try:
        with engine.connect() as conn:
            rows = conn.execute(
                text(sql), {"c": BENCH_CODE, "s": iso(start), "e": iso(end)}
            ).fetchall()
    except Exception as exc:
        logger.warning("基准指数读取失败，忽略基准: %s", exc)
        return {}
    out: dict[date, float] = {}
    for r in rows:
        d = r[0]
        d = d if isinstance(d, date) else pd.to_datetime(d).date()
        if r[1] is not None:
            out[d] = float(r[1])
    return out


def run_backtest(
    cfg: StrategyConfig,
    start: date,
    end: date,
    init_capital: float,
    stock_engine: Engine,
    meta: dict[str, StockMeta],
    panel: PricePanel,
) -> BacktestResult:
    days = list_trading_days(stock_engine, start, end)
    if not days:
        raise RuntimeError(f"回测区间无交易日: {start} ~ {end}")
    rebal = _rebalance_dates(days, cfg.rebalance)
    bench = _load_benchmark(stock_engine, days[0], days[-1])
    fund_cache: dict[date, pd.DataFrame] = {}

    def _fund(d: date) -> pd.DataFrame | None:
        if not cfg.needs_fundamentals():
            return None
        if d not in fund_cache:
            fund_cache[d] = load_fundamental_asof(stock_engine, d)
        return fund_cache[d]

    cash = float(init_capital)
    positions: dict[str, Position] = {}
    last_adj: dict[str, float] = {}
    result = BacktestResult()
    nav_peak = 1.0
    bench_base: float | None = None

    def _slice_maps(d: date):
        day = panel.slice(d)
        adj = {}
        ama20 = {}
        uplimit = {}
        close_actual = {}
        for _, r in day.iterrows():
            code = r["ts_code"]
            if pd.notna(r["adj_close"]):
                adj[code] = float(r["adj_close"])
            ama20[code] = r.get("above_ma20")
            uplimit[code] = r.get("up_limit_hit")
            if pd.notna(r["close"]):
                close_actual[code] = float(r["close"])
        return day, adj, ama20, uplimit, close_actual

    def _sell(code: str, price: float, d: date, reason: str):
        nonlocal cash
        pos = positions.pop(code)
        gross = pos.shares * price
        cash += gross * (1 - SELL_COST)
        pnl = pos.shares * (price - pos.entry_adj) - gross * SELL_COST
        ret = (price / pos.entry_adj - 1.0) if pos.entry_adj else 0.0
        result.trades.append(
            {
                "ts_code": code,
                "stock_name": pos.name,
                "side": "SELL",
                "trade_date": d,
                "price": round(price, 4),
                "shares": int(pos.shares),
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
        shares = np.floor(alloc / (price * (1 + BUY_COST)) / 100.0) * 100.0
        if shares <= 0:
            return
        cost = shares * price
        total = cost * (1 + BUY_COST)
        if total > cash:
            return
        cash -= total
        positions[code] = Position(
            shares=shares, entry_adj=price, entry_date=d, name=name
        )
        result.trades.append(
            {
                "ts_code": code,
                "stock_name": name,
                "side": "BUY",
                "trade_date": d,
                "price": round(price, 4),
                "shares": int(shares),
                "amount": round(cost, 2),
                "pnl": None,
                "return_pct": None,
                "hold_days": 0,
                "reason": "rebalance",
            }
        )

    for d in days:
        day, adj, ama20, uplimit, _close_actual = _slice_maps(d)
        for code, px in adj.items():
            last_adj[code] = px

        # 累计持有交易日
        for pos in positions.values():
            pos.hold_days += 1

        # ---- 风控退出（每日收盘检查）----
        for code in list(positions.keys()):
            pos = positions[code]
            px = adj.get(code, last_adj.get(code))
            if px is None or pos.entry_adj <= 0:
                continue
            ret = px / pos.entry_adj - 1.0
            reason = None
            if cfg.stop_loss is not None and ret <= cfg.stop_loss:
                reason = "stop_loss"
            elif cfg.take_profit is not None and ret >= cfg.take_profit:
                reason = "take_profit"
            elif cfg.max_hold_days is not None and pos.hold_days >= cfg.max_hold_days:
                reason = "max_hold"
            elif cfg.exit_rule == "ma20_break" and ama20.get(code) == 0:
                reason = "exit_rule"
            if reason:
                _sell(code, px, d, reason)

        # ---- 调仓 ----
        if d in rebal:
            ranked = score_date(d, panel, meta, stock_engine, cfg, fundamentals=_fund(d))
            if not ranked.empty:
                buyable = ranked[ranked["can_buy"]]
                target = list(buyable.head(cfg.top_n)["ts_code"])
                target_set = set(target)
                name_map = dict(zip(ranked["ts_code"], ranked.get("stock_name", ranked["ts_code"])))
                # 卖出不在目标中的持仓
                for code in list(positions.keys()):
                    if code not in target_set:
                        px = adj.get(code, last_adj.get(code))
                        if px:
                            _sell(code, px, d, "rebalance")
                # 买入新增目标（等权，按当前总权益/目标数分配）
                equity = cash + sum(
                    p.shares * adj.get(c, last_adj.get(c, p.entry_adj))
                    for c, p in positions.items()
                )
                slots = [c for c in target if c not in positions]
                if slots:
                    per = equity / cfg.top_n
                    for code in slots:
                        px = adj.get(code)
                        if not px:
                            continue
                        nm = meta.get(code).name if meta.get(code) else name_map.get(code, code)
                        _buy(code, nm, px, min(per, cash), d)

        # ---- 记录净值 ----
        pos_value = sum(
            p.shares * adj.get(c, last_adj.get(c, p.entry_adj))
            for c, p in positions.items()
        )
        equity = cash + pos_value
        nav = equity / init_capital
        nav_peak = max(nav_peak, nav)
        dd = nav / nav_peak - 1.0
        bench_nav = None
        if d in bench:
            if bench_base is None:
                bench_base = bench[d]
            if bench_base:
                bench_nav = bench[d] / bench_base
        result.nav.append(
            {
                "trade_date": d,
                "nav": round(nav, 6),
                "cash": round(cash, 2),
                "position_value": round(pos_value, 2),
                "bench_nav": round(bench_nav, 6) if bench_nav is not None else None,
                "drawdown": round(dd, 6),
            }
        )

    # ---- 期末清仓（用最后交易日复权价）----
    last_day = days[-1]
    _, adj_last, _, _, _ = _slice_maps(last_day)
    for code in list(positions.keys()):
        px = adj_last.get(code, last_adj.get(code))
        if px:
            _sell(code, px, last_day, "final")

    result.metrics = _compute_metrics(result.nav, result.trades, len(days))
    return result


def _compute_metrics(nav_rows: list[dict], trades: list[dict], n_days: int) -> dict:
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
    wins = [t for t in closed if t["pnl"] > 0]
    win_rate = float(len(wins) / len(closed)) if closed else None
    bench_return = None
    bench_navs = [r["bench_nav"] for r in nav_rows if r.get("bench_nav") is not None]
    if len(bench_navs) >= 2:
        bench_return = float(bench_navs[-1] / bench_navs[0] - 1.0)
    return {
        "total_return": round(total_return, 4),
        "annual_return": round(annual, 4) if annual is not None else None,
        "max_drawdown": round(max_dd, 4),
        "sharpe": round(sharpe, 4) if sharpe is not None else None,
        "win_rate": round(win_rate, 4) if win_rate is not None else None,
        "trade_count": len(closed),
        "bench_return": round(bench_return, 4) if bench_return is not None else None,
    }


def load_panel_with_lookback(
    stock_engine: Engine, start: date, end: date, lookback_td: int = 130
) -> PricePanel:
    """加载含前置回溯的行情面板（保证 mom120/ma60 可算）。"""
    pad = trading_days_before(stock_engine, start, lookback_td)
    panel_start = pad[0] if pad else start
    return load_price_panel(stock_engine, panel_start, end)
