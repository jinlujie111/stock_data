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
    按 content_type 分组（行业/概念各自截面）计算升序百分位子分并加权 VP 分。

    六个维度均为「值越大越好」；原始值先 P1–P99 winsorize 再取百分位；缺失值(NaN)不参与
    该维排名、也不计入综合分（权重重归一），区分“数据不可得”与“最差”。趋势强度在取百分位前
    对 20 日收益率做归零约束 max(0, ret)。所有子分统一使用 ascending_percentile_score，禁止降序百分位。
    """
    if not agg_rows:
        return []
    g = pd.DataFrame(agg_rows).copy()

    # 按 content_type 分组排名（行业/概念各自成截面）：避免行业与概念(常含小盘、
    # 成交额比/龙头强度更极端)混排导致概念板块霸榜。content_type 缺失用占位符单独成组。
    grp_key = g["content_type"].fillna("__na__")

    def _grouped_pct(values: pd.Series) -> pd.Series:
        # 缺失值(NaN)不再 fillna(0)：保留 NaN，使该维对缺失样本不给分（不当“最差”）。
        return values.astype(float).groupby(grp_key).transform(ascending_percentile_score)

    g["score_continuity"] = _grouped_pct(g["continuity_strength"])
    g["score_vol"] = _grouped_pct(g["industry_vol_ratio_20"])
    g["score_trend"] = trend_score_input(g["trend_return_20d"]).groupby(grp_key).transform(
        ascending_percentile_score
    )
    g["score_breadth"] = _grouped_pct(g["rising_ratio"])
    g["score_breakout"] = _grouped_pct(g["breakout_ratio"])
    # score_leader 仅占 weight_leader(默认 5%)，其上游 leader_strength 已修正量纲问题(见 industry_agg)，
    # 该维现有效；权重维持配置不变。
    g["score_leader"] = _grouped_pct(g["leader_strength"])

    # 综合分对“缺失维度”做权重重归一（缺失不参与、不给 0 分），区分“数据不可得”与“最差”。
    _dims = [
        ("score_continuity", cfg.weight_continuity),
        ("score_vol", cfg.weight_vol),
        ("score_trend", cfg.weight_trend),
        ("score_breadth", cfg.weight_breadth),
        ("score_breakout", cfg.weight_breakout),
        ("score_leader", cfg.weight_leader),
    ]

    def _weighted_vp(row: "pd.Series") -> float:
        num = 0.0
        den = 0.0
        for col, w in _dims:
            v = row[col]
            if pd.notna(v):
                num += w * float(v)
                den += w
        return round(num / den, 2) if den > 0 else 0.0

    g["vp_score"] = g.apply(_weighted_vp, axis=1)

    g = g.sort_values(["vp_score", "industry_code"], ascending=[False, True])
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
            "percentile_pool": "by_content_type",
        }
        # 子分维度可能为 NaN（该维数据缺失、未参与排名）→ 落库为 NULL，不写成 0/最差分。
        _num = lambda k: float(r[k]) if pd.notna(r.get(k)) else None
        out_rows.append(
            {
                "trade_date": r["trade_date"],
                "industry_code": r["industry_code"],
                "industry_name": r.get("industry_name"),
                "content_type": r.get("content_type"),
                "vp_window": int(r["vp_window"]),
                "score_vol": _num("score_vol"),
                "score_trend": _num("score_trend"),
                "score_continuity": _num("score_continuity"),
                "score_breadth": _num("score_breadth"),
                "score_breakout": _num("score_breakout"),
                "score_leader": _num("score_leader"),
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

    logger.info("industry_score rows=%d pool=by_content_type ascending_percentile", len(out_rows))
    return out_rows
