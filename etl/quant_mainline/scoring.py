"""百分位标准化与 FTELP 合成。"""
from __future__ import annotations

from typing import Iterable


def _valid_pairs(values: Iterable[float | None]) -> list[tuple[int, float]]:
    out: list[tuple[int, float]] = []
    for i, v in enumerate(values):
        if v is None:
            continue
        try:
            fv = float(v)
        except (TypeError, ValueError):
            continue
        if fv != fv:  # NaN
            continue
        out.append((i, fv))
    return out


def percentile_scores(
    values: list[float | None],
    *,
    higher_is_better: bool = True,
    neutral: float = 50.0,
) -> list[float]:
    """截面百分位得分 0~100；缺失填 neutral。"""
    pairs = _valid_pairs(values)
    n = len(pairs)
    scores = [neutral] * len(values)
    if n == 0:
        return scores
    if n == 1:
        scores[pairs[0][0]] = 100.0
        return scores

    sorted_pairs = sorted(pairs, key=lambda x: x[1], reverse=higher_is_better)
    for rank, (idx, _) in enumerate(sorted_pairs):
        pct = (1.0 - rank / (n - 1)) * 100.0
        scores[idx] = round(pct, 2)
    return scores


def weighted_sum(parts: list[tuple[float, float | None]]) -> float | None:
    """(weight, value) 加权；全缺失返回 None。"""
    total_w = 0.0
    acc = 0.0
    for w, v in parts:
        if v is None:
            continue
        total_w += w
        acc += w * float(v)
    if total_w <= 0:
        return None
    return round(acc / total_w, 2)
