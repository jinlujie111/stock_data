"""indicator_service 单元测试。"""
from app.indicator_service import (
    compute_all_levels,
    compute_fibonacci_levels,
    compute_ma_levels,
    compute_trendline_levels,
)


def _bars(prices):
    out = []
    for i, p in enumerate(prices):
        out.append(
            {
                "trade_date": f"202601{i+1:02d}",
                "open": p - 1,
                "high": p + 2,
                "low": p - 2,
                "close": p,
                "vol": 1000 + i * 50,
            }
        )
    return out


def test_ma_levels_split_support_resistance():
    bars = _bars([10 + i * 0.5 for i in range(80)])
    result = compute_ma_levels(bars)
    assert result["supports"]
    assert all(s["price"] <= bars[-1]["close"] for s in result["supports"])


def test_fibonacci_levels():
    bars = _bars([50 + (i % 10) for i in range(60)])
    bars[-1]["close"] = 80
    result = compute_fibonacci_levels(bars)
    assert "meta" in result
    assert isinstance(result["supports"], list)
    assert isinstance(result["resistances"], list)


def test_compute_all_levels_keys():
    bars = _bars([20 + i * 0.3 for i in range(100)])
    all_lv = compute_all_levels(bars)
    for key in ("ma", "fibonacci", "volume_price", "trendline"):
        assert key in all_lv
        assert "supports" in all_lv[key]
        assert "resistances" in all_lv[key]
    assert "chip" not in all_lv


def test_trendline_rejects_line_crossing_price_action():
    """支撑线不应从极早期低点连到近期，导致穿过大量 K 线。"""
    bars = []
    for i in range(90):
        if i < 12:
            low, close = 40.0 + i, 45.0 + i
        elif i < 55:
            low, close = 85.0 + (i % 7) * 2, 92.0 + (i % 7) * 2
        else:
            pb = 12 if i % 11 == 5 else 0
            low, close = 78.0 + (i - 55) * 1.1 - pb, 88.0 + (i - 55) * 1.4 - pb
        bars.append(
            {
                "trade_date": f"2026{i:03d}",
                "open": close - 2,
                "high": close + 3,
                "low": low,
                "close": close,
                "vol": 1_000_000,
            }
        )
    result = compute_trendline_levels(bars)
    assert result["supports"], "应有有效支撑线"
    line = result["lines"][0]
    p1_idx = line["points"][0]["index"]
    assert p1_idx >= len(bars) - 65, f"支撑锚点不应落在极早期: index={p1_idx}"


def test_trendline_support_near_price_in_rally():
    """急涨+回踩行情中，支撑应取贴近现价下方的外推位。"""
    bars = []
    for i in range(120):
        base = 9000 + i * 40
        if i > 75:
            base += (i - 75) * 130
        pullback = 900 if i % 12 == 8 else (450 if i % 12 == 9 else 0)
        low = base - pullback
        close = base + 120 - pullback * 0.4
        bars.append(
            {
                "trade_date": f"2026{(i // 30) + 1:02d}{(i % 30) + 1:02d}",
                "open": close - 30,
                "high": close + 80,
                "low": low,
                "close": close,
                "vol": 1_000_000 + i * 20_000,
            }
        )
    last_close = bars[-1]["close"]
    result = compute_trendline_levels(bars)
    assert result["supports"], "应有趋势线支撑"
    support_price = result["supports"][0]["price"]
    assert support_price < last_close
    assert support_price > last_close * 0.9, f"支撑 {support_price} 应贴近现价 {last_close}"
