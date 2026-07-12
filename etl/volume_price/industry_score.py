"""行业 VP 评分与信号。"""
from __future__ import annotations

import json
import logging
from typing import Any

import pandas as pd

from etl.volume_price.db_util import VpConfig
from etl.volume_price.percentile_util import ascending_percentile_score, trend_score_input

logger = logging.getLogger(__name__)


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
    """
    行业+概念合并池内计算升序百分位子分并加权 VP 分。

    六个维度均为「值越大越好」；趋势强度在取百分位前对 20 日收益率做归零约束 max(0, ret)。
    所有子分统一使用 ascending_percentile_score，禁止降序百分位。
    """
    if not agg_rows:
        return []
    g = pd.DataFrame(agg_rows).copy()

    # 合并排名：不按 content_type 分组
    g["score_continuity"] = ascending_percentile_score(
        g["continuity_strength"].fillna(0).astype(float)
    )
    g["score_vol"] = ascending_percentile_score(
        g["industry_vol_ratio_20"].fillna(0).astype(float)
    )
    g["score_trend"] = ascending_percentile_score(
        trend_score_input(g["trend_return_20d"])
    )
    g["score_breadth"] = ascending_percentile_score(g["rising_ratio"].fillna(0).astype(float))
    g["score_breakout"] = ascending_percentile_score(g["breakout_ratio"].fillna(0).astype(float))
    g["score_leader"] = ascending_percentile_score(g["leader_strength"].fillna(0).astype(float))

    g["vp_score"] = (
        g["score_continuity"] * cfg.weight_continuity
        + g["score_vol"] * cfg.weight_vol
        + g["score_trend"] * cfg.weight_trend
        + g["score_breadth"] * cfg.weight_breadth
        + g["score_breakout"] * cfg.weight_breakout
        + g["score_leader"] * cfg.weight_leader
    ).round(2)

    g = g.sort_values("vp_score", ascending=False)
    g["rank_vp"] = range(1, len(g) + 1)

    out_rows: list[dict[str, Any]] = []
    for _, r in g.iterrows():
        vp_score = float(r["vp_score"])
        vp_status = _vp_status(vp_score, cfg)
        detail = {
            "total_amount": float(r["total_amount"]) if pd.notna(r["total_amount"]) else None,
            "avg_pct_chg": float(r["avg_pct_chg"]) if pd.notna(r["avg_pct_chg"]) else None,
            "vol_expand_ratio": float(r["vol_expand_ratio"])
            if pd.notna(r["vol_expand_ratio"])
            else None,
            "continuity_strength": float(r["continuity_strength"])
            if pd.notna(r.get("continuity_strength"))
            else None,
            "trend_return_20d": float(r["trend_return_20d"])
            if pd.notna(r.get("trend_return_20d"))
            else None,
            "leader_strength": float(r["leader_strength"])
            if pd.notna(r.get("leader_strength"))
            else None,
            "percentile_pool": "merged",
        }
        out_rows.append(
            {
                "trade_date": r["trade_date"],
                "industry_code": r["industry_code"],
                "industry_name": r.get("industry_name"),
                "content_type": r.get("content_type"),
                "vp_window": int(r["vp_window"]),
                "score_vol": float(r["score_vol"]),
                "score_trend": float(r["score_trend"]),
                "score_continuity": float(r["score_continuity"]),
                "score_breadth": float(r["score_breadth"]),
                "score_breakout": float(r["score_breakout"]),
                "score_leader": float(r["score_leader"]),
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
                "continuity_strength": float(r["continuity_strength"])
                if pd.notna(r.get("continuity_strength"))
                else None,
                "trend_return_20d": float(r["trend_return_20d"])
                if pd.notna(r.get("trend_return_20d"))
                else None,
                "leader_strength": float(r["leader_strength"])
                if pd.notna(r.get("leader_strength"))
                else None,
                "detail_json": json.dumps(detail, ensure_ascii=False),
            }
        )

    logger.info("industry_score rows=%d pool=merged ascending_percentile", len(out_rows))
    return out_rows
