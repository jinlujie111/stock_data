"""个股量价因子计算。"""
from __future__ import annotations

import logging
from datetime import date
from typing import Any

import numpy as np
import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine

from etl.volume_price.db_util import VpConfig, list_trading_days, load_st_codes

logger = logging.getLogger(__name__)


def _classify_vp_pattern(
    price_up: bool, vol_up: bool, pct_chg: float, vol_ratio: float | None
) -> tuple[str, float]:
    # 量比缺失（均线样本不足等）单独标记为 vol_unknown，不再默认 1.0，
    # 避免把“数据不可得”误判为“量平/缩量”参与量能分类。
    if vol_ratio is None:
        score = 60.0 if price_up else 40.0
        adj = min(10.0, abs(pct_chg) / 2.0)
        score = min(100.0, score + adj) if price_up else max(0.0, score - adj)
        return "vol_unknown", round(score, 2)

    if price_up and vol_up:
        pattern, score = "trend_confirm", 90.0
    elif price_up and not vol_up:
        pattern, score = "weak_rise", 55.0
    elif not price_up and vol_up:
        pattern, score = "distribution", 25.0
    else:
        pattern, score = "consolidation", 50.0
    # 强度微调：涨跌幅 + 量比溢出（此处 vol_ratio 必非空）。
    adj = min(10.0, abs(pct_chg) / 2.0) + min(10.0, max(0.0, vol_ratio - 1.0) * 5.0)
    if pattern in ("trend_confirm", "weak_rise"):
        score = min(100.0, score + adj)
    elif pattern == "distribution":
        score = max(0.0, score - adj)
    elif pattern == "consolidation" and pct_chg < 0:
        # 缩量横盘不再固定 50 分：按当日跌幅小幅下调，避免所有横盘同分。
        score = max(0.0, score - min(10.0, abs(pct_chg) / 2.0))
    return pattern, round(score, 2)


def _vol_streak_series(vol: pd.Series, vol_ma: pd.Series) -> pd.Series:
    streaks: list[int] = []
    streak = 0
    for v, m in zip(vol.tolist(), vol_ma.tolist()):
        if pd.notna(v) and pd.notna(m) and float(m) > 0 and float(v) > float(m):
            streak += 1
        else:
            streak = 0
        streaks.append(streak)
    return pd.Series(streaks, index=vol.index)


