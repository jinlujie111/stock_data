"""配置驱动的截面打分引擎：短线/长线共用。

给定某交易日的行情面板切片 + 基本面 as-of，按策略 config 中的因子权重做
截面百分位加权，产出排名与综合分，并附带可买标记（涨停不可买等）。
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import date
from typing import Any

import numpy as np
import pandas as pd
from sqlalchemy.engine import Engine

from etl.quant.factors import (
    FUNDAMENTAL_FACTORS,
    PricePanel,
    StockMeta,
    load_fundamental_asof,
)

logger = logging.getLogger(__name__)


@dataclass
class FactorSpec:
    name: str
    weight: float
    direction: int = 1


@dataclass
class StrategyConfig:
    horizon: str = "short"
    exclude_st: bool = True
    min_amount: float = 0.0
    min_list_days: int = 60
    mv_min: float | None = None
    mv_max: float | None = None
    exclude_limit: bool = True
    factors: list[FactorSpec] = None  # type: ignore[assignment]
    top_n: int = 20
    rebalance: str = "daily"  # daily / weekly / monthly
    stop_loss: float | None = -0.08
    take_profit: float | None = None
    max_hold_days: int | None = None
    exit_rule: str | None = None  # ma20_break / ma60_break

    @staticmethod
    def from_json(cfg: str | dict) -> "StrategyConfig":
        data: dict[str, Any] = json.loads(cfg) if isinstance(cfg, str) else dict(cfg)
        uni = data.get("universe", {}) or {}
        sel = data.get("select", {}) or {}
        risk = data.get("risk", {}) or {}
        factors = [
            FactorSpec(
                name=f["name"],
                weight=float(f.get("weight", 0.0)),
                direction=int(f.get("direction", 1)),
            )
            for f in data.get("factors", [])
            if f.get("name")
        ]
        return StrategyConfig(
            horizon=data.get("horizon", "short"),
            exclude_st=bool(uni.get("exclude_st", True)),
            min_amount=float(uni.get("min_amount", 0) or 0),
            min_list_days=int(uni.get("min_list_days", 60) or 0),
            mv_min=(float(uni["mv_min"]) if uni.get("mv_min") not in (None, "") else None),
            mv_max=(float(uni["mv_max"]) if uni.get("mv_max") not in (None, "") else None),
            exclude_limit=bool(uni.get("exclude_limit", True)),
            factors=factors,
            top_n=int(sel.get("top_n", 20) or 20),
            rebalance=str(sel.get("rebalance", "daily") or "daily"),
            stop_loss=_opt_float(risk.get("stop_loss")),
            take_profit=_opt_float(risk.get("take_profit")),
            max_hold_days=_opt_int(risk.get("max_hold_days")),
            exit_rule=(str(risk["exit_rule"]) if risk.get("exit_rule") else None),
        )

    def needs_fundamentals(self) -> bool:
        if self.mv_min is not None or self.mv_max is not None:
            return True
        return any(f.name in FUNDAMENTAL_FACTORS for f in (self.factors or []))


def _opt_float(v) -> float | None:
    if v in (None, ""):
        return None
    return float(v)


def _opt_int(v) -> int | None:
    if v in (None, ""):
        return None
    return int(v)


def _pct_rank(series: pd.Series, direction: int) -> pd.Series:
    """截面百分位 0~100；缺失值置中性 50，不参与惩罚。"""
    valid = series.astype(float)
    r = valid.rank(pct=True, na_option="keep") * 100.0
    if direction < 0:
        r = 100.0 - r
    return r.fillna(50.0)


def score_date(
    as_of: date,
    panel: PricePanel,
    meta: dict[str, StockMeta],
    engine: Engine,
    cfg: StrategyConfig,
    *,
    fundamentals: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """返回按综合分降序的候选表（含 rank_no、score、can_buy、factor 明细）。"""
    day = panel.slice(as_of)
    if day.empty:
        return day
    df = day.copy()

    if cfg.needs_fundamentals():
        fdf = fundamentals if fundamentals is not None else load_fundamental_asof(engine, as_of)
        df = df.merge(fdf, on="ts_code", how="left")
    else:
        for col in ("roe", "growth", "pe_inv", "pb_inv", "total_mv"):
            df[col] = np.nan

    # ---- 选股宇宙过滤 ----
    keep = pd.Series(True, index=df.index)
    if cfg.exclude_st:
        st_codes = {c for c, m in meta.items() if m.is_st}
        keep &= ~df["ts_code"].isin(st_codes)
    if cfg.min_amount > 0:
        keep &= df["amount"].fillna(0) >= cfg.min_amount
    if cfg.min_list_days > 0:
        # 交易日近似为日历日 * 1.5
        min_cal = int(cfg.min_list_days * 1.5)
        def _old_enough(code: str) -> bool:
            m = meta.get(code)
            if not m or not m.list_date:
                return False
            return (as_of - m.list_date).days >= min_cal
        keep &= df["ts_code"].map(_old_enough)
    if cfg.mv_min is not None:
        keep &= df["total_mv"].fillna(0) >= cfg.mv_min
    if cfg.mv_max is not None:
        keep &= df["total_mv"].fillna(np.inf) <= cfg.mv_max
    df = df[keep].reset_index(drop=True)
    if df.empty:
        return df

    # ---- 因子截面打分 ----
    factors = [f for f in (cfg.factors or []) if f.name in df.columns]
    for f in (cfg.factors or []):
        if f.name not in df.columns:
            logger.warning("因子 %s 不在面板列中，跳过", f.name)
    total_w = sum(abs(f.weight) for f in factors) or 1.0
    composite = pd.Series(0.0, index=df.index)
    rank_cols: list[str] = []
    for f in factors:
        rank = _pct_rank(df[f.name], f.direction)
        rcol = f"__rank_{f.name}"
        df[rcol] = rank
        rank_cols.append(rcol)
        composite += rank * (f.weight / total_w)

    df["score"] = composite.round(4)
    df = df.sort_values("score", ascending=False).reset_index(drop=True)
    df["rank_no"] = np.arange(1, len(df) + 1)

    can_buy = pd.Series(True, index=df.index)
    if cfg.exclude_limit:
        can_buy &= df["up_limit_hit"].fillna(0) < 1
    df["can_buy"] = can_buy.values

    def _factor_json(i: int) -> str:
        detail: dict[str, Any] = {}
        for f in factors:
            raw = df.at[i, f.name]
            rk = df.at[i, f"__rank_{f.name}"]
            detail[f.name] = {
                "raw": None if pd.isna(raw) else round(float(raw), 4),
                "rank": None if pd.isna(rk) else round(float(rk), 1),
            }
        return json.dumps(detail, ensure_ascii=False)

    df["factor_json"] = [_factor_json(i) for i in range(len(df))]
    df = df.drop(columns=rank_cols)
    return df
