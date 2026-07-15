"""板块量价关系（VPA）日批入口。"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import date
from pathlib import Path

from sqlalchemy import text

_ROOT = Path(__file__).resolve().parents[2]
for _p in (_ROOT, _ROOT / "dw-utils"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from etl.volume_price.db_util import (  # noqa: E402
    ensure_schema,
    get_engine_stock,
    load_config,
    parse_trade_date,
)
from etl.volume_price.industry_agg import (  # noqa: E402
    aggregate_industries,
    list_target_boards,
)
from etl.volume_price.industry_score import score_industries  # noqa: E402
from etl.volume_price.stock_factors import compute_stock_factors  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# 库内与页面仅保留近半年
VP_RETENTION_DAYS = 183

STOCK_UPSERT = """
INSERT INTO dwm_stock_vp_factor_di (
    trade_date, ts_code, close, vol, amount, pct_chg, turnover_rate,
    vol_ma20, vol_ratio_20, price_ma20, price_trend_20, vol_streak_days,
    is_breakout_60, is_breakout_strict, vp_pattern, vp_pattern_score, vp_window
) VALUES (
    :trade_date, :ts_code, :close, :vol, :amount, :pct_chg, :turnover_rate,
    :vol_ma20, :vol_ratio_20, :price_ma20, :price_trend_20, :vol_streak_days,
    :is_breakout_60, :is_breakout_strict, :vp_pattern, :vp_pattern_score, :vp_window
)
ON DUPLICATE KEY UPDATE
    close=VALUES(close), vol=VALUES(vol), amount=VALUES(amount),
    pct_chg=VALUES(pct_chg), turnover_rate=VALUES(turnover_rate),
    vol_ma20=VALUES(vol_ma20), vol_ratio_20=VALUES(vol_ratio_20),
    price_ma20=VALUES(price_ma20), price_trend_20=VALUES(price_trend_20),
    vol_streak_days=VALUES(vol_streak_days), is_breakout_60=VALUES(is_breakout_60),
    is_breakout_strict=VALUES(is_breakout_strict),
    vp_pattern=VALUES(vp_pattern), vp_pattern_score=VALUES(vp_pattern_score),
    updated_at=CURRENT_TIMESTAMP
"""

AGG_UPSERT = """
INSERT INTO dwm_industry_vp_agg_di (
    trade_date, industry_code, industry_name, content_type, member_cnt,
    total_amount, avg_pct_chg, rising_ratio, vol_expand_ratio, breakout_ratio,
    industry_vol_ratio_20, amount_streak_days, continuity_strength,
    trend_return_20d, leader_strength, weight_mode, vp_window
) VALUES (
    :trade_date, :industry_code, :industry_name, :content_type, :member_cnt,
    :total_amount, :avg_pct_chg, :rising_ratio, :vol_expand_ratio, :breakout_ratio,
    :industry_vol_ratio_20, :amount_streak_days, :continuity_strength,
    :trend_return_20d, :leader_strength, :weight_mode, :vp_window
)
ON DUPLICATE KEY UPDATE
    industry_name=VALUES(industry_name), content_type=VALUES(content_type),
    member_cnt=VALUES(member_cnt), total_amount=VALUES(total_amount),
    avg_pct_chg=VALUES(avg_pct_chg), rising_ratio=VALUES(rising_ratio),
    vol_expand_ratio=VALUES(vol_expand_ratio), breakout_ratio=VALUES(breakout_ratio),
    industry_vol_ratio_20=VALUES(industry_vol_ratio_20),
    amount_streak_days=VALUES(amount_streak_days),
    continuity_strength=VALUES(continuity_strength),
    trend_return_20d=VALUES(trend_return_20d),
    leader_strength=VALUES(leader_strength),
    weight_mode=VALUES(weight_mode),
    updated_at=CURRENT_TIMESTAMP
"""

SCORE_UPSERT = """
INSERT INTO dwm_industry_vp_score_di (
    trade_date, industry_code, industry_name, content_type, vp_window,
    score_vol, score_trend, score_continuity, score_breadth, score_breakout, score_leader,
    vp_score, vp_status, signal_type, rank_vp, member_cnt,
    industry_vol_ratio_20, rising_ratio, breakout_ratio, amount_streak_days,
    continuity_strength, trend_return_20d, leader_strength, detail_json
) VALUES (
    :trade_date, :industry_code, :industry_name, :content_type, :vp_window,
    :score_vol, :score_trend, :score_continuity, :score_breadth, :score_breakout, :score_leader,
    :vp_score, :vp_status, :signal_type, :rank_vp, :member_cnt,
    :industry_vol_ratio_20, :rising_ratio, :breakout_ratio, :amount_streak_days,
    :continuity_strength, :trend_return_20d, :leader_strength, :detail_json
)
ON DUPLICATE KEY UPDATE
    industry_name=VALUES(industry_name), content_type=VALUES(content_type),
    score_vol=VALUES(score_vol), score_trend=VALUES(score_trend),
    score_continuity=VALUES(score_continuity), score_breadth=VALUES(score_breadth),
    score_breakout=VALUES(score_breakout), score_leader=VALUES(score_leader),
    vp_score=VALUES(vp_score), vp_status=VALUES(vp_status),
    signal_type=VALUES(signal_type), rank_vp=VALUES(rank_vp), member_cnt=VALUES(member_cnt),
    industry_vol_ratio_20=VALUES(industry_vol_ratio_20),
    rising_ratio=VALUES(rising_ratio), breakout_ratio=VALUES(breakout_ratio),
    amount_streak_days=VALUES(amount_streak_days),
    continuity_strength=VALUES(continuity_strength),
    trend_return_20d=VALUES(trend_return_20d),
    leader_strength=VALUES(leader_strength),
    detail_json=VALUES(detail_json),
    updated_at=CURRENT_TIMESTAMP
