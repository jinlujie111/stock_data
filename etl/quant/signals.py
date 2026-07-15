"""每日量化信号生成：对每个启用策略在给定交易日打分选股，
与前一信号日对比标注 BUY/HOLD/SELL，写入 data_industry.quant_signal_di。
"""
from __future__ import annotations

import logging
from datetime import date

import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine

from etl.quant.db_util import iso, trading_days_before
from etl.quant.engine import StrategyConfig, score_date
from etl.quant.factors import (
    PricePanel,
    StockMeta,
    load_fundamental_asof,
    load_stock_meta,
)

logger = logging.getLogger(__name__)

SIGNAL_INSERT = """
INSERT INTO quant_signal_di (
    strategy_id, trade_date, ts_code, stock_name, action, rank_no, score, close, factor_json
) VALUES (
    :strategy_id, :trade_date, :ts_code, :stock_name, :action, :rank_no, :score, :close, :factor_json
)
ON DUPLICATE KEY UPDATE
    stock_name=VALUES(stock_name), action=VALUES(action), rank_no=VALUES(rank_no),
    score=VALUES(score), close=VALUES(close), factor_json=VALUES(factor_json)
"""


def load_active_strategies(industry_engine: Engine) -> list[dict]:
    with industry_engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT id, code, name, horizon, config_json FROM quant_strategy "
                "WHERE is_active = 1"
            )
        ).mappings().all()
    return [dict(r) for r in rows]


def _prev_selected(industry_engine: Engine, strategy_id: int, d: date) -> set[str]:
    with industry_engine.connect() as conn:
        prev_date = conn.execute(
            text(
                "SELECT MAX(trade_date) FROM quant_signal_di "
                "WHERE strategy_id = :sid AND trade_date < :d"
            ),
            {"sid": strategy_id, "d": iso(d)},
        ).scalar()
        if not prev_date:
            return set()
        rows = conn.execute(
            text(
                "SELECT ts_code FROM quant_signal_di "
                "WHERE strategy_id = :sid AND trade_date = :pd AND action IN ('BUY','HOLD')"
            ),
            {"sid": strategy_id, "pd": prev_date},
        ).fetchall()
    return {r[0] for r in rows}


def generate_for_strategy(
    strategy: dict,
    d: date,
    stock_engine: Engine,
    industry_engine: Engine,
    meta: dict[str, StockMeta],
    panel: PricePanel,
) -> int:
    cfg = StrategyConfig.from_json(strategy["config_json"])
    fundamentals = load_fundamental_asof(stock_engine, d) if cfg.needs_fundamentals() else None
    ranked = score_date(d, panel, meta, stock_engine, cfg, fundamentals=fundamentals)
    if ranked.empty:
        logger.warning("策略 %s 在 %s 无候选", strategy["code"], d)
        return 0

    buyable = ranked[ranked["can_buy"]].head(cfg.top_n)
    selected = list(buyable["ts_code"])
    selected_set = set(selected)
    prev = _prev_selected(industry_engine, strategy["id"], d)

    rows: list[dict] = []
    score_map = dict(zip(ranked["ts_code"], ranked["score"]))
    rank_map = dict(zip(ranked["ts_code"], ranked["rank_no"]))
    close_map = dict(zip(ranked["ts_code"], ranked["close"]))
    fjson_map = dict(zip(ranked["ts_code"], ranked["factor_json"]))

    for code in selected:
        rows.append(
            {
                "strategy_id": strategy["id"],
                "trade_date": iso(d),
                "ts_code": code,
                "stock_name": meta.get(code).name if meta.get(code) else None,
                "action": "BUY" if code not in prev else "HOLD",
                "rank_no": int(rank_map.get(code, 0)) or None,
                "score": float(score_map.get(code)) if pd.notna(score_map.get(code)) else None,
                "close": float(close_map.get(code)) if pd.notna(close_map.get(code)) else None,
                "factor_json": fjson_map.get(code),
            }
        )
    # 上一日持有但今日被剔除 → SELL
    for code in prev - selected_set:
        rows.append(
            {
                "strategy_id": strategy["id"],
                "trade_date": iso(d),
                "ts_code": code,
                "stock_name": meta.get(code).name if meta.get(code) else None,
                "action": "SELL",
                "rank_no": int(rank_map.get(code)) if code in rank_map else None,
                "score": float(score_map.get(code)) if code in score_map and pd.notna(score_map.get(code)) else None,
                "close": float(close_map.get(code)) if code in close_map and pd.notna(close_map.get(code)) else None,
                "factor_json": fjson_map.get(code),
            }
        )

    with industry_engine.begin() as conn:
        conn.execute(
            text("DELETE FROM quant_signal_di WHERE strategy_id = :sid AND trade_date = :d"),
            {"sid": strategy["id"], "d": iso(d)},
        )
        for i in range(0, len(rows), 500):
            conn.execute(text(SIGNAL_INSERT), rows[i : i + 500])
    logger.info(
        "策略 %s %s 信号: %d 选中(%d 新买) %d 卖出",
        strategy["code"],
        d,
        len(selected),
        len([r for r in rows if r["action"] == "BUY"]),
        len([r for r in rows if r["action"] == "SELL"]),
    )
    return len(rows)


def generate_all(
    d: date,
    stock_engine: Engine,
    industry_engine: Engine,
    panel: PricePanel,
    meta: dict[str, StockMeta] | None = None,
) -> dict[str, int]:
    strategies = load_active_strategies(industry_engine)
    if not strategies:
        logger.warning("无启用策略")
        return {}
    meta = meta or load_stock_meta(stock_engine)
    stats: dict[str, int] = {}
    for s in strategies:
        try:
            stats[s["code"]] = generate_for_strategy(
                s, d, stock_engine, industry_engine, meta, panel
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("策略 %s 生成信号失败: %s", s["code"], exc)
            stats[s["code"]] = -1
    return stats
