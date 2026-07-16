"""Compare a few sector-rotation variants for the same window."""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))

from etl.sector_rotation.backtest import run_backtest
from etl.sector_rotation.engine import FactorSpec, RotationConfig
from etl.sector_rotation.factors import CACHE_DIR, load_benchmark_from_csv, load_panel_from_csv


def main() -> None:
    panel = load_panel_from_csv(CACHE_DIR / "sw_l1_daily.csv")
    bench = load_benchmark_from_csv(CACHE_DIR / "sw_l1_daily.csv")
    start, end = date(2025, 7, 16), date(2026, 7, 15)
    cfgs = [
        (
            "baseline_mom20+60_w5",
            RotationConfig(
                top_n=5,
                rebalance="weekly",
                factors=[FactorSpec("mom20", 0.5), FactorSpec("mom60", 0.5)],
            ),
        ),
        (
            "mom60_only_w5",
            RotationConfig(top_n=5, rebalance="weekly", factors=[FactorSpec("mom60", 1.0)]),
        ),
        (
            "mom20_only_w5",
            RotationConfig(top_n=5, rebalance="weekly", factors=[FactorSpec("mom20", 1.0)]),
        ),
        (
            "mom120+60_w5",
            RotationConfig(
                top_n=5,
                rebalance="weekly",
                factors=[FactorSpec("mom120", 0.5), FactorSpec("mom60", 0.5)],
            ),
        ),
        (
            "reversal20_w5",
            RotationConfig(
                top_n=5,
                rebalance="weekly",
                factors=[FactorSpec("mom20", 1.0, direction=-1)],
            ),
        ),
        (
            "mom60_monthly5",
            RotationConfig(top_n=5, rebalance="monthly", factors=[FactorSpec("mom60", 1.0)]),
        ),
    ]
    print(f"{'variant':28s} {'ret':>8s} {'maxDD':>8s} {'sharpe':>8s} {'vs300':>8s} {'vsEW':>8s}")
    for name, cfg in cfgs:
        m = run_backtest(panel, cfg, start, end, bench).metrics
        print(
            f"{name:28s} {m['total_return']:8.2%} {m['max_drawdown']:8.2%} "
            f"{(m['sharpe'] or 0):8.3f} {m['excess_vs_300']:8.2%} {m['excess_vs_ew']:8.2%}"
        )


if __name__ == "__main__":
    main()
