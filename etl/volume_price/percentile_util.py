"""VP 百分位子分：统一升序（值越大 → 百分位越高）。"""
from __future__ import annotations

import pandas as pd


def ascending_percentile_score(
    series: pd.Series,
    *,
    winsorize: bool = True,
    lower: float = 0.01,
    upper: float = 0.99,
) -> pd.Series:
    """
    升序百分位 rank(pct=True)*100。

    适用于「越高越好」的原始指标。禁止对这类维度使用降序排名，
    否则 VP 权重方向会反转。

    口径修正：
    - winsorize：先对原始值做 P1–P99 截尾再排名，降低极端值对百分位的扭曲
      （样本 <5 时截尾无意义，跳过）。
    - 缺失值(NaN)保持 NaN：不参与该维排名、不给分，区分“数据不可得”与“最差分”。
      （pandas rank 默认 na_option='keep'，NaN 输入 → NaN 输出。）
    """
    if series.empty:
        return series
    s = series.astype(float)
    if winsorize:
        valid = s.dropna()
        if len(valid) >= 5:
            lo = valid.quantile(lower)
            hi = valid.quantile(upper)
            s = s.clip(lower=lo, upper=hi)
    return (s.rank(pct=True, method="average") * 100).round(2)


def trend_score_input(trend_return_20d: pd.Series) -> pd.Series:
    """
    趋势强度：20 日收益率，负值归零(下限 0)后再取升序百分位。

    口径修正：缺失(NaN)不再 fillna(0) 当成“零收益”，而是保留 NaN 使其不参与
    趋势维排名（区分“无板块指数数据”与“真实走平/下跌”）。有值时负收益归零。
    """
    return trend_return_20d.astype(float).clip(lower=0)
