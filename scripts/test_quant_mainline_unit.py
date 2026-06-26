"""需求3 量化主线 — scoring 单元测试（无需数据库）。

完整测试套件:
  scripts/test_quant_mainline_unit.py       # 百分位/加权
  scripts/test_quant_mainline_rank_unit.py  # 行业/概念分榜 TopN
  scripts/test_quant_mainline_data.py       # 数据库验收
  scripts/test_quant_mainline_api.py        # API 验收
  bash scripts/test_quant_mainline.sh       # 一键执行
"""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

from etl.quant_mainline.scoring import percentile_scores, weighted_sum


def test_percentile_scores_basic() -> None:
    vals = [10.0, 20.0, 30.0, 40.0]
    scores = percentile_scores(vals)
    assert scores == [0.0, 33.33, 66.67, 100.0], scores


def test_percentile_scores_missing_neutral() -> None:
    vals = [None, 5.0, None, 10.0]
    scores = percentile_scores(vals, neutral=50.0)
    assert scores[0] == 50.0
    assert scores[2] == 50.0
    assert scores[1] == 0.0
    assert scores[3] == 100.0


def test_percentile_lower_is_better() -> None:
    vals = [1.0, 2.0, 3.0]
    scores = percentile_scores(vals, higher_is_better=False)
    assert scores[0] == 100.0
    assert scores[2] == 0.0


def test_weighted_sum_renormalize() -> None:
    assert weighted_sum([(0.4, 80.0), (0.3, None), (0.3, 60.0)]) == 71.43


def test_weighted_sum_all_none() -> None:
    assert weighted_sum([(0.5, None), (0.5, None)]) is None


def main() -> int:
    tests = [
        test_percentile_scores_basic,
        test_percentile_scores_missing_neutral,
        test_percentile_lower_is_better,
        test_weighted_sum_renormalize,
        test_weighted_sum_all_none,
    ]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS {t.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL {t.__name__}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
