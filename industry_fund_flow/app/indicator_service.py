"""K 线支撑/阻力位计算：均线、斐波那契、量价、趋势线。"""
from __future__ import annotations

from typing import Any

MA_PERIODS = (5, 10, 20, 30, 60)
FIB_RATIOS = (0.236, 0.382, 0.5, 0.618, 0.786)
INDICATOR_KEYS = ("ma", "fibonacci", "volume_price", "trendline")


def _f(v: Any) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _round_price(v: float, digits: int = 2) -> float:
    return round(v, digits)


def _level(price: float, label: str, role: str, **extra: Any) -> dict[str, Any]:
    item: dict[str, Any] = {
        "price": _round_price(price),
        "label": label,
        "role": role,
    }
    item.update(extra)
    return item


def calc_ma_series(closes: list[float], period: int) -> list[float | None]:
    out: list[float | None] = []
    for i in range(len(closes)):
        if i < period - 1:
            out.append(None)
            continue
        window = closes[i - period + 1 : i + 1]
        out.append(_round_price(sum(window) / period))
    return out


def compute_ma_levels(bars: list[dict]) -> dict[str, Any]:
    if not bars:
        return {"supports": [], "resistances": [], "series": {}}
    closes = [_f(b.get("close")) or 0.0 for b in bars]
    last_close = closes[-1]
    supports: list[dict] = []
    resistances: list[dict] = []
    series: dict[str, list[float | None]] = {}
    for p in MA_PERIODS:
        ma = calc_ma_series(closes, p)
        series[f"ma{p}"] = ma
        val = ma[-1]
        if val is None:
            continue
        label = f"MA{p}"
        if last_close >= val:
            supports.append(_level(val, f"{label}支撑", "support", period=p))
        else:
            resistances.append(_level(val, f"{label}阻力", "resistance", period=p))
    supports.sort(key=lambda x: x["price"], reverse=True)
    resistances.sort(key=lambda x: x["price"])
    return {"supports": supports, "resistances": resistances, "series": series}


def _swing_high_low(bars: list[dict], lookback: int = 60) -> tuple[float, float, int, int]:
    segment = bars[-lookback:] if len(bars) > lookback else bars
    highs = [_f(b.get("high")) or 0.0 for b in segment]
    lows = [_f(b.get("low")) or 0.0 for b in segment]
    hi = max(highs)
    lo = min(lows)
    hi_i = highs.index(hi)
    lo_i = lows.index(lo)
    return hi, lo, hi_i, lo_i


def compute_fibonacci_levels(bars: list[dict]) -> dict[str, Any]:
    if len(bars) < 10:
        return {"supports": [], "resistances": [], "meta": {}}
    swing_high, swing_low, hi_i, lo_i = _swing_high_low(bars)
    if swing_high <= swing_low:
        return {"supports": [], "resistances": [], "meta": {}}
    diff = swing_high - swing_low
    uptrend = lo_i < hi_i
    last_close = _f(bars[-1].get("close")) or 0.0
    levels: list[dict] = []
    for ratio in FIB_RATIOS:
        if uptrend:
            price = swing_high - diff * ratio
            name = f"斐波{int(ratio * 1000) / 10}%"
        else:
            price = swing_low + diff * ratio
            name = f"斐波{int(ratio * 1000) / 10}%"
        levels.append(_level(price, name, "neutral", ratio=ratio))
    supports = [x for x in levels if x["price"] < last_close]
    resistances = [x for x in levels if x["price"] > last_close]
    for x in supports:
        x["role"] = "support"
        x["label"] = x["label"] + "支撑"
    for x in resistances:
        x["role"] = "resistance"
        x["label"] = x["label"] + "阻力"
    supports.sort(key=lambda x: x["price"], reverse=True)
    resistances.sort(key=lambda x: x["price"])
    return {
        "supports": supports,
        "resistances": resistances,
        "meta": {
            "swing_high": _round_price(swing_high),
            "swing_low": _round_price(swing_low),
            "direction": "up" if uptrend else "down",
        },
    }


def _typical_price(bar: dict) -> float:
    h = _f(bar.get("high")) or 0.0
    l = _f(bar.get("low")) or 0.0
    c = _f(bar.get("close")) or 0.0
    return (h + l + c) / 3.0


