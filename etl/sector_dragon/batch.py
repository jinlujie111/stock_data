"""行业+概念板块龙头 MVP 批处理入口。"""
from __future__ import annotations

import argparse
import logging
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from pathlib import Path

from sqlalchemy import text

# 允许从仓库根目录 python -m etl.sector_dragon.batch 运行
_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
_UTILS = _ROOT / "dw-utils"
if str(_UTILS) not in sys.path:
    sys.path.insert(0, str(_UTILS))

from etl.sector_dragon.db_util import (  # noqa: E402
    DragonConfig,
    ensure_schema,
    get_engine_stock,
    list_boards,
    load_config,
    parse_trade_date,
)
from etl.sector_dragon.score_mvp import score_board_mvp  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

SCORE_INSERT = """
INSERT INTO dwm_sector_stock_dragon_score_di (
    trade_date, industry_code, industry_name, content_type, ts_code, stock_name,
    score_industry, score_fund, score_trend, score_inst, score_composite,
    rank_industry, rank_fund, rank_trend, rank_inst, rank_composite,
    is_industry_leader, is_fund_leader, is_trend_leader, is_inst_leader, is_composite_leader,
    score_mode, industry_as_of, inst_as_of, detail_json
) VALUES (
    :trade_date, :industry_code, :industry_name, :content_type, :ts_code, :stock_name,
    :score_industry, :score_fund, :score_trend, :score_inst, :score_composite,
    :rank_industry, :rank_fund, :rank_trend, :rank_inst, :rank_composite,
    :is_industry_leader, :is_fund_leader, :is_trend_leader, :is_inst_leader, :is_composite_leader,
    :score_mode, :industry_as_of, :inst_as_of, :detail_json
)
ON DUPLICATE KEY UPDATE
    industry_name=VALUES(industry_name), content_type=VALUES(content_type),
    stock_name=VALUES(stock_name),
    score_industry=VALUES(score_industry), score_fund=VALUES(score_fund),
    score_trend=VALUES(score_trend), score_inst=VALUES(score_inst),
    score_composite=VALUES(score_composite),
    rank_industry=VALUES(rank_industry), rank_fund=VALUES(rank_fund),
    rank_trend=VALUES(rank_trend), rank_inst=VALUES(rank_inst),
    rank_composite=VALUES(rank_composite),
    is_industry_leader=VALUES(is_industry_leader), is_fund_leader=VALUES(is_fund_leader),
    is_trend_leader=VALUES(is_trend_leader), is_inst_leader=VALUES(is_inst_leader),
    is_composite_leader=VALUES(is_composite_leader),
    inst_as_of=VALUES(inst_as_of), detail_json=VALUES(detail_json),
    updated_at=CURRENT_TIMESTAMP
"""

SUMMARY_INSERT = """
INSERT INTO sector_dragon_summary_di (
    trade_date, industry_code, industry_name, content_type,
    leader_industry_ts, leader_industry_name,
    leader_fund_ts, leader_fund_name,
    leader_trend_ts, leader_trend_name,
    leader_inst_ts, leader_inst_name,
    leader_composite_ts, leader_composite_name,
    summary_text, score_mode
) VALUES (
    :trade_date, :industry_code, :industry_name, :content_type,
    :leader_industry_ts, :leader_industry_name,
    :leader_fund_ts, :leader_fund_name,
    :leader_trend_ts, :leader_trend_name,
    :leader_inst_ts, :leader_inst_name,
    :leader_composite_ts, :leader_composite_name,
    :summary_text, :score_mode
)
ON DUPLICATE KEY UPDATE
    industry_name=VALUES(industry_name), content_type=VALUES(content_type),
    leader_industry_ts=VALUES(leader_industry_ts), leader_industry_name=VALUES(leader_industry_name),
    leader_fund_ts=VALUES(leader_fund_ts), leader_fund_name=VALUES(leader_fund_name),
    leader_trend_ts=VALUES(leader_trend_ts), leader_trend_name=VALUES(leader_trend_name),
    leader_inst_ts=VALUES(leader_inst_ts), leader_inst_name=VALUES(leader_inst_name),
    leader_composite_ts=VALUES(leader_composite_ts), leader_composite_name=VALUES(leader_composite_name),
    summary_text=VALUES(summary_text),
    updated_at=CURRENT_TIMESTAMP
"""


