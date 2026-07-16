"""板块轮动 Web 服务：策略 / 信号 / 回测（读写 stock_data.rotation_*）。"""
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

from app.db import execute_stock, fetch_all_stock, fetch_one_stock, get_stock_engine

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


def _validate_config(config: Any) -> str:
    if isinstance(config, str):
        data = json.loads(config)
    elif isinstance(config, dict):
        data = config
    else:
        raise ValueError("config 必须为 JSON 对象或字符串")
    if not data.get("factors"):
        raise ValueError("config.factors 不能为空")
    if not (data.get("select") or {}).get("top_n"):
        raise ValueError("config.select.top_n 必填")
    from etl.sector_rotation.engine import RotationConfig

    RotationConfig.from_json(data)
    return json.dumps(data, ensure_ascii=False)


def list_strategies(user_id: int) -> list[dict]:
    rows = fetch_all_stock(
        """
        SELECT id, code, name, description, config_json,
               is_system, is_active, owner_user_id, updated_at
        FROM rotation_strategy
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
    r = fetch_one_stock("SELECT * FROM rotation_strategy WHERE id = :id", {"id": strategy_id})
    if not r:
        return None
    item = _row(r)
    try:
        item["config"] = json.loads(r["config_json"]) if r.get("config_json") else {}
    except Exception:
        item["config"] = {}
    return item


def create_strategy(
    user_id: int, code: str, name: str, description: str | None, config: Any
) -> dict:
    if not code or not code.strip():
        raise ValueError("code 必填")
    if not name or not name.strip():
        raise ValueError("name 必填")
    cfg_json = _validate_config(config)
    execute_stock(
        """
        INSERT INTO rotation_strategy
            (code, name, description, config_json, is_system, is_active, owner_user_id)
        VALUES (:code, :name, :desc, :cfg, 0, 1, :uid)
        """,
        {
            "code": code.strip(),
            "name": name.strip(),
            "desc": description,
            "cfg": cfg_json,
            "uid": user_id,
        },
    )
    r = fetch_one_stock(
        "SELECT id FROM rotation_strategy WHERE code = :code", {"code": code.strip()}
    )
    return get_strategy(r["id"]) if r else {"code": code}


def update_strategy(
    user_id: int, strategy_id: int, *, name=None, description=None, config=None, is_active=None
) -> dict:
    r = fetch_one_stock("SELECT * FROM rotation_strategy WHERE id = :id", {"id": strategy_id})
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
        execute_stock(
            f"UPDATE rotation_strategy SET {', '.join(sets)} WHERE id = :id", params
        )
    return get_strategy(strategy_id)


def delete_strategy(user_id: int, strategy_id: int) -> bool:
    r = fetch_one_stock("SELECT * FROM rotation_strategy WHERE id = :id", {"id": strategy_id})
    if not r:
        return False
    if r["is_system"]:
        raise ValueError("系统内置策略不可删除")
    if r["owner_user_id"] != user_id:
        raise ValueError("无权删除该策略")
    n = execute_stock("DELETE FROM rotation_strategy WHERE id = :id", {"id": strategy_id})
    return n > 0


def signal_trade_dates(strategy_id: int, limit: int = 60) -> list[str]:
    rows = fetch_all_stock(
        f"""
        SELECT DISTINCT trade_date FROM rotation_signal_di
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
        row = fetch_one_stock(
            "SELECT MAX(trade_date) AS d FROM rotation_signal_di WHERE strategy_id = :sid",
            {"sid": strategy_id},
        )
        td = _serialize(row["d"]) if row and row.get("d") else None
    if not td:
        return {"trade_date": None, "items": []}
    rows = fetch_all_stock(
        """
        SELECT ts_code, industry_name, action, rank_no, score, close, factor_json
        FROM rotation_signal_di
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
        out_name = item.pop("industry_name", None)
        item["stock_name"] = out_name
        items.append(item)
    return {"trade_date": td, "items": items}


def create_backtest(
    user_id: int, strategy_id: int, start_date: str, end_date: str, init_capital: float, name: str | None
) -> int:
    strat = fetch_one_stock(
        "SELECT * FROM rotation_strategy WHERE id = :id", {"id": strategy_id}
    )
    if not strat:
        raise ValueError("策略不存在")
    s = _iso(start_date)
    e = _iso(end_date)
    if s > e:
        s, e = e, s
    cap = float(init_capital) if init_capital else DEFAULT_INIT_CAPITAL
    execute_stock(
        """
        INSERT INTO rotation_backtest_run
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
    row = fetch_one_stock(
        """
        SELECT id FROM rotation_backtest_run
        WHERE owner_user_id = :uid AND strategy_id = :sid
        ORDER BY id DESC LIMIT 1
        """,
        {"uid": user_id, "sid": strategy_id},
    )
    run_id = int(row["id"])
    threading.Thread(
        target=_run_backtest_worker,
        args=(run_id, strat["config_json"], s, e, cap),
        daemon=True,
    ).start()
    return run_id


def _run_backtest_worker(run_id: int, config_json: str, s: str, e: str, cap: float) -> None:
    from etl.sector_rotation.backtest import run_backtest
    from etl.sector_rotation.engine import RotationConfig
    from etl.sector_rotation.factors import (
        CACHE_DIR,
        load_benchmark_from_csv,
        load_benchmark_from_mysql,
        load_panel_from_csv,
        load_panel_from_mysql,
    )

    try:
        execute_stock(
            "UPDATE rotation_backtest_run SET status='running' WHERE id=:id", {"id": run_id}
        )
        cfg = RotationConfig.from_json(config_json)
        cfg.init_capital = float(cap)
        start = datetime.strptime(s.replace("-", ""), "%Y%m%d").date()
        end = datetime.strptime(e.replace("-", ""), "%Y%m%d").date()

        bench: dict = {}
        try:
            stock_engine = get_stock_engine()
            panel = load_panel_from_mysql(stock_engine, start, end)
            bench = load_benchmark_from_mysql(stock_engine, start, end)
        except Exception as exc:
            logger.warning("MySQL 申万面板不可用，回退 CSV cache: %s", exc)
            csv_path = CACHE_DIR / "sw_l1_daily.csv"
            flow_csv = CACHE_DIR / "sw_l1_fund_flow.csv"
            if not csv_path.exists():
                raise RuntimeError(
                    "ods_industry_daily_di 无数据且本地 cache 不存在；"
                    "请执行 20260716_restore_sw_daily_sync.sql 并回填 sw_daily"
                ) from exc
            panel = load_panel_from_csv(
                csv_path, flow_csv if flow_csv.exists() else None
            )
            bench = load_benchmark_from_csv(csv_path)

        result = run_backtest(panel, cfg, start, end, benchmark=bench or None)
        _persist_backtest(run_id, result)
        m = result.metrics
        execute_stock(
            """
            UPDATE rotation_backtest_run SET
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
        logger.info("板块回测 %s 完成: %s", run_id, m)
    except Exception as exc:  # noqa: BLE001
        logger.exception("板块回测 %s 失败", run_id)
        execute_stock(
            "UPDATE rotation_backtest_run SET status='failed', error_msg=:msg, finished_at=NOW() WHERE id=:id",
            {"id": run_id, "msg": str(exc)[:500]},
        )


def _persist_backtest(run_id: int, result) -> None:
    eng = get_stock_engine()
    with eng.begin() as conn:
        conn.execute(text("DELETE FROM rotation_backtest_trade WHERE run_id=:id"), {"id": run_id})
        conn.execute(text("DELETE FROM rotation_backtest_nav WHERE run_id=:id"), {"id": run_id})
        trade_rows = [
            {
                "run_id": run_id,
                "ts_code": t["ts_code"],
                "stock_name": t.get("name") or t.get("stock_name"),
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
                INSERT INTO rotation_backtest_trade
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
                INSERT INTO rotation_backtest_nav
                    (run_id, trade_date, nav, cash, position_value, bench_nav, drawdown)
                VALUES (:run_id, :trade_date, :nav, :cash, :position_value, :bench_nav, :drawdown)
                """
            )
            for i in range(0, len(nav_rows), 500):
                conn.execute(insn, nav_rows[i : i + 500])


def list_backtests(user_id: int, limit: int = 30) -> list[dict]:
    rows = fetch_all_stock(
        f"""
        SELECT r.id, r.strategy_id, s.name AS strategy_name, r.name, r.start_date, r.end_date,
               r.init_capital, r.status, r.total_return, r.annual_return, r.max_drawdown,
               r.sharpe, r.win_rate, r.trade_count, r.bench_return, r.error_msg, r.created_at
        FROM rotation_backtest_run r
        LEFT JOIN rotation_strategy s ON s.id = r.strategy_id
        WHERE r.owner_user_id = :uid
        ORDER BY r.id DESC LIMIT {int(limit)}
        """,
        {"uid": user_id},
    )
    return [_row(r) for r in rows]


def get_backtest(user_id: int, run_id: int) -> dict | None:
    r = fetch_one_stock(
        """
        SELECT r.*, s.name AS strategy_name FROM rotation_backtest_run r
        LEFT JOIN rotation_strategy s ON s.id = r.strategy_id
        WHERE r.id = :id AND r.owner_user_id = :uid
        """,
        {"id": run_id, "uid": user_id},
    )
    if not r:
        return None
    out = _row(r)
    out.pop("params_json", None)
    nav = fetch_all_stock(
        "SELECT trade_date, nav, bench_nav, drawdown FROM rotation_backtest_nav "
        "WHERE run_id = :id ORDER BY trade_date ASC",
        {"id": run_id},
    )
    trades = fetch_all_stock(
        "SELECT ts_code, stock_name, side, trade_date, price, shares, amount, pnl, "
        "return_pct, hold_days, reason FROM rotation_backtest_trade "
        "WHERE run_id = :id ORDER BY trade_date ASC, side DESC",
        {"id": run_id},
    )
    out["nav"] = [_row(x) for x in nav]
    out["trades"] = [_row(x) for x in trades]
    return out
