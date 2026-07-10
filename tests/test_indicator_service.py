"""indicator_service 单元测试。"""
from app.indicator_service import (
    compute_all_levels,
    compute_fibonacci_levels,
    compute_ma_levels,
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


def test_compute_chip_from_cyq():
    cyq = [
        {"price": 100.0, "percent": 15.0},
        {"price": 95.0, "percent": 25.0},
        {"price": 90.0, "percent": 20.0},
        {"price": 105.0, "percent": 10.0},
    ]
    from app.indicator_service import compute_chip_levels

    result = compute_chip_levels([{"close": 98.0}], cyq_rows=cyq)
    assert result["meta"]["source"] == "cyq_chips"
    assert result["supports"]
    assert result["profile"]


def test_compute_all_levels_keys():
    bars = _bars([20 + i * 0.3 for i in range(100)])
    all_lv = compute_all_levels(bars)
    for key in ("ma", "fibonacci", "volume_price", "trendline", "chip"):
        assert key in all_lv
        assert "supports" in all_lv[key]
        assert "resistances" in all_lv[key]
