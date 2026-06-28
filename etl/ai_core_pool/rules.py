"""规则后处理：剔除概念股、等级映射、核心池筛选。"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from etl.ai_core_pool.context import StockContext
from etl.ai_core_pool.db_util import AiCoreConfig


@dataclass
class AiScoreRow:
    industry_id: str
    industry_name: str
    ts_code: str
    stock_name: str | None
    industry_match: bool
    segment: str | None
    core_degree: str | None
    score: float | None
    level: str | None
    reason: str | None
    model_name: str | None = None
    prompt_version: str | None = None
    raw_json: dict[str, Any] | None = None
    reject_rule: str | None = None


def score_to_level(score: float | None) -> str | None:
    if score is None:
        return None
    if score >= 90:
        return "S"
    if score >= 80:
        return "A"
    if score >= 60:
        return "B"
    return "C"


def apply_rules(
    row: AiScoreRow,
    ctx: StockContext,
    cfg: AiCoreConfig,
) -> AiScoreRow:
    score = row.score
    if score is not None:
        score = max(0.0, min(100.0, float(score)))
        row.score = score

    if not row.industry_match:
        row.reject_rule = "R-3"
        row.level = "C"
        return row

    if score is not None and score <= cfg.reject_score:
        row.reject_rule = "R-2"
        row.industry_match = False
        row.level = "C"
        return row

    if ctx.mainbz_related_pct is not None and ctx.mainbz_related_pct < cfg.mainbz_min_pct:
        row.reject_rule = "R-1"
        row.industry_match = False
        row.level = "C"
        if row.reason:
            row.reason += f"（主营占比{ctx.mainbz_related_pct}%<{cfg.mainbz_min_pct}%）"
        return row

    row.level = score_to_level(score)
    return row


def eligible_for_core_pool(row: AiScoreRow, cfg: AiCoreConfig) -> bool:
    if not row.industry_match:
        return False
    if row.score is None:
        return False
    if row.score < cfg.score_threshold:
        return False
    if row.score <= cfg.reject_score:
        return False
    return row.level in ("S", "A", "B")


@dataclass
class CorePoolRow:
    industry_id: str
    industry_name: str
    ts_code: str
    stock_name: str | None
    score: float
    level: str
    weight: float | None
    segment: str | None
    reason: str | None


def build_core_pool(
    scores: list[AiScoreRow],
    cfg: AiCoreConfig,
) -> list[CorePoolRow]:
    rows = [s for s in scores if eligible_for_core_pool(s, cfg)]
    by_industry: dict[str, list[AiScoreRow]] = {}
    for s in rows:
        by_industry.setdefault(s.industry_id, []).append(s)

    out: list[CorePoolRow] = []
    for iid, group in by_industry.items():
        total = sum(float(s.score or 0) for s in group)
        for s in group:
            w = round(float(s.score or 0) / total, 6) if total > 0 else None
            out.append(
                CorePoolRow(
                    industry_id=iid,
                    industry_name=s.industry_name,
                    ts_code=s.ts_code,
                    stock_name=s.stock_name,
                    score=float(s.score or 0),
                    level=str(s.level or "B"),
                    weight=w,
                    segment=s.segment,
                    reason=s.reason,
                )
            )
    return out
