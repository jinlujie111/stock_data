"""板块择时回测：信号日确认 → T+1 开盘成交，按板块统计收益率/成功率。"""
from __future__ import annotations

import argparse
import logging
import math
import sys
from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine

_ROOT = Path(__file__).resolve().parents[2]
for _p in (_ROOT, _ROOT / "dw-utils"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from etl.board_timing.db_util import (  # noqa: E402
    TimingConfig,
    get_engine_stock,
    parse_trade_date,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

SIGNAL_HOT = "dwm_board_timing_signal_di"
SIGNAL_ARCH = "dwm_board_timing_signal_arch"
DAILY = "ods_dc_daily_di"
RUN_TABLE = "dwm_board_timing_bt_run"
TRADE_TABLE = "dwm_board_timing_bt_trade"
METRICS_TABLE = "dwm_board_timing_bt_metrics"

DEFAULT_RUN_CODE = "daily_default"


def _is_na(v: Any) -> bool:
    if v is None:
        return True
    try:
        if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
            return True
    except Exception:
        pass
    try:
        if not isinstance(v, (list, dict, tuple)) and pd.isna(v):
            return True
    except Exception:
        pass
    return False


def _f(v: Any) -> float | None:
    if _is_na(v):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def load_signals(
    engine: Engine,
    start: date,
    end: date,
    *,
    content_types: list[str],
) -> pd.DataFrame:
    types = content_types or ["行业", "概念"]
    ph = ", ".join(f":t{i}" for i in range(len(types)))
    params: dict[str, Any] = {
        "start": start,
        "end": end,
        **{f"t{i}": t for i, t in enumerate(types)},
    }
    sql = f"""
        SELECT trade_date, industry_code, industry_name, content_type,
               signal_type, signal_reason, close
        FROM {SIGNAL_HOT}
        WHERE trade_date BETWEEN :start AND :end
          AND content_type IN ({ph})
          AND signal_type IN ('buy', 'sell')
        UNION ALL
        SELECT trade_date, industry_code, industry_name, content_type,
               signal_type, signal_reason, close
        FROM {SIGNAL_ARCH}
        WHERE trade_date BETWEEN :start AND :end
          AND content_type IN ({ph})
          AND signal_type IN ('buy', 'sell')
          AND NOT EXISTS (
            SELECT 1 FROM {SIGNAL_HOT} h
            WHERE h.trade_date = {SIGNAL_ARCH}.trade_date
              AND h.industry_code = {SIGNAL_ARCH}.industry_code
          )
    """
    with engine.connect() as conn:
        df = pd.read_sql(text(sql), conn, params=params)
    if df.empty:
        return df
    df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.date
    df = df.drop_duplicates(subset=["trade_date", "industry_code", "signal_type"], keep="first")
    return df.sort_values(["industry_code", "trade_date"]).reset_index(drop=True)


def load_ohlc(engine: Engine, codes: list[str], start: date, end: date) -> pd.DataFrame:
    if not codes:
        return pd.DataFrame()
    # 多取一段以覆盖 T+1 开盘与窗口末日
    start_ext = start - timedelta(days=10)
    end_ext = end + timedelta(days=20)
    # ts_code 可能带/不带 .DC
    variants: list[str] = []
    for c in codes:
        c = str(c).strip()
        variants.append(c)
        if c.endswith(".DC"):
            variants.append(c[:-3])
        else:
            variants.append(f"{c}.DC")
    variants = sorted(set(variants))
    # 分批 IN，避免超长
    frames: list[pd.DataFrame] = []
    with engine.connect() as conn:
        for i in range(0, len(variants), 400):
            chunk = variants[i : i + 400]
            ph = ", ".join(f":c{j}" for j in range(len(chunk)))
            params = {
                "start": start_ext,
                "end": end_ext,
                **{f"c{j}": v for j, v in enumerate(chunk)},
            }
            sql = f"""
                SELECT ts_code, trade_date, open, close
                FROM {DAILY}
                WHERE trade_date BETWEEN :start AND :end
                  AND ts_code IN ({ph})
            """
            frames.append(pd.read_sql(text(sql), conn, params=params))
    if not frames:
        return pd.DataFrame()
    df = pd.concat(frames, ignore_index=True)
    if df.empty:
        return df
    df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.date
    df["industry_code"] = df["ts_code"].astype(str).str.replace(r"\.DC$", "", regex=True)
    df = df.sort_values(["industry_code", "trade_date"]).drop_duplicates(
        subset=["industry_code", "trade_date"], keep="last"
    )
    return df.reset_index(drop=True)


def _next_open(
    ohlc_by_code: dict[str, pd.DataFrame],
    code: str,
    signal_date: date,
) -> tuple[date | None, float | None]:
    """信号日之后的下一个有开盘价的交易日。"""
    g = ohlc_by_code.get(code)
    if g is None or g.empty:
        return None, None
    later = g[g["trade_date"] > signal_date]
    if later.empty:
        return None, None
    row = later.iloc[0]
    op = _f(row["open"])
    if op is None or op <= 0:
        return None, None
    return row["trade_date"], op


def _close_on(
    ohlc_by_code: dict[str, pd.DataFrame],
    code: str,
    asof: date,
) -> tuple[date | None, float | None]:
    g = ohlc_by_code.get(code)
    if g is None or g.empty:
        return None, None
    hist = g[g["trade_date"] <= asof]
    if hist.empty:
        return None, None
    row = hist.iloc[-1]
    cl = _f(row["close"])
    if cl is None or cl <= 0:
        return None, None
    return row["trade_date"], cl


def _hold_trading_days(
    ohlc_by_code: dict[str, pd.DataFrame],
    code: str,
    entry: date,
    exit_: date,
) -> int:
    g = ohlc_by_code.get(code)
    if g is None or g.empty:
        return max(0, (exit_ - entry).days)
    n = int(((g["trade_date"] >= entry) & (g["trade_date"] <= exit_)).sum())
    return max(0, n)


def pair_trades(
    signals: pd.DataFrame,
    ohlc: pd.DataFrame,
    *,
    end: date,
    cost_bps: float,
) -> list[dict]:
    if signals.empty:
        return []
    ohlc_by_code: dict[str, pd.DataFrame] = {
        str(c): g.reset_index(drop=True) for c, g in ohlc.groupby("industry_code", sort=False)
    }
    cost = float(cost_bps or 0) / 10000.0
    trades: list[dict] = []

    for code, g in signals.groupby("industry_code", sort=False):
        code = str(code)
        g = g.sort_values("trade_date")
        name = None
        ctype = None
        open_buy: dict | None = None

        for _, r in g.iterrows():
            name = r.get("industry_name") or name
            ctype = r.get("content_type") or ctype
            sig = str(r.get("signal_type") or "none")
            td = r["trade_date"]

            if sig == "buy":
                if open_buy is not None:
                    continue  # 已持仓忽略加仓信号
                entry_d, entry_p = _next_open(ohlc_by_code, code, td)
                if entry_d is None or entry_p is None:
                    continue
                open_buy = {
                    "industry_code": code,
                    "industry_name": name,
                    "content_type": ctype,
                    "buy_signal_date": td,
                    "entry_date": entry_d,
                    "entry_price": entry_p,
                    "exit_reason": r.get("signal_reason"),
                }
            elif sig == "sell" and open_buy is not None:
                exit_d, exit_p = _next_open(ohlc_by_code, code, td)
                if exit_d is None or exit_p is None:
                    # 无下一开盘则用窗口末日收盘盯市
                    exit_d, exit_p = _close_on(ohlc_by_code, code, end)
                    is_open = 1
                else:
                    is_open = 0
                if exit_d is None or exit_p is None:
                    open_buy = None
                    continue
                entry_p = float(open_buy["entry_price"])
                ret = exit_p / entry_p - 1.0 - 2.0 * cost
                trades.append(
                    {
                        **open_buy,
                        "sell_signal_date": td,
                        "exit_date": exit_d,
                        "exit_price": exit_p,
                        "return_pct": ret,
                        "hold_days": _hold_trading_days(
                            ohlc_by_code, code, open_buy["entry_date"], exit_d
                        ),
                        "exit_reason": r.get("signal_reason") or open_buy.get("exit_reason"),
                        "is_open": is_open,
                    }
                )
                open_buy = None

        # 窗口末未平仓：收盘盯市
        if open_buy is not None:
            exit_d, exit_p = _close_on(ohlc_by_code, code, end)
            if exit_d is not None and exit_p is not None:
                entry_p = float(open_buy["entry_price"])
                ret = exit_p / entry_p - 1.0 - cost  # 未卖出只扣买入成本
                trades.append(
                    {
                        **open_buy,
                        "sell_signal_date": None,
                        "exit_date": exit_d,
                        "exit_price": exit_p,
                        "return_pct": ret,
                        "hold_days": _hold_trading_days(
                            ohlc_by_code, code, open_buy["entry_date"], exit_d
                        ),
                        "exit_reason": "窗口末盯市(未平仓)",
                        "is_open": 1,
                    }
                )
    return trades


def _max_drawdown(returns: list[float]) -> float | None:
    if not returns:
        return None
    equity = 1.0
    peak = 1.0
    max_dd = 0.0
    for r in returns:
        equity *= 1.0 + float(r)
        if equity > peak:
            peak = equity
        dd = (peak - equity) / peak if peak > 0 else 0.0
        if dd > max_dd:
            max_dd = dd
    return max_dd


def _compound(returns: list[float]) -> float | None:
    if not returns:
        return None
    eq = 1.0
    for r in returns:
        eq *= 1.0 + float(r)
    return eq - 1.0


def aggregate_metrics(trades: list[dict]) -> tuple[list[dict], dict]:
    """返回 (per_board_metrics, run_summary)。"""
    if not trades:
        return [], {
            "trade_count": 0,
            "board_count": 0,
            "win_rate": None,
            "avg_return": None,
            "total_return": None,
            "max_drawdown": None,
            "avg_hold_days": None,
            "profit_factor": None,
        }

    by_board: dict[str, list[dict]] = {}
    for t in trades:
        by_board.setdefault(t["industry_code"], []).append(t)

    board_rows: list[dict] = []
    all_closed_rets: list[float] = []
    all_hold: list[int] = []
    win_n = 0
    closed_n = 0
    gross_profit = 0.0
    gross_loss = 0.0

    for code, ts in by_board.items():
        ts_sorted = sorted(ts, key=lambda x: (x["entry_date"], x.get("exit_date") or date.min))
        closed = [x for x in ts_sorted if not x.get("is_open")]
        # 指标含盯市笔（用户要看完整表现）；胜率仅已平仓
        rets_all = [float(x["return_pct"]) for x in ts_sorted if x.get("return_pct") is not None]
        rets_closed = [float(x["return_pct"]) for x in closed if x.get("return_pct") is not None]
        holds = [int(x["hold_days"]) for x in ts_sorted if x.get("hold_days") is not None]
        wins = sum(1 for r in rets_closed if r > 0)
        gp = sum(r for r in rets_closed if r > 0)
        gl = sum(-r for r in rets_closed if r < 0)
        name = ts_sorted[0].get("industry_name")
        ctype = ts_sorted[0].get("content_type")
        board_rows.append(
            {
                "industry_code": code,
                "industry_name": name,
                "content_type": ctype,
                "trade_count": len(ts_sorted),
                "closed_count": len(closed),
                "win_count": wins,
                "win_rate": (wins / len(rets_closed)) if rets_closed else None,
                "avg_return": (sum(rets_all) / len(rets_all)) if rets_all else None,
                "total_return": _compound(rets_all),
                "max_drawdown": _max_drawdown(rets_all),
                "avg_hold_days": (sum(holds) / len(holds)) if holds else None,
                "profit_factor": (gp / gl) if gl > 0 else (None if gp <= 0 else None),
                "last_return": rets_all[-1] if rets_all else None,
            }
        )
        # profit_factor: if gl==0 and gp>0 → treat as None or large; use None when no losses
        if gl > 0:
            board_rows[-1]["profit_factor"] = gp / gl
        elif gp > 0 and rets_closed:
            board_rows[-1]["profit_factor"] = None

        all_closed_rets.extend(rets_closed)
        all_hold.extend(holds)
        win_n += wins
        closed_n += len(rets_closed)
        gross_profit += gp
        gross_loss += gl

    # 等权：各板块 total_return 再平均（近似）；回撤用各板块复利序列拼接不稳，
    # 改用全部已平仓按时间排序的复利曲线
    timed = sorted(
        [t for t in trades if t.get("return_pct") is not None and not t.get("is_open")],
        key=lambda x: (x.get("exit_date") or x["entry_date"], x["industry_code"]),
    )
    timed_rets = [float(t["return_pct"]) for t in timed]
    board_compounds = [
        float(b["total_return"])
        for b in board_rows
        if b.get("total_return") is not None
    ]

    summary = {
        "trade_count": len(trades),
        "board_count": len(by_board),
        "win_rate": (win_n / closed_n) if closed_n else None,
        "avg_return": (sum(all_closed_rets) / len(all_closed_rets)) if all_closed_rets else None,
        "total_return": (sum(board_compounds) / len(board_compounds)) if board_compounds else None,
        "max_drawdown": _max_drawdown(timed_rets),
        "avg_hold_days": (sum(all_hold) / len(all_hold)) if all_hold else None,
        "profit_factor": (gross_profit / gross_loss) if gross_loss > 0 else None,
    }
    return board_rows, summary


def _upsert_run(conn, *, run_code: str, start: date, end: date, cfg: TimingConfig, status: str) -> int:
    conn.execute(
        text(
            f"""
            INSERT INTO {RUN_TABLE} (
                run_code, name, start_date, end_date, content_types,
                exec_model, cost_bps, params_json, status
            ) VALUES (
                :run_code, :name, :start_date, :end_date, :content_types,
                :exec_model, :cost_bps, :params_json, :status
            )
            ON DUPLICATE KEY UPDATE
                name=VALUES(name),
                content_types=VALUES(content_types),
                exec_model=VALUES(exec_model),
                cost_bps=VALUES(cost_bps),
                params_json=VALUES(params_json),
                status=VALUES(status),
                error_msg=NULL,
                finished_at=NULL
            """
        ),
        {
            "run_code": run_code,
            "name": f"板块择时回测 {start}~{end}",
            "start_date": start,
            "end_date": end,
            "content_types": ",".join(cfg.content_types),
            "exec_model": cfg.exec_model,
            "cost_bps": cfg.cost_bps,
            "params_json": cfg.to_json(),
            "status": status,
        },
    )
    row = conn.execute(
        text(
            f"""
            SELECT id FROM {RUN_TABLE}
            WHERE run_code=:run_code AND start_date=:start AND end_date=:end
            """
        ),
        {"run_code": run_code, "start": start, "end": end},
    ).mappings().first()
    if not row:
        raise RuntimeError("无法获取 bt_run.id")
    run_id = int(row["id"])
    conn.execute(text(f"DELETE FROM {TRADE_TABLE} WHERE run_id=:id"), {"id": run_id})
    conn.execute(text(f"DELETE FROM {METRICS_TABLE} WHERE run_id=:id"), {"id": run_id})
    return run_id


def _finish_run(conn, run_id: int, summary: dict, *, status: str = "done", error: str | None = None) -> None:
    conn.execute(
        text(
            f"""
            UPDATE {RUN_TABLE}
            SET status=:status,
                trade_count=:trade_count,
                board_count=:board_count,
                win_rate=:win_rate,
                avg_return=:avg_return,
                total_return=:total_return,
                max_drawdown=:max_drawdown,
                avg_hold_days=:avg_hold_days,
                profit_factor=:profit_factor,
                error_msg=:error_msg,
                finished_at=CURRENT_TIMESTAMP
            WHERE id=:id
            """
        ),
        {
            "id": run_id,
            "status": status,
            "trade_count": summary.get("trade_count"),
            "board_count": summary.get("board_count"),
            "win_rate": summary.get("win_rate"),
            "avg_return": summary.get("avg_return"),
            "total_return": summary.get("total_return"),
            "max_drawdown": summary.get("max_drawdown"),
            "avg_hold_days": summary.get("avg_hold_days"),
            "profit_factor": summary.get("profit_factor"),
            "error_msg": error,
        },
    )


def _insert_trades(conn, run_id: int, trades: list[dict]) -> None:
    if not trades:
        return
    sql = text(
        f"""
        INSERT INTO {TRADE_TABLE} (
            run_id, industry_code, industry_name, content_type,
            buy_signal_date, entry_date, entry_price,
            sell_signal_date, exit_date, exit_price,
            return_pct, hold_days, exit_reason, is_open
        ) VALUES (
            :run_id, :industry_code, :industry_name, :content_type,
            :buy_signal_date, :entry_date, :entry_price,
            :sell_signal_date, :exit_date, :exit_price,
            :return_pct, :hold_days, :exit_reason, :is_open
        )
        """
    )
    rows = []
    for t in trades:
        rows.append(
            {
                "run_id": run_id,
                "industry_code": t["industry_code"],
                "industry_name": t.get("industry_name"),
                "content_type": t.get("content_type"),
                "buy_signal_date": t["buy_signal_date"],
                "entry_date": t["entry_date"],
                "entry_price": t["entry_price"],
                "sell_signal_date": t.get("sell_signal_date"),
                "exit_date": t.get("exit_date"),
                "exit_price": t.get("exit_price"),
                "return_pct": t.get("return_pct"),
                "hold_days": t.get("hold_days"),
                "exit_reason": (str(t["exit_reason"])[:512] if t.get("exit_reason") else None),
                "is_open": int(t.get("is_open") or 0),
            }
        )
    for i in range(0, len(rows), 300):
        conn.execute(sql, rows[i : i + 300])


def _insert_metrics(conn, run_id: int, metrics: list[dict]) -> None:
    if not metrics:
        return
    sql = text(
        f"""
        INSERT INTO {METRICS_TABLE} (
            run_id, industry_code, industry_name, content_type,
            trade_count, closed_count, win_count, win_rate,
            avg_return, total_return, max_drawdown, avg_hold_days,
            profit_factor, last_return
        ) VALUES (
            :run_id, :industry_code, :industry_name, :content_type,
            :trade_count, :closed_count, :win_count, :win_rate,
            :avg_return, :total_return, :max_drawdown, :avg_hold_days,
            :profit_factor, :last_return
        )
        """
    )
    rows = [{**m, "run_id": run_id} for m in metrics]
    for i in range(0, len(rows), 300):
        conn.execute(sql, rows[i : i + 300])


def run_backtest(
    end_date: date,
    *,
    start_date: date | None = None,
    cfg: TimingConfig | None = None,
    run_code: str = DEFAULT_RUN_CODE,
    lookback_days: int | None = None,
) -> dict:
    cfg = cfg or TimingConfig()
    engine = get_engine_stock()
    lb = lookback_days if lookback_days is not None else cfg.backtest_lookback_days
    start = start_date or (end_date - timedelta(days=int(lb * 1.6)))
    if start > end_date:
        raise ValueError("start_date 不能晚于 end_date")

    ctypes = list(cfg.content_types)
    logger.info(
        "backtest start=%s end=%s run_code=%s exec=%s cost_bps=%s",
        start,
        end_date,
        run_code,
        cfg.exec_model,
        cfg.cost_bps,
    )

    with engine.begin() as conn:
        run_id = _upsert_run(
            conn,
            run_code=run_code,
            start=start,
            end=end_date,
            cfg=cfg,
            status="running",
        )

    try:
        signals = load_signals(engine, start, end_date, content_types=ctypes)
        codes = sorted(signals["industry_code"].astype(str).unique()) if not signals.empty else []
        # 归一化 code（去 .DC）以便与 OHLC 对齐
        if not signals.empty:
            signals = signals.copy()
            signals["industry_code"] = (
                signals["industry_code"].astype(str).str.replace(r"\.DC$", "", regex=True)
            )
            codes = sorted(signals["industry_code"].unique())

        ohlc = load_ohlc(engine, codes, start, end_date)
        trades = pair_trades(signals, ohlc, end=end_date, cost_bps=cfg.cost_bps)
        metrics, summary = aggregate_metrics(trades)

        with engine.begin() as conn:
            _insert_trades(conn, run_id, trades)
            _insert_metrics(conn, run_id, metrics)
            _finish_run(conn, run_id, summary, status="done")

        out = {
            "run_id": run_id,
            "run_code": run_code,
            "start": str(start),
            "end": str(end_date),
            "signals": int(len(signals)),
            **summary,
        }
        logger.info("backtest done %s", out)
        return out
    except Exception as exc:
        logger.exception("backtest failed")
        with engine.begin() as conn:
            _finish_run(
                conn,
                run_id,
                {
                    "trade_count": 0,
                    "board_count": 0,
                    "win_rate": None,
                    "avg_return": None,
                    "total_return": None,
                    "max_drawdown": None,
                    "avg_hold_days": None,
                    "profit_factor": None,
                },
                status="failed",
                error=str(exc)[:500],
            )
        raise


def run_param_grid(
    end_date: date,
    *,
    start_date: date | None = None,
    base: TimingConfig | None = None,
    buy_scores: list[float] | None = None,
    sell_scores: list[float] | None = None,
    stop_losses: list[float] | None = None,
) -> list[dict]:
    """
    参数网格：对 buy/sell/stop 做笛卡尔积（默认小网格）。
    注意：网格只改回测成交统计口径的 params 快照；信号仍来自已落库的 signal 表，
    故阈值网格主要用于记录对照。真正改信号需重跑 scoring。
    """
    base = base or TimingConfig()
    buys = buy_scores or [base.buy_score]
    sells = sell_scores or [base.sell_score]
    stops = stop_losses or [base.stop_loss_pct]
    results: list[dict] = []
    for b in buys:
        for s in sells:
            for sl in stops:
                cfg = replace(base, buy_score=float(b), sell_score=float(s), stop_loss_pct=float(sl))
                code = f"grid_b{int(b)}_s{int(s)}_sl{int(sl * 100)}"
                # 网格模式下仍用现有信号配对（成本/区间可变）；阈值写入 params 供对照
                out = run_backtest(
                    end_date,
                    start_date=start_date,
                    cfg=cfg,
                    run_code=code,
                )
                results.append(out)
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="板块择时回测(T+1开盘)")
    parser.add_argument("trade_date", help="结束日 YYYYMMDD")
    parser.add_argument("start_date", nargs="?", default=None, help="可选开始日 YYYYMMDD")
    parser.add_argument("--run-code", default=DEFAULT_RUN_CODE)
    parser.add_argument("--lookback-days", type=int, default=None)
    parser.add_argument("--cost-bps", type=float, default=None)
    parser.add_argument(
        "--grid",
        action="store_true",
        help="跑小参数网格(记录多组 run；信号仍取库内已生成事件)",
    )
    args = parser.parse_args(argv)

    end = parse_trade_date(args.trade_date)
    start = parse_trade_date(args.start_date) if args.start_date else None
    cfg = TimingConfig()
    if args.cost_bps is not None:
        cfg = replace(cfg, cost_bps=float(args.cost_bps))

    if args.grid:
        run_param_grid(
            end,
            start_date=start,
            base=cfg,
            buy_scores=[65, 70, 75],
            sell_scores=[35, 40, 45],
            stop_losses=[0.06, 0.08, 0.10],
        )
    else:
        run_backtest(
            end,
            start_date=start,
            cfg=cfg,
            run_code=args.run_code,
            lookback_days=args.lookback_days,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
