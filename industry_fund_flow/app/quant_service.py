"""量化选股 Web 服务：策略 / 每日信号 / 回测 / 买卖点历史。

- 策略、信号、回测结果、买卖点均存 data_industry（app.db 可读写）。
- 因子/行情从 stock_data 只读（app.db.fetch_*_stock / get_stock_engine）。
- 回测在后台线程执行，前端轮询状态。
"""
from __future__ import annotations

import json
import logging
import sys
import threading
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import text

from app.db import execute, fetch_all, fetch_all_stock, fetch_one, fetch_one_stock, get_engine, get_stock_engine

# 使 etl.quant 可导入（仓库根 + dw-utils）
_REPO_ROOT = Path(__file__).resolve().parents[2]
for _p in (_REPO_ROOT, _REPO_ROOT / "dw-utils"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

logger = logging.getLogger(__name__)

DEFAULT_INIT_CAPITAL = 1_000_000.0


def _serialize(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()[:10]
    if isinstance(value, Decimal):
        return float(value)
    return value


def _row(row: dict) -> dict:
    return {k: _serialize(v) for k, v in row.items()}


def _iso(d: str) -> str:
    s = str(d).strip().replace("-", "")
    if len(s) != 8:
        raise ValueError(f"日期格式应为 YYYYMMDD 或 YYYY-MM-DD: {d}")
    return f"{s[:4]}-{s[4:6]}-{s[6:8]}"


# --------------------------------------------------------------------------
# 策略
# --------------------------------------------------------------------------
def list_strategies(user_id: int) -> list[dict]:
    rows = fetch_all(
        """
        SELECT id, code, name, horizon, description, config_json,
               is_system, is_active, owner_user_id, updated_at
        FROM quant_strategy
        WHERE is_system = 1 OR owner_user_id = :uid
        ORDER BY is_system DESC, id ASC
        """,
        {"uid": user_id},
    )
    out = []
    for r in rows:
        item = _row(r)
        try:
            item["config"] = json.loads(r["config_json"]) if r.get("config_json") else {}
        except Exception:
            item["config"] = {}
        item.pop("config_json", None)
        out.append(item)
    return out


def get_strategy(strategy_id: int) -> dict | None:
    r = fetch_one("SELECT * FROM quant_strategy WHERE id = :id", {"id": strategy_id})
    if not r:
        return None
    item = _row(r)
    try:
        item["config"] = json.loads(r["config_json"]) if r.get("config_json") else {}
    except Exception:
        item["config"] = {}
    return item


def _validate_config(config: Any) -> str:
    if isinstance(config, str):
        try:
            data = json.loads(config)
        except Exception as exc:
            raise ValueError(f"config 不是合法 JSON: {exc}") from exc
    elif isinstance(config, dict):
        data = config
    else:
        raise ValueError("config 必须为 JSON 对象或字符串")
    if not data.get("factors"):
        raise ValueError("config.factors 不能为空")
    if not (data.get("select") or {}).get("top_n"):
        raise ValueError("config.select.top_n 必填")
    return json.dumps(data, ensure_ascii=False)


def create_strategy(
    user_id: int, code: str, name: str, horizon: str, description: str | None, config: Any
) -> dict:
    if not code or not code.strip():
        raise ValueError("code 必填")
    if not name or not name.strip():
        raise ValueError("name 必填")
    cfg_json = _validate_config(config)
    execute(
        """
        INSERT INTO quant_strategy
            (code, name, horizon, description, config_json, is_system, is_active, owner_user_id)
        VALUES (:code, :name, :horizon, :desc, :cfg, 0, 1, :uid)
        """,
        {
            "code": code.strip(),
            "name": name.strip(),
            "horizon": horizon if horizon in ("short", "long") else "short",
            "desc": description,
            "cfg": cfg_json,
            "uid": user_id,
        },
    )
    r = fetch_one(
        "SELECT * FROM quant_strategy WHERE code = :code", {"code": code.strip()}
    )
    return get_strategy(r["id"]) if r else {"code": code}


def update_strategy(
    user_id: int, strategy_id: int, *, name=None, description=None, config=None, is_active=None
) -> dict:
    r = fetch_one("SELECT * FROM quant_strategy WHERE id = :id", {"id": strategy_id})
    if not r:
        raise ValueError("策略不存在")
    if r["is_system"]:
        raise ValueError("系统内置策略不可修改")
    if r["owner_user_id"] != user_id:
        raise ValueError("无权修改该策略")
    sets = []
    params: dict[str, Any] = {"id": strategy_id}
    if name is not None:
        sets.append("name = :name")
        params["name"] = name
    if description is not None:
        sets.append("description = :desc")
        params["desc"] = description
    if config is not None:
        sets.append("config_json = :cfg")
        params["cfg"] = _validate_config(config)
    if is_active is not None:
        sets.append("is_active = :act")
        params["act"] = 1 if is_active else 0
    if sets:
        execute(f"UPDATE quant_strategy SET {', '.join(sets)} WHERE id = :id", params)
    return get_strategy(strategy_id)


def delete_strategy(user_id: int, strategy_id: int) -> bool:
    r = fetch_one("SELECT * FROM quant_strategy WHERE id = :id", {"id": strategy_id})
    if not r:
        return False
    if r["is_system"]:
        raise ValueError("系统内置策略不可删除")
    if r["owner_user_id"] != user_id:
        raise ValueError("无权删除该策略")
    n = execute("DELETE FROM quant_strategy WHERE id = :id", {"id": strategy_id})
    return n > 0


# --------------------------------------------------------------------------
# 每日信号
# --------------------------------------------------------------------------
def signal_trade_dates(strategy_id: int, limit: int = 60) -> list[str]:
    rows = fetch_all(
        f"""
        SELECT DISTINCT trade_date FROM quant_signal_di
        WHERE strategy_id = :sid
        ORDER BY trade_date DESC LIMIT {int(limit)}
        """,
        {"sid": strategy_id},
    )
    return [_serialize(r["trade_date"]) for r in rows]


def list_signals(strategy_id: int, trade_date: str | None = None) -> dict:
    if trade_date:
        td = _iso(trade_date)
    else:
        row = fetch_one(
            "SELECT MAX(trade_date) AS d FROM quant_signal_di WHERE strategy_id = :sid",
            {"sid": strategy_id},
        )
        td = _serialize(row["d"]) if row and row.get("d") else None
    if not td:
        return {"trade_date": None, "items": []}
    rows = fetch_all(
        """
        SELECT ts_code, stock_name, action, rank_no, score, close, factor_json
        FROM quant_signal_di
        WHERE strategy_id = :sid AND trade_date = :td
        ORDER BY (action='SELL') ASC, rank_no ASC
        """,
        {"sid": strategy_id, "td": td},
    )
    items = []
    for r in rows:
        item = _row(r)
        try:
            item["factors"] = json.loads(r["factor_json"]) if r.get("factor_json") else {}
        except Exception:
            item["factors"] = {}
        item.pop("factor_json", None)
        items.append(item)
    return {"trade_date": td, "items": items}


# --------------------------------------------------------------------------
# 回测
# --------------------------------------------------------------------------
_running_lock = threading.Lock()


def create_backtest(
    user_id: int, strategy_id: int, start_date: str, end_date: str, init_capital: float, name: str | None
) -> int:
    strat = fetch_one("SELECT * FROM quant_strategy WHERE id = :id", {"id": strategy_id})
    if not strat:
        raise ValueError("策略不存在")
    s = _iso(start_date)
    e = _iso(end_date)
    if s > e:
        s, e = e, s
    cap = float(init_capital) if init_capital else DEFAULT_INIT_CAPITAL
    execute(
        """
        INSERT INTO quant_backtest_run
            (strategy_id, owner_user_id, name, start_date, end_date, init_capital, params_json, status)
        VALUES (:sid, :uid, :name, :s, :e, :cap, :params, 'pending')
        """,
        {
            "sid": strategy_id,
            "uid": user_id,
            "name": name or f"{strat['name']} {s}~{e}",
            "s": s,
            "e": e,
            "cap": cap,
            "params": strat["config_json"],
        },
    )
    row = fetch_one(
        """
        SELECT id FROM quant_backtest_run
        WHERE owner_user_id = :uid AND strategy_id = :sid
        ORDER BY id DESC LIMIT 1
        """,
        {"uid": user_id, "sid": strategy_id},
    )
    run_id = int(row["id"])
    t = threading.Thread(
        target=_run_backtest_worker,
        args=(run_id, strat["config_json"], s, e, cap),
        daemon=True,
    )
    t.start()
    return run_id


def _run_backtest_worker(run_id: int, config_json: str, s: str, e: str, cap: float) -> None:
    from etl.quant.engine import StrategyConfig
    from etl.quant.backtest import run_backtest, load_panel_with_lookback
    from etl.quant.factors import load_stock_meta
    from etl.quant.db_util import parse_trade_date

    try:
        execute("UPDATE quant_backtest_run SET status='running' WHERE id=:id", {"id": run_id})
        cfg = StrategyConfig.from_json(config_json)
        stock_engine = get_stock_engine()
        start = parse_trade_date(s)
        end = parse_trade_date(e)
        meta = load_stock_meta(stock_engine)
        panel = load_panel_with_lookback(stock_engine, start, end)
        result = run_backtest(cfg, start, end, cap, stock_engine, meta, panel)
        _persist_backtest(run_id, result)
        m = result.metrics
        execute(
            """
            UPDATE quant_backtest_run SET
                status='done', total_return=:tr, annual_return=:ar, max_drawdown=:md,
                sharpe=:sh, win_rate=:wr, trade_count=:tc, bench_return=:br,
                finished_at=NOW()
            WHERE id=:id
            """,
            {
                "id": run_id,
                "tr": m.get("total_return"),
                "ar": m.get("annual_return"),
                "md": m.get("max_drawdown"),
                "sh": m.get("sharpe"),
                "wr": m.get("win_rate"),
                "tc": m.get("trade_count"),
                "br": m.get("bench_return"),
            },
        )
        logger.info("回测 %s 完成: %s", run_id, m)
    except Exception as exc:  # noqa: BLE001
        logger.exception("回测 %s 失败", run_id)
        execute(
            "UPDATE quant_backtest_run SET status='failed', error_msg=:msg, finished_at=NOW() WHERE id=:id",
            {"id": run_id, "msg": str(exc)[:500]},
        )


def _persist_backtest(run_id: int, result) -> None:
    eng = get_engine()
    with eng.begin() as conn:
        conn.execute(text("DELETE FROM quant_backtest_trade WHERE run_id=:id"), {"id": run_id})
        conn.execute(text("DELETE FROM quant_backtest_nav WHERE run_id=:id"), {"id": run_id})
        trade_rows = [
            {
                "run_id": run_id,
                "ts_code": t["ts_code"],
                "stock_name": t.get("stock_name"),
                "side": t["side"],
                "trade_date": t["trade_date"],
                "price": t["price"],
                "shares": t.get("shares"),
                "amount": t.get("amount"),
                "pnl": t.get("pnl"),
                "return_pct": t.get("return_pct"),
                "hold_days": t.get("hold_days"),
                "reason": t.get("reason"),
            }
            for t in result.trades
        ]
        if trade_rows:
            ins = text(
                """
                INSERT INTO quant_backtest_trade
                    (run_id, ts_code, stock_name, side, trade_date, price, shares, amount,
                     pnl, return_pct, hold_days, reason)
                VALUES (:run_id, :ts_code, :stock_name, :side, :trade_date, :price, :shares,
                        :amount, :pnl, :return_pct, :hold_days, :reason)
                """
            )
            for i in range(0, len(trade_rows), 500):
                conn.execute(ins, trade_rows[i : i + 500])
        nav_rows = [
            {
                "run_id": run_id,
                "trade_date": n["trade_date"],
                "nav": n["nav"],
                "cash": n.get("cash"),
                "position_value": n.get("position_value"),
                "bench_nav": n.get("bench_nav"),
                "drawdown": n.get("drawdown"),
            }
            for n in result.nav
        ]
        if nav_rows:
            insn = text(
                """
                INSERT INTO quant_backtest_nav
                    (run_id, trade_date, nav, cash, position_value, bench_nav, drawdown)
                VALUES (:run_id, :trade_date, :nav, :cash, :position_value, :bench_nav, :drawdown)
                """
            )
            for i in range(0, len(nav_rows), 500):
                conn.execute(insn, nav_rows[i : i + 500])


def list_backtests(user_id: int, limit: int = 30) -> list[dict]:
    rows = fetch_all(
        f"""
        SELECT r.id, r.strategy_id, s.name AS strategy_name, r.name, r.start_date, r.end_date,
               r.init_capital, r.status, r.total_return, r.annual_return, r.max_drawdown,
               r.sharpe, r.win_rate, r.trade_count, r.bench_return, r.error_msg, r.created_at
        FROM quant_backtest_run r
        LEFT JOIN quant_strategy s ON s.id = r.strategy_id
        WHERE r.owner_user_id = :uid
        ORDER BY r.id DESC LIMIT {int(limit)}
        """,
        {"uid": user_id},
    )
    return [_row(r) for r in rows]


def get_backtest(user_id: int, run_id: int) -> dict | None:
    r = fetch_one(
        """
        SELECT r.*, s.name AS strategy_name FROM quant_backtest_run r
        LEFT JOIN quant_strategy s ON s.id = r.strategy_id
        WHERE r.id = :id AND r.owner_user_id = :uid
        """,
        {"id": run_id, "uid": user_id},
    )
    if not r:
        return None
    out = _row(r)
    out.pop("params_json", None)
    nav = fetch_all(
        "SELECT trade_date, nav, bench_nav, drawdown FROM quant_backtest_nav "
        "WHERE run_id = :id ORDER BY trade_date ASC",
        {"id": run_id},
    )
    trades = fetch_all(
        "SELECT ts_code, stock_name, side, trade_date, price, shares, amount, pnl, "
        "return_pct, hold_days, reason FROM quant_backtest_trade "
        "WHERE run_id = :id ORDER BY trade_date ASC, side DESC",
        {"id": run_id},
    )
    out["nav"] = [_row(x) for x in nav]
    out["trades"] = [_row(x) for x in trades]
    return out


# --------------------------------------------------------------------------
# 买卖点历史 / 持仓
# --------------------------------------------------------------------------
def add_trade(
    user_id: int, ts_code: str, side: str, trade_date: str, price: float,
    shares: int | None, stock_name: str | None, note: str | None,
    source: str = "manual", strategy_id: int | None = None,
) -> dict:
    if not ts_code or not ts_code.strip():
        raise ValueError("ts_code 必填")
    if side not in ("BUY", "SELL"):
        raise ValueError("side 必须为 BUY/SELL")
    td = _iso(trade_date)
    px = float(price)
    if px <= 0:
        raise ValueError("price 必须大于 0")
    sh = int(shares) if shares else None
    amount = round(px * sh, 2) if sh else None
    execute(
        """
        INSERT INTO quant_trade_log
            (user_id, ts_code, stock_name, side, trade_date, price, shares, amount, source, strategy_id, note)
        VALUES (:uid, :tc, :name, :side, :td, :px, :sh, :amt, :src, :sid, :note)
        """,
        {
            "uid": user_id, "tc": ts_code.strip(), "name": stock_name, "side": side,
            "td": td, "px": px, "sh": sh, "amt": amount, "src": source,
            "sid": strategy_id, "note": note,
        },
    )
    return {"ok": True}


def list_trades(user_id: int, ts_code: str | None = None, limit: int = 200) -> list[dict]:
    params: dict[str, Any] = {"uid": user_id}
    filt = ""
    if ts_code:
        filt = "AND ts_code = :tc"
        params["tc"] = ts_code.strip()
    rows = fetch_all(
        f"""
        SELECT id, ts_code, stock_name, side, trade_date, price, shares, amount,
               source, strategy_id, note, created_at
        FROM quant_trade_log
        WHERE user_id = :uid {filt}
        ORDER BY trade_date DESC, id DESC LIMIT {int(limit)}
        """,
        params,
    )
    return [_row(r) for r in rows]


def delete_trade(user_id: int, trade_id: int) -> bool:
    n = execute(
        "DELETE FROM quant_trade_log WHERE id = :id AND user_id = :uid",
        {"id": trade_id, "uid": user_id},
    )
    return n > 0


def positions_summary(user_id: int) -> list[dict]:
    """按 ts_code 汇总买卖点为持仓：净股数、买入均价、浮动盈亏。"""
    rows = fetch_all(
        """
        SELECT ts_code, stock_name, side, price, shares, amount
        FROM quant_trade_log
        WHERE user_id = :uid AND shares IS NOT NULL
        """,
        {"uid": user_id},
    )
    agg: dict[str, dict] = {}
    for r in rows:
        code = r["ts_code"]
        a = agg.setdefault(
            code,
            {"ts_code": code, "stock_name": r.get("stock_name"),
             "buy_shares": 0, "buy_cost": 0.0, "sell_shares": 0, "sell_amount": 0.0},
        )
        sh = int(r["shares"] or 0)
        amt = float(r["amount"] or 0)
        if r["side"] == "BUY":
            a["buy_shares"] += sh
            a["buy_cost"] += amt
        else:
            a["sell_shares"] += sh
            a["sell_amount"] += amt
        if r.get("stock_name") and not a.get("stock_name"):
            a["stock_name"] = r["stock_name"]

    out = []
    codes = [c for c, a in agg.items() if a["buy_shares"] - a["sell_shares"] > 0]
    price_map = _latest_prices(codes)
    for code, a in agg.items():
        net = a["buy_shares"] - a["sell_shares"]
        if net <= 0:
            continue
        avg_cost = a["buy_cost"] / a["buy_shares"] if a["buy_shares"] else None
        cur = price_map.get(code)
        market_value = net * cur if cur else None
        unrealized = (cur - avg_cost) * net if (cur and avg_cost) else None
        unrealized_pct = ((cur / avg_cost - 1) * 100) if (cur and avg_cost) else None
        out.append({
            "ts_code": code,
            "stock_name": a["stock_name"],
            "net_shares": net,
            "avg_cost": round(avg_cost, 4) if avg_cost else None,
            "cur_price": round(cur, 4) if cur else None,
            "market_value": round(market_value, 2) if market_value else None,
            "unrealized": round(unrealized, 2) if unrealized is not None else None,
            "unrealized_pct": round(unrealized_pct, 2) if unrealized_pct is not None else None,
        })
    out.sort(key=lambda x: x.get("market_value") or 0, reverse=True)
    return out


def _latest_prices(codes: list[str]) -> dict[str, float]:
    if not codes:
        return {}
    row = fetch_one_stock("SELECT MAX(trade_date) AS d FROM ods_stock_detail_di")
    td = _serialize(row["d"]) if row and row.get("d") else None
    if not td:
        return {}
    placeholders = ", ".join(f":c{i}" for i in range(len(codes)))
    params = {"td": td, **{f"c{i}": c for i, c in enumerate(codes)}}
    rows = fetch_all_stock(
        f"""
        SELECT ts_code, close FROM ods_stock_detail_di
        WHERE trade_date = :td AND ts_code IN ({placeholders})
        """,
        params,
    )
    return {r["ts_code"]: float(r["close"]) for r in rows if r.get("close") is not None}
