"""排名分与 MVP 综合分计算。"""
from __future__ import annotations

import json
import math
from typing import Any


def _quantile(xs: list[float], q: float) -> float:
    """线性插值分位数（无外部依赖）。"""
    s = sorted(xs)
    if not s:
        return 0.0
    pos = q * (len(s) - 1)
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    if lo == hi:
        return s[lo]
    frac = pos - lo
    return s[lo] * (1 - frac) + s[hi] * frac


def percentile_score(
    values: dict[str, float | None],
    code: str,
    *,
    min_n: int = 3,
    winsorize: bool = True,
) -> float | None:
    """
    成分股截面百分位排名 → 0~100（越大越好）。

    口径修正：
    - 最小样本门槛 min_n（默认 3，与板块最小成分数一致）：有效样本不足返回 None，不强行排名。
    - winsorize：对有效值做 P1–P99 截尾（样本 >=5 才生效），降低极端值扭曲。
    - 零离散（如某维全为 0 / 全相等，例如 fund_map 全 0）返回中性 50，
      避免“全 100”虚高误导。
    """
    x = values.get(code)
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return None
    valid = [
        float(v)
        for v in values.values()
        if v is not None and not (isinstance(v, float) and math.isnan(v))
    ]
    if len(valid) < min_n:
        return None
    xf = float(x)
    if winsorize and len(valid) >= 5:
        lo = _quantile(valid, 0.01)
        hi = _quantile(valid, 0.99)
        valid = [min(max(v, lo), hi) for v in valid]
        xf = min(max(xf, lo), hi)
    if max(valid) <= min(valid):
        return 50.0
    n = len(valid)
    rank = sum(1 for v in valid if v <= xf)
    return round(100.0 * rank / n, 2)


def rs_to_score(
    rs: float | None,
    board_ret: float | None,
    *,
    cap: float = 3.0,
    cap_score: float = 90.0,
    stock_ret: float | None = None,
    flat_eps: float = 1e-4,
) -> float | None:
    """
    相对强度 RS(=个股收益/板块收益) → 0~cap_score 分。

    口径修正：
    - 弱于基准(RS<1，含 RS<0)不再一律 0 分：RS 在 [-cap, cap] 线性映射到 [0, cap_score]，
      RS=0 约为中值，负 RS(个股弱于板块)得低分但仍保留区分度。
    - 板块基本走平(|board_ret|<=flat_eps)时 RS 失真：改用个股自身收益方向单独定分
      （围绕中值，涨→略高、跌→略低），避免 board_ret==0 时整片 RS 缺失。
    """
    if board_ret is None or abs(board_ret) <= flat_eps:
        # 走平期：RS 无意义，用个股绝对收益(小数，如 0.05=5%)围绕中值给分并限幅。
        if stock_ret is None:
            return None
        mid = cap_score / 2.0
        return round(min(cap_score, max(0.0, mid + max(-mid, min(mid, stock_ret * 100.0)))), 2)
    if rs is None:
        return None
    rs_clamped = min(max(rs, -cap), cap)
    return round(cap_score * (rs_clamped + cap) / (2 * cap), 2)


def composite_weighted(*parts: tuple[float, float | None]) -> float | None:
    """按权重合成；缺失子项自动降权（权重和重归一）。"""
    valid = [(w, s) for w, s in parts if s is not None]
    if not valid:
        return None
    w_sum = sum(w for w, _ in valid)
    if w_sum <= 0:  # 所有有效子项权重为 0，无法合成
        return None
    return round(sum(w * s for w, s in valid) / w_sum, 2)


def composite_mvp(
    score_fund: float | None,
    score_rs: float | None,
    score_amount: float | None,
    score_mv: float | None,
    *,
    w_fund: float = 0.4,
    w_rs: float = 0.3,
    w_amount: float = 0.2,
    w_mv: float = 0.1,
    score_industry: float | None = None,
    score_inst: float | None = None,
    w_industry: float = 0.0,
    w_inst: float = 0.0,
) -> float | None:
    """
    综合分 = 资金 + 趋势(RS) + 量 + 市值 (+ 可选 产业 + 机构/研报活跃度)。

    传入 score_industry/score_inst 及其权重(>0)即把产业、机构维度纳入综合分，
    使“综合龙头”与 UI「四龙头 + 综合」口径一致；缺失子项由 composite_weighted
    自动降权并对权重重归一（w_industry/w_inst 默认 0，不传则保持原 MVP 四因子口径）。
    """
    return composite_weighted(
        (w_fund, score_fund),
        (w_rs, score_rs),
        (w_amount, score_amount),
        (w_mv, score_mv),
        (w_industry, score_industry),
        (w_inst, score_inst),
    )


def rank_desc(scores: dict[str, float | None]) -> dict[str, int | None]:
    """得分越高排名越靠前（rank=1 最好）。"""
    items = [(c, s) for c, s in scores.items() if s is not None]
    items.sort(key=lambda x: (-x[1], x[0]))
    out: dict[str, int | None] = {c: None for c in scores}
    for i, (code, _) in enumerate(items, start=1):
        out[code] = i
    return out


def mark_leader(rows: list[dict[str, Any]], score_key: str, flag_key: str) -> None:
    best_code: str | None = None
    best_val = -1.0
    for r in rows:
        v = r.get(score_key)
        if v is not None and v > best_val:
            best_val = v
            best_code = r["ts_code"]
    for r in rows:
        r[flag_key] = 1 if r["ts_code"] == best_code and best_code else 0


def build_summary_text(
    industry_name: str,
    trade_date: str,
    leaders: dict[str, str | None],
) -> str:
    def line(label: str, key: str) -> str:
        name = leaders.get(key) or "—"
        return f"{label}：{name}"

    # inst 维度实为“近30日研报篇数”排名（研报活跃度），非机构持仓，文案据实改为“研报活跃龙头”。
    return (
        f"【{industry_name}板块龙头识别】截至 {trade_date}\n\n"
        f"{line('产业龙头', 'industry')}\n"
        f"{line('资金龙头', 'fund')}\n"
        f"{line('趋势龙头', 'trend')}\n"
        f"{line('研报活跃龙头', 'inst')}\n"
        f"{line('综合龙头', 'composite')}"
    )


def detail_json(**kwargs: Any) -> str:
    return json.dumps(kwargs, ensure_ascii=False)