def _volume_bins(bars: list[dict], bins: int = 40) -> list[tuple[float, float]]:
    if not bars:
        return []
    lows = [_f(b.get("low")) or 0.0 for b in bars]
    highs = [_f(b.get("high")) or 0.0 for b in bars]
    lo, hi = min(lows), max(highs)
    if hi <= lo:
        return []
    step = (hi - lo) / bins
    acc = [0.0] * bins
    for bar in bars:
        tp = _typical_price(bar)
        vol = _f(bar.get("vol")) or 0.0
        idx = min(bins - 1, max(0, int((tp - lo) / step)))
        acc[idx] += vol
    return [(_round_price(lo + (i + 0.5) * step), acc[i]) for i in range(bins)]


def compute_volume_price_levels(bars: list[dict]) -> dict[str, Any]:
    if len(bars) < 20:
        return {"supports": [], "resistances": [], "meta": {}}
    last_close = _f(bars[-1].get("close")) or 0.0
    profile = _volume_bins(bars, bins=36)
    profile_sorted = sorted(profile, key=lambda x: x[1], reverse=True)
    top_nodes = profile_sorted[:5]
    supports: list[dict] = []
    resistances: list[dict] = []
    for price, vol in top_nodes:
        if vol <= 0:
            continue
        if price < last_close:
            supports.append(_level(price, "量价密集支撑", "support", volume=vol))
        elif price > last_close:
            resistances.append(_level(price, "量价密集阻力", "resistance", volume=vol))
        else:
            supports.append(_level(price, "量价密集区", "support", volume=vol))

    # 放量 K 线高低点
    vols = [_f(b.get("vol")) or 0.0 for b in bars]
    avg_vol = sum(vols[-20:]) / min(20, len(vols))
    for bar in bars[-30:]:
        vol = _f(bar.get("vol")) or 0.0
        if vol < avg_vol * 1.5:
            continue
        h = _f(bar.get("high"))
        l = _f(bar.get("low"))
        pct = _f(bar.get("pct_chg") or bar.get("pct_change")) or 0.0
        if h and pct > 0:
            resistances.append(
                _level(h, "放量高点阻力", "resistance", trade_date=str(bar.get("trade_date", "")))
            )
        if l and pct < 0:
            supports.append(
                _level(l, "放量低点支撑", "support", trade_date=str(bar.get("trade_date", "")))
            )

    def _dedupe(items: list[dict], tol: float = 0.015) -> list[dict]:
        out: list[dict] = []
        for it in sorted(items, key=lambda x: x["price"]):
            if not out or abs(it["price"] - out[-1]["price"]) / max(out[-1]["price"], 1) > tol:
                out.append(it)
        return out

    supports = _dedupe(supports)
    resistances = _dedupe(resistances)
    supports.sort(key=lambda x: x["price"], reverse=True)
    resistances.sort(key=lambda x: x["price"])
    return {
        "supports": supports[:8],
        "resistances": resistances[:8],
        "meta": {"avg_vol_20": _round_price(avg_vol, 0)},
    }


def _local_extrema(bars: list[dict], window: int = 4) -> tuple[list[tuple[int, float]], list[tuple[int, float]]]:
    peaks: list[tuple[int, float]] = []
    troughs: list[tuple[int, float]] = []
    n = len(bars)
    for i in range(window, n - window):
        seg_h = [_f(bars[j].get("high")) or 0.0 for j in range(i - window, i + window + 1)]
        seg_l = [_f(bars[j].get("low")) or 0.0 for j in range(i - window, i + window + 1)]
        h = _f(bars[i].get("high")) or 0.0
        l = _f(bars[i].get("low")) or 0.0
        if h >= max(seg_h):
            peaks.append((i, h))
        if l <= min(seg_l):
            troughs.append((i, l))
    return peaks, troughs


def _line_at_index(p1: tuple[int, float], p2: tuple[int, float], idx: int) -> float:
    i1, v1 = p1
    i2, v2 = p2
    if i2 == i1:
        return v2
    slope = (v2 - v1) / (i2 - i1)
    return v1 + slope * (idx - i1)


def _recent_extrema(points: list[tuple[int, float]], last_idx: int, lookback: int = 90) -> list[tuple[int, float]]:
    cutoff = max(0, last_idx - lookback)
    return [(i, v) for i, v in points if cutoff <= i <= last_idx]


def _slope_label(p1: tuple[int, float], p2: tuple[int, float], role: str) -> str:
    i1, v1 = p1
    i2, v2 = p2
    slope = (v2 - v1) / (i2 - i1) if i2 != i1 else 0.0
    if role == "support":
        if slope > 0:
            return "上升支撑线"
        if slope < 0:
            return "下降支撑线"
        return "水平支撑线"
    if slope > 0:
        return "上升阻力线"
    if slope < 0:
        return "下降阻力线"
    return "水平阻力线"


