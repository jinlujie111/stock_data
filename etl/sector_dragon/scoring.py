"""排名分与 MVP 综合分计算。"""
from __future__ import annotations

import json
import math
from typing import Any


def percentile_score(values: dict[str, float | None], code: str) -> float | None:
    """成分股截面百分位排名 → 0~100（越大越好）。"""
    x = values.get(code)
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return None
    valid = [v for v in values.values() if v is not None and not math.isnan(v)]
    if not valid:
        return None
    n = len(valid)
    rank = sum(1 for v in valid if v <= x)
    return round(100.0 * rank / n, 2)


def rs_to_score(
    rs: float | None,
    board_ret: float | None,
    *,
    cap: float = 3.0,
    cap_score: float = 90.0,
) -> float | None:
    if rs is None or board_ret is None:
        return None
    if board_ret == 0:
        return None
    rs_clamped = min(max(rs, 0.0), cap)
    return round(cap_score * (rs_clamped / cap), 2)


def composite_weighted(*parts: tuple[float, float | None]) -> float | None:
    """按权重合成；缺失子项自动降权（权重和重归一）。"""
    valid = [(w, s) for w, s in parts if s is not None]
    if not valid:
        return None
    w_sum = sum(w for w, _ in valid)
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
) -> float | None:
    return composite_weighted(
        (w_fund, score_fund),
        (w_rs, score_rs),
        (w_amount, score_amount),
        (w_mv, score_mv),
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

    return (
        f"【{industry_name}板块龙头识别】截至 {trade_date}\n\n"
        f"{line('产业龙头', 'industry')}\n"
        f"{line('资金龙头', 'fund')}\n"
        f"{line('趋势龙头', 'trend')}\n"
        f"{line('机构龙头', 'inst')}\n"
        f"{line('综合龙头', 'composite')}"
    )


def detail_json(**kwargs: Any) -> str:
    return json.dumps(kwargs, ensure_ascii=False)
