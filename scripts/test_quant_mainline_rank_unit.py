"""需求3 量化主线 — 分类型 TopN 排名逻辑单元测试（无需数据库）。"""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))


def assign_per_type_topn(
    mainline_rows: list[dict],
    top_types: tuple[str, ...],
    top_n: int,
) -> None:
    """与 etl/quant_mainline/batch.py 中排名逻辑保持一致。"""
    rank_lookup: dict[str, int] = {}
    top_lookup: dict[str, int] = {}
    for ct in top_types:
        type_rows = [r for r in mainline_rows if r.get("content_type") == ct]
        type_rows.sort(key=lambda x: (x.get("rank_score") or 0), reverse=True)
        for i, r in enumerate(type_rows):
            code = str(r["industry_code"])
            rank_no = i + 1
            is_top = 1 if i < top_n else 0
            r["rank_no"] = rank_no
            r["is_top3"] = is_top
            rank_lookup[code] = rank_no
            top_lookup[code] = is_top
    for r in mainline_rows:
        code = r["industry_code"]
        if code in rank_lookup:
            r["rank_no"] = rank_lookup[code]
            r["is_top3"] = top_lookup.get(code, 0)
        else:
            r["rank_no"] = None
            r["is_top3"] = 0


def test_industry_and_concept_each_top10() -> None:
    rows = []
    for ct, prefix in (("行业", "IND"), ("概念", "CON")):
        for i in range(15):
            rows.append(
                {
                    "industry_code": f"{prefix}{i:02d}",
                    "content_type": ct,
                    "rank_score": 100 - i,
                }
            )
    assign_per_type_topn(rows, ("行业", "概念"), 10)
    for ct in ("行业", "概念"):
        tops = [r for r in rows if r["content_type"] == ct and r["is_top3"]]
        assert len(tops) == 10, (ct, len(tops))
        assert [r["rank_no"] for r in tops] == list(range(1, 11))
        non_tops = [r for r in rows if r["content_type"] == ct and not r["is_top3"]]
        assert len(non_tops) == 5
        assert all(r["rank_no"] > 10 for r in non_tops)


def test_rank_no_independent_across_types() -> None:
    rows = [
        {"industry_code": "A1", "content_type": "行业", "rank_score": 90},
        {"industry_code": "C1", "content_type": "概念", "rank_score": 95},
    ]
    assign_per_type_topn(rows, ("行业", "概念"), 10)
    by_code = {r["industry_code"]: r for r in rows}
    assert by_code["A1"]["rank_no"] == 1
    assert by_code["C1"]["rank_no"] == 1
    assert by_code["A1"]["is_top3"] == 1
    assert by_code["C1"]["is_top3"] == 1


def test_fewer_boards_than_topn() -> None:
    rows = [
        {"industry_code": "A1", "content_type": "行业", "rank_score": 80},
        {"industry_code": "A2", "content_type": "行业", "rank_score": 70},
    ]
    assign_per_type_topn(rows, ("行业",), 10)
    tops = [r for r in rows if r["is_top3"]]
    assert len(tops) == 2
    assert [r["rank_no"] for r in tops] == [1, 2]


def test_order_by_rank_score_desc() -> None:
    rows = [
        {"industry_code": "LOW", "content_type": "行业", "rank_score": 10},
        {"industry_code": "HIGH", "content_type": "行业", "rank_score": 99},
        {"industry_code": "MID", "content_type": "行业", "rank_score": 50},
    ]
    assign_per_type_topn(rows, ("行业",), 2)
    by_code = {r["industry_code"]: r for r in rows}
    assert by_code["HIGH"]["rank_no"] == 1 and by_code["HIGH"]["is_top3"] == 1
    assert by_code["MID"]["rank_no"] == 2 and by_code["MID"]["is_top3"] == 1
    assert by_code["LOW"]["rank_no"] == 3 and by_code["LOW"]["is_top3"] == 0


def main() -> int:
    tests = [
        test_industry_and_concept_each_top10,
        test_rank_no_independent_across_types,
        test_fewer_boards_than_topn,
        test_order_by_rank_score_desc,
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