def _parse_content_types(s: str) -> list[str]:
    return [x.strip() for x in s.split(",") if x.strip()]


def _process_board(
    trade_date: date,
    board: dict,
    cfg: DragonConfig,
) -> tuple[list[dict], dict | None]:
    engine = get_engine_stock()
    return score_board_mvp(engine, trade_date, board, cfg)


def run_batch(
    trade_date: date,
    content_types: list[str],
    *,
    workers: int = 8,
    score_mode: str = "mvp",
) -> dict[str, int]:
    engine = get_engine_stock()
    ensure_schema(engine)
    cfg = load_config(engine, content_types)
    cfg.score_mode = score_mode

    mem_cnt = engine.connect().execute(
        text("SELECT COUNT(*) FROM ods_dc_member_di WHERE trade_date = :td"),
        {"td": trade_date},
    ).scalar()
    if not mem_cnt:
        raise RuntimeError(f"ods_dc_member_di 无数据: {trade_date}")

    boards = list_boards(
        engine, trade_date, content_types, min_constituents=cfg.min_constituents,
    )
    if not boards:
        raise RuntimeError(f"无目标板块: {trade_date} types={content_types}")

    by_type = Counter(b.get("content_type") for b in boards)
    logger.info(
        "batch start trade_date=%s boards=%d by_type=%s workers=%d types=%s",
        trade_date, len(boards), dict(by_type), workers, content_types,
    )

    with engine.begin() as conn:
        conn.execute(
            text(
                "DELETE FROM dwm_sector_stock_dragon_score_di "
                "WHERE trade_date = :td AND score_mode = :mode"
            ),
            {"td": trade_date, "mode": score_mode},
        )
        conn.execute(
            text(
                "DELETE FROM sector_dragon_summary_di "
                "WHERE trade_date = :td AND score_mode = :mode"
            ),
            {"td": trade_date, "mode": score_mode},
        )

    all_scores: list[dict] = []
    summaries: list[dict] = []
    skipped = 0

    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = {
            pool.submit(_process_board, trade_date, b, cfg): b
            for b in boards
        }
        for fut in as_completed(futures):
            board = futures[fut]
            try:
                scores, summary = fut.result()
            except Exception:
                logger.exception("board failed %s", board.get("industry_code"))
                skipped += 1
                continue
            if not scores:
                skipped += 1
                continue
            all_scores.extend(scores)
            if summary:
                summaries.append(summary)

    if not all_scores:
        raise RuntimeError("批处理未产出任何评分")

    with engine.begin() as conn:
        conn.execute(text(SCORE_INSERT), all_scores)
        conn.execute(text(SUMMARY_INSERT), summaries)

    stats = {
        "boards_total": len(boards),
        "boards_ok": len(summaries),
        "boards_skipped": skipped,
        "score_rows": len(all_scores),
        "ok_by_type": dict(Counter(s.get("content_type") for s in summaries)),
    }
    logger.info("batch done %s", stats)
    return stats


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="板块龙头 MVP 批处理")
    parser.add_argument("trade_date", nargs="?", help="YYYYMMDD")
    parser.add_argument(
        "--content-types",
        default="行业,概念",
        help="逗号分隔板块类型",
    )
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--score-mode", default="mvp")
    args = parser.parse_args(argv)

    if args.trade_date:
        td = parse_trade_date(args.trade_date)
    else:
        engine = get_engine_stock()
        row = engine.connect().execute(
            text("SELECT MAX(trade_date) FROM ods_dc_member_di")
        ).scalar()
        if not row:
            logger.error("无法解析交易日")
            return 1
        td = row if isinstance(row, date) else parse_trade_date(str(row).replace("-", "")[:8])

    ctypes = _parse_content_types(args.content_types)
    try:
        run_batch(td, ctypes, workers=args.workers, score_mode=args.score_mode)
    except Exception as exc:
        logger.error("%s", exc)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
