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
BT_RUN = "dwm_board_timing_bt_run"
BT_TRADE = "dwm_board_timing_bt_trade"
BT_METRICS = "dwm_board_timing_bt_metrics"
MAINLINE_TABLE = "dws_dc_industry_mainline_monitor_di"
VP_TABLE = "dwm_industry_vp_score_di"
DEFAULT_RUN_CODE = "daily_default"
RETENTION_DAYS = 730
EXEC_MODEL = "t1_open"

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
    row = fetch_one_stock(f"SELECT MAX(trade_date) AS d FROM {SIGNAL_TABLE}")
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


def _latest_bt_run(run_code: str = DEFAULT_RUN_CODE) -> dict | None:
    row = fetch_one_stock(
        f"""
        SELECT *
        FROM {BT_RUN}
        WHERE run_code = :code AND status = 'done'
        ORDER BY end_date DESC, id DESC
        LIMIT 1
        """,
        {"code": run_code},
    )
    return _serialize_row(row)


def list_backtest_runs(limit: int = 20) -> dict:
    rows = fetch_all_stock(
        f"""
        SELECT *
        FROM {BT_RUN}
        WHERE status = 'done'
        ORDER BY end_date DESC, id DESC
        LIMIT :lim
        """,
        {"lim": limit},
    )
    return {"items": [_serialize_row(r) for r in rows], "count": len(rows)}


def get_timing_config(run_code: str = DEFAULT_RUN_CODE) -> dict:
    """默认参数 + 最近一次 run 的 params 快照（可复现）。"""
    import json

    defaults = {
        "weight_trend": 0.30,
        "weight_fund": 0.30,
        "weight_vp": 0.25,
        "weight_sentiment": 0.15,
        "buy_score": 70.0,
        "sell_score": 40.0,
        "gate_trend": 60.0,
        "gate_fund": 55.0,
        "gate_vp": 50.0,
        "sell_trend": 45.0,
        "stop_loss_pct": 0.08,
        "cost_bps": 3.0,
        "exec_model": EXEC_MODEL,
        "backtest_lookback_days": 120,
        "content_types": ["行业", "概念"],
    }
    run = _latest_bt_run(run_code)
    params = None
    if run and run.get("params_json"):
        raw = run["params_json"]
        if isinstance(raw, str):
            try:
                params = json.loads(raw)
            except json.JSONDecodeError:
                params = None
        elif isinstance(raw, dict):
            params = raw
    return {
        "exec_model": EXEC_MODEL,
        "defaults": defaults,
        "active_params": params or defaults,
        "run": run,
    }


def get_backtest_summary(run_code: str = DEFAULT_RUN_CODE) -> dict:
    return {
        "exec_model": EXEC_MODEL,
        "retention_days": RETENTION_DAYS,
        "run": _latest_bt_run(run_code),
        "config": get_timing_config(run_code),
    }


