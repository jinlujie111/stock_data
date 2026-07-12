"""VP 百分位子分：统一升序（值越大 → 百分位越高）。"""
from __future__ import annotations

import pandas as pd


def ascending_percentile_score(series: pd.Series) -> pd.Series:
    """
    升序百分位 rank(pct=True)*100。

    适用于「越高越好」的原始指标。禁止对这类维度使用降序排名，
    否则 VP 权重方向会反转。
    """
    if series.empty:
        return series
    return (series.rank(pct=True, method="average") * 100).round(2)


def trend_score_input(trend_return_20d: pd.Series) -> pd.Series:
    """趋势强度：20 日收益率，负值归零后再取升序百分位。"""
    return trend_return_20d.fillna(0).astype(float).clip(lower=0)
