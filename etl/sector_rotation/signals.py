"""每日板块轮动信号 → data_industry.rotation_signal_di。"""
from __future__ import annotations

import json
import logging
from datetime import date

import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine

from etl.sector_rotation.engine import RotationConfig, score_date
from etl.sector_rotation.factors import SectorPanel, load_panel_from_mysql

logger = logging.getLogger(__name__)


def load_active_strategies(industry_engine: Engine) -> list[dict]:
    with industry_engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT id, code, name, config_json
                FROM rotation_strategy
                WHERE is_active = 1
                ORDER BY id
                """
            )
        ).mappings().all()
    return [dict(r) for r in rows]


def generate_for_strategy(
    d: date,
    strategy: dict,
    panel: SectorPanel,
    industry_engine: Engine,
    *,
    prev_codes: set[str] | None = None,
) -> int:
    cfg = RotationConfig.from_json(strategy["config_json"])
    # 信号日用固定风格或 auto 的当前默认（无完整调仓历史时用 momentum 起步）
    regime = "momentum" if cfg.regime == "auto" else cfg.regime
    if cfg.regime == "reversal":
        regime = "reversal"
    ranked = score_date(d, panel, cfg, regime=regime)  # type: ignore[arg-type]
    if ranked.empty:
        return 0
    buyable = ranked[ranked["can_buy"]].head(cfg.top_n)
    target = set(buyable["ts_code"])
    prev = prev_codes or set()

    rows = []
    for i, r in buyable.iterrows():
        code = r["ts_code"]
        action = "HOLD" if code in prev else "BUY"
        factors = {
            f.name: r[f.name] if f.name in r.index and pd.notna(r[f.name]) else None
            for f in cfg.factors
        }
        factors["regime"] = regime
        rows.append(
            {
                "strategy_id": strategy["id"],
                "trade_date": d,
                "ts_code": code,
                "industry_name": r.get("name"),
                "action": action,
                "rank_no": int(r.name) + 1 if isinstance(r.name, int) else i + 1,
                "score": float(r["score"]) if pd.notna(r["score"]) else None,
                "close": float(r["close"]) if pd.notna(r["close"]) else None,
                "factor_json": json.dumps(factors, ensure_ascii=False),
            }
        )
    # 修正 rank
    for i, row in enumerate(rows):
        row["rank_no"] = i + 1
    for code in prev - target:
        name = panel.names.get(code, code)
        rows.append(
            {
                "strategy_id": strategy["id"],
                "trade_date": d,
                "ts_code": code,
                "industry_name": name,
                "action": "SELL",
                "rank_no": None,
                "score": None,
                "close": None,
                "factor_json": json.dumps({"regime": regime}, ensure_ascii=False),
            }
        )

    with industry_engine.begin() as conn:
        conn.execute(
            text(
                "DELETE FROM rotation_signal_di WHERE strategy_id=:sid AND trade_date=:d"
            ),
            {"sid": strategy["id"], "d": d.isoformat()},
        )
        if rows:
            conn.execute(
                text(
                    """
                    INSERT INTO rotation_signal_di
                        (strategy_id, trade_date, ts_code, industry_name, action,
                         rank_no, score, close, factor_json)
                    VALUES
                        (:strategy_id, :trade_date, :ts_code, :industry_name, :action,
                         :rank_no, :score, :close, :factor_json)
                    """
                ),
                rows,
            )
    return len(rows)


def prev_holdings(industry_engine: Engine, strategy_id: int, before: date) -> set[str]:
    with industry_engine.connect() as conn:
        row = conn.execute(
            text(
                """
                SELECT MAX(trade_date) AS d FROM rotation_signal_di
                WHERE strategy_id = :sid AND trade_date < :d
                """
            ),
            {"sid": strategy_id, "d": before.isoformat()},
        ).mappings().first()
        if not row or not row["d"]:
            return set()
        rows = conn.execute(
            text(
                """
                SELECT ts_code FROM rotation_signal_di
                WHERE strategy_id = :sid AND trade_date = :d AND action IN ('BUY','HOLD')
                """
            ),
            {"sid": strategy_id, "d": row["d"]},
        ).fetchall()
    return {r[0] for r in rows}


def generate_all(
    d: date, stock_engine: Engine, industry_engine: Engine, panel: SectorPanel | None = None
) -> dict[str, int]:
    if panel is None:
        panel = load_panel_from_mysql(stock_engine, d, d)
    strategies = load_active_strategies(industry_engine)
    stats: dict[str, int] = {}
    for s in strategies:
        prev = prev_holdings(industry_engine, s["id"], d)
        n = generate_for_strategy(d, s, panel, industry_engine, prev_codes=prev)
        stats[s["code"]] = n
        logger.info("rotation signal %s %s: %d rows", d, s["code"], n)
    return stats