"""


def _parse_content_types(s: str) -> list[str]:
    return [x.strip() for x in s.split(",") if x.strip()]


def _chunk_insert(conn, sql: str, rows: list[dict], size: int = 500) -> None:
    for i in range(0, len(rows), size):
        conn.execute(text(sql), rows[i : i + size])


def run_batch(
    trade_date: date,
    content_types: list[str] | None = None,
    *,
    workers: int = 8,
) -> dict[str, int]:
    engine = get_engine_stock()
    ensure_schema(engine)
    cfg = load_config(engine)
    ctypes = content_types or list(cfg.content_types)
    window = cfg.window_default

    detail_cnt = engine.connect().execute(
        text("SELECT COUNT(*) FROM ods_stock_detail_di WHERE trade_date = :td"),
        {"td": trade_date},
    ).scalar()
    if not detail_cnt:
        raise RuntimeError(f"ods_stock_detail_di 无数据: {trade_date}")

    factors = compute_stock_factors(engine, trade_date, cfg)
    boards = list_target_boards(engine, trade_date, ctypes, cfg.min_member_cnt)
    if not boards:
        raise RuntimeError(f"无目标板块: {trade_date} types={ctypes}")

    logger.info(
        "vp_batch start trade_date=%s stocks=%d boards=%d window=%d",
        trade_date,
        len(factors),
        len(boards),
        window,
    )

    with engine.begin() as conn:
        conn.execute(
            text("DELETE FROM dwm_stock_vp_factor_di WHERE trade_date = :td AND vp_window = :w"),
            {"td": trade_date, "w": window},
        )
        _chunk_insert(conn, STOCK_UPSERT, factors)

    agg_rows = aggregate_industries(engine, trade_date, boards, factors, cfg)
    if not agg_rows:
        raise RuntimeError("行业聚合未产出任何记录")

    score_rows = score_industries(agg_rows, cfg)

    with engine.begin() as conn:
        conn.execute(
            text("DELETE FROM dwm_industry_vp_agg_di WHERE trade_date = :td AND vp_window = :w"),
            {"td": trade_date, "w": window},
        )
        conn.execute(
            text("DELETE FROM dwm_industry_vp_score_di WHERE trade_date = :td AND vp_window = :w"),
            {"td": trade_date, "w": window},
        )
        _chunk_insert(conn, AGG_UPSERT, agg_rows)
        _chunk_insert(conn, SCORE_UPSERT, score_rows)
        purged_factor = conn.execute(
            text(
                """
                DELETE FROM dwm_stock_vp_factor_di
                WHERE trade_date < DATE_SUB(:td, INTERVAL :days DAY)
                """
            ),
            {"td": trade_date, "days": VP_RETENTION_DAYS},
        ).rowcount
        purged_agg = conn.execute(
            text(
                """
                DELETE FROM dwm_industry_vp_agg_di
                WHERE trade_date < DATE_SUB(:td, INTERVAL :days DAY)
                """
            ),
            {"td": trade_date, "days": VP_RETENTION_DAYS},
        ).rowcount
        purged_score = conn.execute(
            text(
                """
                DELETE FROM dwm_industry_vp_score_di
                WHERE trade_date < DATE_SUB(:td, INTERVAL :days DAY)
                """
            ),
            {"td": trade_date, "days": VP_RETENTION_DAYS},
        ).rowcount

    by_type = {}
    for r in score_rows:
        ct = r.get("content_type") or "?"
        by_type[ct] = by_type.get(ct, 0) + 1

    stats = {
        "stock_rows": len(factors),
        "board_total": len(boards),
        "agg_rows": len(agg_rows),
        "score_rows": len(score_rows),
        "purged_factor_rows": int(purged_factor or 0),
        "purged_agg_rows": int(purged_agg or 0),
        "purged_score_rows": int(purged_score or 0),
        "retention_days": VP_RETENTION_DAYS,
        "by_type": by_type,
    }
    logger.info("vp_batch done %s", stats)
    return stats


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="板块量价 VPA 日批")
    parser.add_argument("trade_date", nargs="?", help="YYYYMMDD")
    parser.add_argument("--content-types", default="行业,概念")
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args(argv)

    if args.trade_date:
        td = parse_trade_date(args.trade_date)
    else:
        engine = get_engine_stock()
        row = engine.connect().execute(
            text("SELECT MAX(trade_date) FROM ods_stock_detail_di")
        ).scalar()
        if not row:
            logger.error("无法解析交易日")
            return 1
        td = row if isinstance(row, date) else parse_trade_date(str(row).replace("-", "")[:8])

    ctypes = _parse_content_types(args.content_types)
    try:
        run_batch(td, ctypes, workers=args.workers)
    except Exception as exc:
        logger.error("%s", exc)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
