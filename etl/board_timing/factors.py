"""从 ODS 加载面板并计算四因子原始量与 0–100 子分。"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any

import numpy as np
import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine

from etl.board_timing.db_util import TimingConfig, code_variants
from etl.sector_dragon.db_util import list_boards
from etl.volume_price.percentile_util import ascending_percentile_score

logger = logging.getLogger(__name__)


def _to_float(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s, errors="coerce")


def load_daily_panel(
    engine: Engine,
    boards: list[dict[str, Any]],
    start: date,
    end: date,
) -> pd.DataFrame:
    """ods_dc_daily_di → industry_code 对齐后的 OHLCV。"""
    variant_to_ic: dict[str, str] = {}
    variants: set[str] = set()
    meta: dict[str, dict] = {}
    for b in boards:
        ic = str(b["industry_code"])
        meta[ic] = b
        for v in code_variants(ic):
            variants.add(v)
            variant_to_ic[v] = ic
    if not variants:
        return pd.DataFrame()

    placeholders = ", ".join(f":c{i}" for i in range(len(variants)))
    params: dict[str, Any] = {
        "start": start,
        "end": end,
        **{f"c{i}": c for i, c in enumerate(sorted(variants))},
    }
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                f"""
                SELECT ts_code, trade_date, open, high, low, close, pct_change, vol, amount
                FROM ods_dc_daily_di
                WHERE trade_date BETWEEN :start AND :end
                  AND ts_code IN ({placeholders})
                """
            ),
            params,
        ).mappings().all()

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame([dict(r) for r in rows])
    df["industry_code"] = df["ts_code"].map(variant_to_ic)
    df = df.dropna(subset=["industry_code"])
    df["industry_name"] = df["industry_code"].map(
        lambda c: (meta.get(c) or {}).get("industry_name")
    )
    df["content_type"] = df["industry_code"].map(
        lambda c: (meta.get(c) or {}).get("content_type")
    )
    for col in ("open", "high", "low", "close", "pct_change", "vol", "amount"):
        df[col] = _to_float(df[col])
    df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.date
    # 同一 industry_code 多变体取一条
    df = (
        df.sort_values(["industry_code", "trade_date", "ts_code"])
        .drop_duplicates(["industry_code", "trade_date"], keep="last")
        .reset_index(drop=True)
    )
    return df


def load_fund_panel(
    engine: Engine,
    boards: list[dict[str, Any]],
    start: date,
    end: date,
) -> pd.DataFrame:
    variant_to_ic: dict[str, str] = {}
    variants: set[str] = set()
    for b in boards:
        ic = str(b["industry_code"])
        for v in code_variants(ic):
            variants.add(v)
            variant_to_ic[v] = ic
    if not variants:
        return pd.DataFrame()

    placeholders = ", ".join(f":c{i}" for i in range(len(variants)))
    params: dict[str, Any] = {
        "start": start,
        "end": end,
        **{f"c{i}": c for i, c in enumerate(sorted(variants))},
    }
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                f"""
                SELECT industry_code AS ts_code, trade_date, net_amount
                FROM ods_industry_fund_flow_di
                WHERE trade_date BETWEEN :start AND :end
                  AND industry_code IN ({placeholders})
                """
            ),
            params,
        ).mappings().all()

    if not rows:
        return pd.DataFrame(columns=["industry_code", "trade_date", "net_amount"])

    df = pd.DataFrame([dict(r) for r in rows])
    df["industry_code"] = df["ts_code"].map(variant_to_ic)
    df = df.dropna(subset=["industry_code"])
    df["net_amount"] = _to_float(df["net_amount"])
    df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.date
    return (
        df.sort_values(["industry_code", "trade_date", "ts_code"])
        .drop_duplicates(["industry_code", "trade_date"], keep="last")
        [["industry_code", "trade_date", "net_amount"]]
        .reset_index(drop=True)
    )


def load_breadth_panel(
    engine: Engine,
    boards: list[dict[str, Any]],
    start: date,
    end: date,
) -> pd.DataFrame:
    variant_to_ic: dict[str, str] = {}
    variants: set[str] = set()
    for b in boards:
        ic = str(b["industry_code"])
        for v in code_variants(ic):
            variants.add(v)
            variant_to_ic[v] = ic
    if not variants:
        return pd.DataFrame()

    placeholders = ", ".join(f":c{i}" for i in range(len(variants)))
    params: dict[str, Any] = {
        "start": start,
        "end": end,
        **{f"c{i}": c for i, c in enumerate(sorted(variants))},
    }
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                f"""
                SELECT ts_code, trade_date, up_num, down_num
                FROM ods_dc_index_di
                WHERE trade_date BETWEEN :start AND :end
                  AND ts_code IN ({placeholders})
                """
            ),
            params,
        ).mappings().all()

    if not rows:
        return pd.DataFrame(columns=["industry_code", "trade_date", "up_ratio"])

    df = pd.DataFrame([dict(r) for r in rows])
    df["industry_code"] = df["ts_code"].map(variant_to_ic)
    df = df.dropna(subset=["industry_code"])
    df["up_num"] = _to_float(df["up_num"]).fillna(0)
    df["down_num"] = _to_float(df["down_num"]).fillna(0)
    denom = df["up_num"] + df["down_num"]
    df["up_ratio"] = np.where(denom > 0, df["up_num"] / denom, np.nan)
    df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.date
    return (
        df.sort_values(["industry_code", "trade_date", "ts_code"])
        .drop_duplicates(["industry_code", "trade_date"], keep="last")
        [["industry_code", "trade_date", "up_ratio"]]
        .reset_index(drop=True)
    )


def load_limit_up_ratio(
    engine: Engine,
    boards: list[dict[str, Any]],
    trade_dates: list[date],
) -> pd.DataFrame:
    """按日聚合成分涨停扩散率（limit=U）。"""
    if not trade_dates or not boards:
        return pd.DataFrame(columns=["industry_code", "trade_date", "limit_up_ratio"])

    variant_to_ic: dict[str, str] = {}
    variants: set[str] = set()
    for b in boards:
        ic = str(b["industry_code"])
        for v in code_variants(ic):
            variants.add(v)
            variant_to_ic[v] = ic

    placeholders = ", ".join(f":c{i}" for i in range(len(variants)))
    date_ph = ", ".join(f":d{i}" for i in range(len(trade_dates)))
    params: dict[str, Any] = {
        **{f"c{i}": c for i, c in enumerate(sorted(variants))},
        **{f"d{i}": d for i, d in enumerate(trade_dates)},
    }
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                f"""
                SELECT
                    m.trade_date,
                    m.ts_code,
                    COUNT(DISTINCT m.con_code) AS member_cnt,
                    COUNT(DISTINCT CASE WHEN l.`limit` = 'U' THEN m.con_code END) AS limit_up_cnt
                FROM ods_dc_member_di m
                LEFT JOIN ods_limit_list_di l
                  ON l.trade_date = m.trade_date
                 AND l.ts_code = m.con_code
                 AND l.`limit` = 'U'
                WHERE m.trade_date IN ({date_ph})
                  AND m.ts_code IN ({placeholders})
                GROUP BY m.trade_date, m.ts_code
                """
            ),
            params,
        ).mappings().all()

    if not rows:
        return pd.DataFrame(columns=["industry_code", "trade_date", "limit_up_ratio"])

    df = pd.DataFrame([dict(r) for r in rows])
    df["industry_code"] = df["ts_code"].map(variant_to_ic)
    df = df.dropna(subset=["industry_code"])
    df["member_cnt"] = _to_float(df["member_cnt"])
    df["limit_up_cnt"] = _to_float(df["limit_up_cnt"]).fillna(0)
    df["limit_up_ratio"] = np.where(
        df["member_cnt"] > 0, df["limit_up_cnt"] / df["member_cnt"], np.nan
    )
    df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.date
    return (
        df.sort_values(["industry_code", "trade_date"])
        .drop_duplicates(["industry_code", "trade_date"], keep="last")
        [["industry_code", "trade_date", "limit_up_ratio"]]
        .reset_index(drop=True)
    )


def _consecutive_positive(series: pd.Series) -> pd.Series:
    """连续净流入天数（当日净流入>0 才累计，否则 0）。"""
    out = []
    streak = 0
    for v in series.fillna(0).tolist():
        if v > 0:
            streak += 1
        else:
            streak = 0
        out.append(streak)
    return pd.Series(out, index=series.index)


def compute_factor_frame(
    daily: pd.DataFrame,
    fund: pd.DataFrame,
    breadth: pd.DataFrame,
    limit_up: pd.DataFrame,
    cfg: TimingConfig,
) -> pd.DataFrame:
    """合并面板，按板块时序算原始量，再按日+content_type 截面打分。"""
    if daily.empty:
        return pd.DataFrame()

    df = daily.copy()
    if not fund.empty:
        df = df.merge(fund, on=["industry_code", "trade_date"], how="left")
    else:
        df["net_amount"] = np.nan
    if not breadth.empty:
        df = df.merge(breadth, on=["industry_code", "trade_date"], how="left")
    else:
        df["up_ratio"] = np.nan
    if not limit_up.empty:
        df = df.merge(limit_up, on=["industry_code", "trade_date"], how="left")
    else:
        df["limit_up_ratio"] = np.nan

    parts: list[pd.DataFrame] = []
    for _ic, g in df.groupby("industry_code", sort=False):
        g = g.sort_values("trade_date").copy()
        close = g["close"]
        amount = g["amount"]
        g["ma20"] = close.rolling(20, min_periods=10).mean()
        g["ma60"] = close.rolling(60, min_periods=20).mean()
        g["mom20"] = close / close.shift(20) - 1.0
        g["amount_ma20"] = amount.rolling(20, min_periods=10).mean()
        g["amount_ratio20"] = amount / g["amount_ma20"]
        g["flow5"] = g["net_amount"].rolling(5, min_periods=1).sum()
        g["net_inflow_days"] = _consecutive_positive(g["net_amount"])
        g["above_ma20"] = (close > g["ma20"]).astype(float)
        g["vp_aligned"] = (
            ((g["pct_change"] > 0) & (g["amount_ratio20"] >= 1.0))
            | ((g["pct_change"] < 0) & (g["amount_ratio20"] <= 1.0))
        ).astype(float)
        g["vp_dump"] = (
            (g["pct_change"] <= -2.0) & (g["amount_ratio20"] >= 1.5)
        ).astype(float)
        parts.append(g)

    panel = pd.concat(parts, ignore_index=True)

    scored_parts: list[pd.DataFrame] = []
    for (_td, _ct), g in panel.groupby(["trade_date", "content_type"], sort=False):
        g = g.copy()
        mom_in = g["mom20"].clip(lower=0)
        score_mom = ascending_percentile_score(mom_in)
        score_ma = g["above_ma20"] * 100.0
        g["score_trend"] = (0.6 * score_mom.fillna(0) + 0.4 * score_ma).round(2)

        score_flow = ascending_percentile_score(g["flow5"])
        inflow_cap = (g["net_inflow_days"].clip(upper=5) / 5.0 * 100.0)
        g["score_fund"] = (0.7 * score_flow.fillna(0) + 0.3 * inflow_cap).round(2)

        score_amt = ascending_percentile_score(g["amount_ratio20"])
        g["score_vp"] = (
            0.7 * score_amt.fillna(0) + 0.3 * g["vp_aligned"].fillna(0) * 100.0
        ).round(2)
        # 明显背离/砸盘压分
        g.loc[g["vp_dump"] > 0, "score_vp"] = g.loc[g["vp_dump"] > 0, "score_vp"].clip(
            upper=35
        )

        score_up = ascending_percentile_score(g["up_ratio"])
        score_lu = ascending_percentile_score(g["limit_up_ratio"].fillna(0))
        g["score_sentiment"] = (0.6 * score_up.fillna(50) + 0.4 * score_lu.fillna(0)).round(
            2
        )
        g["sentiment_overheat"] = (
            (g["limit_up_ratio"].fillna(0) >= cfg.overheat_limit_up_ratio)
            | ((g["score_sentiment"] >= 95) & (g["limit_up_ratio"].fillna(0) >= 0.08))
        ).astype(int)

        g["score"] = (
            cfg.weight_trend * g["score_trend"]
            + cfg.weight_fund * g["score_fund"]
            + cfg.weight_vp * g["score_vp"]
            + cfg.weight_sentiment * g["score_sentiment"]
        ).round(2)
        g["rank_score"] = g["score"].rank(ascending=False, method="min").astype("Int64")
        scored_parts.append(g)

    out = pd.concat(scored_parts, ignore_index=True)
    logger.info(
        "factor frame rows=%d boards=%d dates=%d",
        len(out),
        out["industry_code"].nunique(),
        out["trade_date"].nunique(),
    )
    return out


def build_panel_for_range(
    engine: Engine,
    end: date,
    *,
    start: date | None = None,
    content_types: list[str] | None = None,
    cfg: TimingConfig | None = None,
) -> pd.DataFrame:
    cfg = cfg or TimingConfig()
    ctypes = content_types or list(cfg.content_types)
    boards = list_boards(engine, end, ctypes, min_constituents=5)
    if not boards:
        raise RuntimeError(f"无目标板块: {end} types={ctypes}")

    lookback_start = start or (end - timedelta(days=cfg.lookback_days + 40))
    # 日历日约等于，真正窗口靠 rolling；再往前多取一点
    hist_start = lookback_start - timedelta(days=120)

    daily = load_daily_panel(engine, boards, hist_start, end)
    fund = load_fund_panel(engine, boards, hist_start, end)
    breadth = load_breadth_panel(engine, boards, hist_start, end)

    trade_dates = sorted(daily["trade_date"].unique().tolist()) if not daily.empty else []
    # 涨停扩散只算输出区间附近，减轻压力
    limit_dates = [d for d in trade_dates if d >= lookback_start] or trade_dates[-30:]
    limit_up = load_limit_up_ratio(engine, boards, limit_dates)

    return compute_factor_frame(daily, fund, breadth, limit_up, cfg)