def rank_boards(
    trade_date: str | None = None,
    *,
    content_types: str = "行业,概念",
    signal_type: str | None = None,
    top: int = 50,
    sort: str = "score",
    mainline_levels: str | None = None,
    vp_status: str | None = None,
    with_metrics: bool = True,
) -> dict:
    td = _resolve_trade_date(trade_date)
    types = [x.strip() for x in content_types.split(",") if x.strip()] or ["行业", "概念"]
    ph = ", ".join(f":t{i}" for i in range(len(types)))
    params: dict[str, Any] = {"td": td, "top": top, **{f"t{i}": t for i, t in enumerate(types)}}

    metric_sorts = {
        "total_return",
        "win_rate",
        "avg_return",
        "trade_count",
        "max_drawdown",
    }
    score_sorts = {
        "score",
        "score_trend",
        "score_fund",
        "score_vp",
        "score_sentiment",
        "rank_score",
    }
    sort_key = sort if sort in (score_sorts | metric_sorts) else "score"

    where_sig = ""
    if signal_type and signal_type in {"buy", "sell", "none"}:
        where_sig = " AND s.signal_type = :sig"
        params["sig"] = signal_type

    join_ml = f"""
        LEFT JOIN {MAINLINE_TABLE} m
          ON m.trade_date = s.trade_date
         AND REPLACE(m.industry_code, '.DC', '') = REPLACE(s.industry_code, '.DC', '')
    """
    where_ml = ""
    if mainline_levels and mainline_levels.strip():
        levels = [x.strip() for x in mainline_levels.split(",") if x.strip()]
        if levels:
            mph = ", ".join(f":ml{i}" for i in range(len(levels)))
            where_ml = f" AND m.mainline_level IN ({mph})"
            params.update({f"ml{i}": lv for i, lv in enumerate(levels)})

    join_vp = f"""
        LEFT JOIN {VP_TABLE} v
          ON v.trade_date = s.trade_date
         AND REPLACE(v.industry_code, '.DC', '') = REPLACE(s.industry_code, '.DC', '')
    """
    where_vp = ""
    if vp_status and vp_status.strip():
        statuses = [x.strip() for x in vp_status.split(",") if x.strip()]
        if statuses:
            vph = ", ".join(f":vp{i}" for i in range(len(statuses)))
            where_vp = f" AND v.vp_status IN ({vph})"
            params.update({f"vp{i}": st for i, st in enumerate(statuses)})

    bt_run = _latest_bt_run() if with_metrics else None
    join_bt = ""
    select_bt = """
        NULL AS bt_trade_count, NULL AS bt_win_rate, NULL AS bt_avg_return,
        NULL AS bt_total_return, NULL AS bt_max_drawdown, NULL AS bt_avg_hold_days,
        NULL AS bt_profit_factor, NULL AS bt_last_return
    """
    if bt_run and bt_run.get("id"):
        params["run_id"] = bt_run["id"]
        join_bt = f"""
            LEFT JOIN {BT_METRICS} bt
              ON bt.run_id = :run_id
             AND REPLACE(bt.industry_code, '.DC', '') = REPLACE(s.industry_code, '.DC', '')
        """
        select_bt = """
            bt.trade_count AS bt_trade_count,
            bt.win_rate AS bt_win_rate,
            bt.avg_return AS bt_avg_return,
            bt.total_return AS bt_total_return,
            bt.max_drawdown AS bt_max_drawdown,
            bt.avg_hold_days AS bt_avg_hold_days,
            bt.profit_factor AS bt_profit_factor,
            bt.last_return AS bt_last_return
        """

    if sort_key in metric_sorts and bt_run:
        order_map = {
            "total_return": "bt.total_return DESC",
            "win_rate": "bt.win_rate DESC",
            "avg_return": "bt.avg_return DESC",
            "trade_count": "bt.trade_count DESC",
            "max_drawdown": "bt.max_drawdown ASC",
        }
        order = order_map[sort_key] + ", s.score DESC"
    elif sort_key == "rank_score":
        order = "s.rank_score ASC, s.score DESC"
    else:
        order = f"s.{sort_key} DESC, s.industry_code ASC"

    select_ml = "m.mainline_level"
    select_vp = "v.vp_status"

    rows = fetch_all_stock(
        f"""
        SELECT
            s.industry_code, s.industry_name, s.content_type, s.close, s.ma20, s.ma60,
            s.score, s.score_trend, s.score_fund, s.score_vp, s.score_sentiment,
            s.signal_type, s.signal_reason, s.position_state,
            s.mom20, s.flow5, s.net_inflow_days, s.amount_ratio20, s.up_ratio, s.limit_up_ratio,
            s.sentiment_overheat, s.last_buy_close, s.rank_score,
            {select_ml},
            {select_vp},
            {select_bt}
        FROM {SIGNAL_TABLE} s
        {join_ml}
        {join_vp}
        {join_bt}
        WHERE s.trade_date = :td
          AND s.content_type IN ({ph})
          {where_sig}
          {where_ml}
          {where_vp}
        ORDER BY {order}
        LIMIT :top
        """,
        params,
    )
    return {
        "trade_date": td,
        "exec_model": EXEC_MODEL,
        "backtest_run": bt_run,
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


def list_board_metrics(
    *,
    run_code: str = DEFAULT_RUN_CODE,
    content_types: str = "行业,概念",
    top: int = 50,
    sort: str = "total_return",
) -> dict:
    run = _latest_bt_run(run_code)
    if not run:
        return {"run": None, "items": [], "count": 0, "exec_model": EXEC_MODEL}
    types = [x.strip() for x in content_types.split(",") if x.strip()] or ["行业", "概念"]
    ph = ", ".join(f":t{i}" for i in range(len(types)))
    sort_key = (
        sort
        if sort
        in {
            "total_return",
            "win_rate",
            "avg_return",
            "trade_count",
            "max_drawdown",
            "avg_hold_days",
        }
        else "total_return"
    )
    order = "max_drawdown ASC" if sort_key == "max_drawdown" else f"{sort_key} DESC"
    params: dict[str, Any] = {
        "run_id": run["id"],
        "top": top,
        **{f"t{i}": t for i, t in enumerate(types)},
    }
    rows = fetch_all_stock(
        f"""
        SELECT industry_code, industry_name, content_type,
               trade_count, closed_count, win_count, win_rate,
               avg_return, total_return, max_drawdown, avg_hold_days,
               profit_factor, last_return
        FROM {BT_METRICS}
        WHERE run_id = :run_id
          AND (content_type IN ({ph}) OR content_type IS NULL)
        ORDER BY {order}, industry_code ASC
        LIMIT :top
        """,
        params,
    )
    return {
        "run": run,
        "exec_model": EXEC_MODEL,
        "items": [_serialize_row(r) for r in rows],
        "count": len(rows),
    }


def get_board_trades(
    industry_code: str,
    *,
    run_code: str = DEFAULT_RUN_CODE,
    limit: int = 100,
    bars: list[dict] | None = None,
) -> dict:
    run = _latest_bt_run(run_code)
    if not run:
        return {
            "run": None,
            "items": [],
            "count": 0,
            "metrics": None,
            "equity_curve": [],
            "buyhold_curve": [],
            "executions": [],
            "exec_model": EXEC_MODEL,
        }
    bare = industry_code.strip().replace(".DC", "")
    metrics = fetch_one_stock(
        f"""
        SELECT *
        FROM {BT_METRICS}
        WHERE run_id = :run_id
          AND REPLACE(industry_code, '.DC', '') = :bare
        LIMIT 1
        """,
        {"run_id": run["id"], "bare": bare},
    )
    rows = fetch_all_stock(
        f"""
        SELECT *
        FROM {BT_TRADE}
        WHERE run_id = :run_id
          AND REPLACE(industry_code, '.DC', '') = :bare
        ORDER BY entry_date DESC, id DESC
        LIMIT :lim
        """,
        {"run_id": run["id"], "bare": bare, "lim": limit},
    )
    chron = list(reversed(rows))
    equity = 1.0
    curve = []
    for r in chron:
        ret = r.get("return_pct")
        if ret is None:
            continue
        equity *= 1.0 + float(ret)
        curve.append(
            {
                "trade_date": _serialize(r.get("exit_date") or r.get("entry_date")),
                "equity": equity,
                "return_pct": float(ret),
                "is_open": int(r.get("is_open") or 0),
            }
        )

    # 买入持有曲线（对齐 bars 或按成交区间）
    buyhold_curve: list[dict] = []
    if bars:
        closes = [
            (b.get("trade_date"), float(b["close"]))
            for b in bars
            if b.get("close") is not None and b.get("trade_date")
        ]
        if closes:
            base = closes[0][1]
            if base > 0:
                buyhold_curve = [
                    {"trade_date": d, "equity": c / base}
                    for d, c in closes
                ]

    # 图上成交点：T+1 开盘实际进出
    executions = []
    for r in chron:
        executions.append(
            {
                "kind": "entry",
                "signal_date": _serialize(r.get("buy_signal_date")),
                "trade_date": _serialize(r.get("entry_date")),
                "price": float(r["entry_price"]) if r.get("entry_price") is not None else None,
            }
        )
        if r.get("exit_date") is not None:
            executions.append(
                {
                    "kind": "exit",
                    "signal_date": _serialize(r.get("sell_signal_date")),
                    "trade_date": _serialize(r.get("exit_date")),
                    "price": float(r["exit_price"]) if r.get("exit_price") is not None else None,
                    "is_open": int(r.get("is_open") or 0),
                }
            )

    return {
        "run": run,
        "exec_model": EXEC_MODEL,
        "metrics": _serialize_row(metrics),
        "items": [_serialize_row(r) for r in rows],
        "equity_curve": curve,
        "buyhold_curve": buyhold_curve,
        "executions": executions,
        "count": len(rows),
    }


def _norm_iso(raw: str | None) -> str | None:
    if not raw:
        return None
    s = str(raw).strip()
    if len(s) >= 10 and s[4] == "-" and s[7] == "-":
        return s[:10]
    digits = s.replace("-", "")[:8]
    if len(digits) == 8 and digits.isdigit():
        return f"{digits[:4]}-{digits[4:6]}-{digits[6:8]}"
    return None


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
    start_iso = _norm_iso(start_date)
    end_iso = _norm_iso(td) or td
    chart = chart_svc.get_board_kline(
        code,
        end_iso,
        days=days,
        start_date=start_iso,
    )
    bars = chart.get("bars") or []
    if not bars:
        raise ValueError(f"板块 {code} 暂无 K 线")

    start = bars[0].get("trade_date") or end_iso
    end = bars[-1].get("trade_date") or end_iso
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
               ma20, ma60, close, mom20, net_inflow_days, up_ratio, limit_up_ratio,
               sentiment_overheat
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

    last_timing = next((t for t in reversed(series) if t and t.get("score") is not None), None)
    bt = get_board_trades(code, bars=bars)

    return {
        **chart,
        "trade_date": end_iso,
        "industry_code": code,
        "start_date": start,
        "end_date": end,
        "exec_model": EXEC_MODEL,
        "timing": series,
        "latest_timing": last_timing,
        "signals": [
            _serialize_row(r)
            for r in sig_rows
            if (r.get("signal_type") or "none") in ("buy", "sell")
        ],
        "backtest": {
            "run": bt.get("run"),
            "metrics": bt.get("metrics"),
            "trades": bt.get("items"),
            "equity_curve": bt.get("equity_curve"),
            "buyhold_curve": bt.get("buyhold_curve"),
            "executions": bt.get("executions"),
        },
    }