def compute_stock_factors(
    engine: Engine,
    trade_date: date,
    cfg: VpConfig,
) -> list[dict[str, Any]]:
    window = cfg.window_default
    lookback = max(window, cfg.breakout_lookback) + 5
    trading_days = list_trading_days(engine, trade_date, lookback)
    if trade_date not in trading_days:
        raise RuntimeError(f"trade_date {trade_date} 不在交易日序列中")
    start = trading_days[0]

    st_codes: set[str] = set()
    if cfg.exclude_st:
        try:
            st_codes = load_st_codes(engine)
        except Exception:
            logger.warning("加载 ST 列表失败，跳过 ST 过滤")

    sql = """
        SELECT d.trade_date, d.ts_code, d.close, d.high, d.vol, d.amount, d.pct_chg,
               b.turnover_rate
        FROM ods_stock_detail_di d
        LEFT JOIN ods_daily_basic_di b
          ON b.trade_date = d.trade_date AND b.ts_code = d.ts_code
        WHERE d.trade_date BETWEEN :start AND :end
          AND d.vol IS NOT NULL AND d.vol > 0
    """
    with engine.connect() as conn:
        df = pd.read_sql(text(sql), conn, params={"start": start, "end": trade_date})

    if df.empty:
        raise RuntimeError(f"ods_stock_detail_di 无数据: {start} ~ {trade_date}")

    if st_codes:
        df = df[~df["ts_code"].isin(st_codes)]

    df["high"] = df["high"].fillna(df["close"])

    df = df.sort_values(["ts_code", "trade_date"])
    parts: list[pd.DataFrame] = []
    for ts_code, grp in df.groupby("ts_code", sort=False):
        g = grp.copy()
        # 量比基准均线排除当日：rolling(20).mean().shift(1) 取 T-1..T-20 的 20 日均量，
        # 不含当日，避免当日成交量算进分母自我参照、压低量比。
        g["vol_ma20"] = (
            g["vol"].rolling(window=window, min_periods=window).mean().shift(1)
        )
        g["vol_ratio_20"] = g["vol"] / g["vol_ma20"].replace(0, np.nan)
        g["price_ma20"] = g["close"].rolling(window=window, min_periods=window).mean()
        lag_close = g["close"].shift(window)
        g["price_trend_20"] = (g["close"] - lag_close) / lag_close.replace(0, np.nan) * 100.0
        # 60 日新高基准：仅取“前一日及之前”的最高价（排除当日），close 站上/突破此值才算新高。
        g["high_60_prior"] = g["high"].shift(1).rolling(
            window=cfg.breakout_lookback - 1, min_periods=cfg.breakout_lookback - 1
        ).max()
        # 突破放量基准也排除当日（T-1..T-5 均额），与量比口径一致。
        g["amount_ma5"] = g["amount"].rolling(window=5, min_periods=5).mean().shift(1)
        g["vol_streak_days"] = _vol_streak_series(g["vol"], g["vol_ma20"])
        # 新高统一用 prior-high（排除当日）；放量口径统一用成交额(amount)，避免与 strict 混用量/额。
        # is_breakout_60：close 站上 60 日 prior-high 且成交额放大。
        g["is_breakout_60"] = (
            (g["close"] >= g["high_60_prior"])
            & (g["amount"] > g["amount_ma5"] * cfg.breakout_vol_mult)
        ).astype(int)
        # is_breakout_strict：close 严格创新高(> 而非 >=)且成交额放大，比 is_breakout_60 更严。
        g["is_breakout_strict"] = (
            (g["close"] > g["high_60_prior"])
            & (g["amount"] > g["amount_ma5"] * cfg.breakout_vol_mult)
        ).astype(int)
        parts.append(g)

    all_df = pd.concat(parts, ignore_index=True)
    # MySQL DATE 列经 pd.read_sql 读回为 datetime.date（object dtype）或 datetime64，
    # 统一转成 datetime64 再与 Timestamp 比较，避免类型不匹配导致筛空。
    all_df["_td"] = pd.to_datetime(all_df["trade_date"])
    today = all_df[all_df["_td"] == pd.Timestamp(trade_date)].drop(columns="_td").copy()
    if today.empty:
        raise RuntimeError(f"当日无有效个股行情: {trade_date}")

    rows: list[dict[str, Any]] = []
    for _, r in today.iterrows():
        if pd.isna(r.get("vol_ma20")):
            continue
        pct = float(r["pct_chg"]) if pd.notna(r["pct_chg"]) else 0.0
        vol_ratio = float(r["vol_ratio_20"]) if pd.notna(r["vol_ratio_20"]) else None
        price_up = pct > 0
        vol_up = bool(vol_ratio is not None and vol_ratio > 1.0)
        # 传入原始 vol_ratio（可能为 None），由分类函数区分“量比缺失”与“量平”。
        pattern, pattern_score = _classify_vp_pattern(price_up, vol_up, pct, vol_ratio)
        rows.append(
            {
                "trade_date": trade_date,
                "ts_code": r["ts_code"],
                "close": float(r["close"]) if pd.notna(r["close"]) else None,
                "vol": float(r["vol"]) if pd.notna(r["vol"]) else None,
                "amount": float(r["amount"]) if pd.notna(r["amount"]) else None,
                "pct_chg": pct,
                "turnover_rate": float(r["turnover_rate"]) if pd.notna(r.get("turnover_rate")) else None,
                "vol_ma20": float(r["vol_ma20"]),
                "vol_ratio_20": vol_ratio,
                "price_ma20": float(r["price_ma20"]) if pd.notna(r.get("price_ma20")) else None,
                "price_trend_20": float(r["price_trend_20"]) if pd.notna(r.get("price_trend_20")) else None,
                "vol_streak_days": int(r["vol_streak_days"] or 0),
                "is_breakout_60": int(r["is_breakout_60"] or 0),
                "is_breakout_strict": int(r["is_breakout_strict"] or 0),
                "vp_pattern": pattern,
                "vp_pattern_score": pattern_score,
                "vp_window": window,
            }
        )
    logger.info("stock_factors trade_date=%s rows=%d", trade_date, len(rows))
    return rows
