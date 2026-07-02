"""行业 VP 评分与信号。"""
from __future__ import annotations

import json
import logging
from typing import Any

import pandas as pd

from etl.volume_price.db_util import VpConfig

logger = logging.getLogger(__name__)


def _percentile_score(series: pd.Series) -> pd.Series:
    if series.empty:
        return series
    return (series.rank(pct=True, method="average") * 100).round(2)


def _vp_status(score: float, cfg: VpConfig) -> str:
    if score >= cfg.score_status_burst:
        return "mainline_burst"
    if score >= cfg.score_status_up:
        return "trend_up"
    if score >= cfg.score_status_range:
        return "range_bound"
    if score >= cfg.score_status_weak:
        return "weak"
    return "ebbing"


def _signal_type(vp_status: str) -> str:
    if vp_status == "mainline_burst":
        return "main_rise"
    if vp_status == "ebbing":
        return "ebbing"
    return "none"


def score_industries(agg_rows: list[dict[str, Any]], cfg: VpConfig) -> list[dict[str, Any]]:
    if not agg_rows:
        return []
    df = pd.DataFrame(agg_rows)
    out_rows: list[dict[str, Any]] = []

    for ct, grp in df.groupby("content_type", dropna=False):
        g = grp.copy()
        g["score_vol"] = _percentile_score(
            g["industry_vol_ratio_20"].fillna(0).astype(float)
        )
        g["score_trend"] = _percentile_score(g["avg_pct_chg"].fillna(0).astype(float))
        g["score_continuity"] = _percentile_score(
            g["amount_streak_days"].fillna(0).astype(float)
        )
        g["score_breadth"] = _percentile_score(g["rising_ratio"].fillna(0).astype(float))
        g["score_breakout"] = _percentile_score(g["breakout_ratio"].fillna(0).astype(float))
        g["vp_score"] = (
            g["score_vol"] * cfg.weight_vol
            + g["score_trend"] * cfg.weight_trend
            + g["score_continuity"] * cfg.weight_continuity
            + g["score_breadth"] * cfg.weight_breadth
            + g["score_breakout"] * cfg.weight_breakout
        ).round(2)
        g = g.sort_values("vp_score", ascending=False)
        g["rank_vp"] = range(1, len(g) + 1)

        for _, r in g.iterrows():
            vp_score = float(r["vp_score"])
            vp_status = _vp_status(vp_score, cfg)
            detail = {
                "total_amount": float(r["total_amount"]) if pd.notna(r["total_amount"]) else None,
                "avg_pct_chg": float(r["avg_pct_chg"]) if pd.notna(r["avg_pct_chg"]) else None,
                "vol_expand_ratio": float(r["vol_expand_ratio"])
                if pd.notna(r["vol_expand_ratio"])
                else None,
            }
            out_rows.append(
                {
                    "trade_date": r["trade_date"],
                    "industry_code": r["industry_code"],
                    "industry_name": r.get("industry_name"),
                    "content_type": ct,
                    "window": int(r["window"]),
                    "score_vol": float(r["score_vol"]),
                    "score_trend": float(r["score_trend"]),
                    "score_continuity": float(r["score_continuity"]),
                    "score_breadth": float(r["score_breadth"]),
                    "score_breakout": float(r["score_breakout"]),
                    "vp_score": vp_score,
                    "vp_status": vp_status,
                    "signal_type": _signal_type(vp_status),
                    "rank_vp": int(r["rank_vp"]),
                    "member_cnt": int(r["member_cnt"]),
                    "industry_vol_ratio_20": float(r["industry_vol_ratio_20"])
                    if pd.notna(r.get("industry_vol_ratio_20"))
                    else None,
                    "rising_ratio": float(r["rising_ratio"]) if pd.notna(r["rising_ratio"]) else None,
                    "breakout_ratio": float(r["breakout_ratio"])
                    if pd.notna(r["breakout_ratio"])
                    else None,
                    "amount_streak_days": int(r["amount_streak_days"] or 0),
                    "detail_json": json.dumps(detail, ensure_ascii=False),
                }
            )

    logger.info("industry_score rows=%d", len(out_rows))
    return out_rows