def _trendline_violations(
    bars: list[dict],
    p1: tuple[int, float],
    p2: tuple[int, float],
    last_idx: int,
    mode: str,
    tol: float = 0.008,
) -> int:
    """统计趋势线被价格有效突破的次数（支撑被跌破 / 阻力被突破）。"""
    violations = 0
    for i in range(p1[0], last_idx + 1):
        y = _line_at_index(p1, p2, i)
        if mode == "support":
            low = _f(bars[i].get("low")) or 0.0
            if low < y * (1 - tol):
                violations += 1
        else:
            high = _f(bars[i].get("high")) or 0.0
            if high > y * (1 + tol):
                violations += 1
    return violations


def _best_trendline_pair(
    points: list[tuple[int, float]],
    bars: list[dict],
    last_idx: int,
    last_close: float,
    *,
    mode: str,
    min_sep: int = 8,
    anchor_lookback: int = 60,
    max_violation_ratio: float = 0.2,
) -> tuple[tuple[int, float], tuple[int, float], float] | None:
    """选取近期有效、少被突破的趋势线锚点。"""
    if len(points) < 2:
        return None
    min_anchor_idx = max(0, last_idx - anchor_lookback)
    candidates: list[tuple[int, float, tuple[int, float], tuple[int, float]]] = []

    for i in range(len(points)):
        for j in range(i + 1, len(points)):
            p1, p2 = points[i], points[j]
            if p1[0] < min_anchor_idx or p2[0] < min_anchor_idx:
                continue
            if p2[0] - p1[0] < min_sep:
                continue
            end_price = _line_at_index(p1, p2, last_idx)
            if mode == "support" and end_price >= last_close:
                continue
            if mode == "resistance" and end_price <= last_close:
                continue
            span = last_idx - p1[0] + 1
            violations = _trendline_violations(bars, p1, p2, last_idx, mode)
            if span > 0 and violations / span > max_violation_ratio:
                continue
            candidates.append((violations, end_price, p1, p2))

    if not candidates:
        return None

    if mode == "support":
        candidates.sort(key=lambda x: (x[0], -x[1]))
    else:
        candidates.sort(key=lambda x: (x[0], x[1]))

    _, end_price, p1, p2 = candidates[0]
    return p1, p2, end_price


def _append_trendline(
    lines: list[dict],
    levels: list[dict],
    bars: list[dict],
    p1: tuple[int, float],
    p2: tuple[int, float],
    end_price: float,
    role: str,
) -> None:
    last_idx = len(bars) - 1
    label = _slope_label(p1, p2, role)
    d1 = str(bars[p1[0]].get("trade_date", ""))
    d2 = str(bars[p2[0]].get("trade_date", ""))
    lines.append(
        {
            "type": "support" if role == "support" else "resistance",
            "label": label,
            "points": [
                {"index": p1[0], "date": d1, "price": _round_price(p1[1])},
                {"index": p2[0], "date": d2, "price": _round_price(p2[1])},
                {
                    "index": last_idx,
                    "date": str(bars[-1].get("trade_date", "")),
                    "price": _round_price(end_price),
                },
            ],
        }
    )
    levels.append(_level(end_price, label, role))


def compute_trendline_levels(bars: list[dict]) -> dict[str, Any]:
    if len(bars) < 30:
        return {"supports": [], "resistances": [], "lines": []}
    peaks, troughs = _local_extrema(bars, window=3)
    last_idx = len(bars) - 1
    last_close = _f(bars[-1].get("close")) or 0.0
    lines: list[dict] = []
    supports: list[dict] = []
    resistances: list[dict] = []

    recent_troughs = _recent_extrema(troughs, last_idx, lookback=90)
    support_pair = _best_trendline_pair(
        recent_troughs, bars, last_idx, last_close, mode="support"
    )
    if support_pair:
        p1, p2, end_price = support_pair
        _append_trendline(lines, supports, bars, p1, p2, end_price, "support")

    recent_peaks = _recent_extrema(peaks, last_idx, lookback=90)
    resistance_pair = _best_trendline_pair(
        recent_peaks, bars, last_idx, last_close, mode="resistance"
    )
    if resistance_pair:
        p1, p2, end_price = resistance_pair
        _append_trendline(lines, resistances, bars, p1, p2, end_price, "resistance")

    return {"supports": supports, "resistances": resistances, "lines": lines}


def compute_all_levels(bars: list[dict]) -> dict[str, Any]:
    return {
        "ma": compute_ma_levels(bars),
        "fibonacci": compute_fibonacci_levels(bars),
        "volume_price": compute_volume_price_levels(bars),
        "trendline": compute_trendline_levels(bars),
    }
