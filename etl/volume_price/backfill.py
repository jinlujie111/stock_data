"""VP 六维指标历史回溯：按交易日顺序逐日执行 run_batch。

必须升序逐日跑：continuity_strength、industry_vol_ratio_20 等依赖此前写入的
dwm_industry_vp_agg_di 历史；乱序或并行会导致前若干交易日指标不准。

用法（服务器）:
  source dw-utils/func.sh
  python -m etl.volume_price.backfill --start 20260101
  python -m etl.volume_price.backfill --start 20260101 --end 20260710
  python -m etl.volume_price.backfill --dry-run
  bash dw-dwm/backfill_vp_batch.sh 20260101 20260710
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import date, datetime
from pathlib import Path

from sqlalchemy import text

_ROOT = Path(__file__).resolve().parents[2]
for _p in (_ROOT, _ROOT / "dw-utils", _ROOT / "dw-sync"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from etl.volume_price.batch import run_batch  # noqa: E402
from etl.volume_price.db_util import (  # noqa: E402
    get_engine_stock,
    load_config,
    parse_trade_date,
)
from trade_data_flag import get_trading_dates  # noqa: E402

logger = logging.getLogger(__name__)

DEFAULT_START = date(2026, 1, 1)


def _parse_date(s: str) -> date:
    s = s.strip()
    if len(s) == 8 and s.isdigit():
        return datetime.strptime(s, "%Y%m%d").date()
    return datetime.strptime(s, "%Y-%m-%d").date()


def _default_end(engine) -> date:
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT MAX(trade_date) FROM ods_stock_detail_di")
        ).scalar()
    if row:
        return row if isinstance(row, date) else _parse_date(str(row)[:10])
    return date.today()


def _has_ods_detail(engine, trade_date: date) -> bool:
    with engine.connect() as conn:
        cnt = conn.execute(
            text("SELECT COUNT(*) FROM ods_stock_detail_di WHERE trade_date = :td"),
            {"td": trade_date},
        ).scalar()
    return int(cnt or 0) > 0


def _has_vp_score(engine, trade_date: date, window: int) -> bool:
    with engine.connect() as conn:
        cnt = conn.execute(
            text(
                """
                SELECT COUNT(*) FROM dwm_industry_vp_score_di
                WHERE trade_date = :td AND vp_window = :w
                """
            ),
            {"td": trade_date, "w": window},
        ).scalar()
    return int(cnt or 0) > 0


def _parse_content_types(s: str) -> list[str]:
    return [x.strip() for x in s.split(",") if x.strip()]


def backfill(
    start: date,
    end: date,
    *,
    content_types: list[str] | None = None,
    skip_existing: bool = False,
    continue_on_error: bool = True,
    dry_run: bool = False,
) -> dict[str, list[date] | int]:
    engine = get_engine_stock()
    cfg = load_config(engine)
    window = cfg.window_default
    ctypes = content_types or list(cfg.content_types)

    dates = get_trading_dates(start, end)
    if not dates:
        raise RuntimeError(f"区间 {start} ~ {end} 在 ods_trading_day 无交易日")

    ok: list[date] = []
    skipped: list[date] = []
    failed: list[date] = []
    no_ods: list[date] = []

    logger.info(
        "VP 回溯 %s ~ %s，共 %d 个交易日，skip_existing=%s dry_run=%s types=%s",
        dates[0],
        dates[-1],
        len(dates),
        skip_existing,
        dry_run,
        ctypes,
    )

    t0 = time.perf_counter()
    for i, td in enumerate(dates, start=1):
        if not _has_ods_detail(engine, td):
            logger.warning("[%d/%d] %s 跳过：ods_stock_detail_di 无行情", i, len(dates), td)
            no_ods.append(td)
            continue

        if skip_existing and _has_vp_score(engine, td, window):
            logger.info("[%d/%d] %s 跳过：已有 VP 评分", i, len(dates), td)
            skipped.append(td)
            continue

        if dry_run:
            logger.info("[%d/%d] %s dry-run", i, len(dates), td)
            ok.append(td)
            continue

        logger.info("[%d/%d] %s 开始 run_batch ...", i, len(dates), td)
        try:
            stats = run_batch(td, ctypes)
            logger.info(
                "[%d/%d] %s 完成 score=%d stocks=%d",
                i,
                len(dates),
                td,
                stats.get("score_rows", 0),
                stats.get("stock_rows", 0),
            )
            ok.append(td)
        except Exception as exc:
            logger.error("[%d/%d] %s 失败: %s", i, len(dates), td, exc)
            failed.append(td)
            if not continue_on_error:
                break

    elapsed = time.perf_counter() - t0
    summary = {
        "total": len(dates),
        "ok": ok,
        "skipped": skipped,
        "failed": failed,
        "no_ods": no_ods,
        "elapsed_sec": int(elapsed),
    }
    logger.info(
        "VP 回溯结束: ok=%d skipped=%d failed=%d no_ods=%d elapsed=%ds",
        len(ok),
        len(skipped),
        len(failed),
        len(no_ods),
        summary["elapsed_sec"],
    )
    if failed:
        logger.error("失败日期: %s", ", ".join(d.strftime("%Y%m%d") for d in failed))
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="VP 六维指标历史回溯（2026 起默认）")
    parser.add_argument(
        "--start",
        default=DEFAULT_START.strftime("%Y%m%d"),
        help="起始交易日 YYYYMMDD（含），默认 20260101",
    )
    parser.add_argument(
        "--end",
        default=None,
        help="结束交易日 YYYYMMDD（含），默认 ods_stock_detail_di 最大日期",
    )
    parser.add_argument("--content-types", default="行业,概念")
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="已有 dwm_industry_vp_score_di 当日数据则跳过（断点续跑）",
    )
    parser.add_argument(
        "--stop-on-error",
        action="store_true",
        help="遇错即停（默认遇错继续）",
    )
    parser.add_argument("--dry-run", action="store_true", help="只列出待跑交易日")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    start = _parse_date(args.start)
    engine = get_engine_stock()
    end = _parse_date(args.end) if args.end else _default_end(engine)
    if end < start:
        start, end = end, start

    ctypes = _parse_content_types(args.content_types)
    try:
        summary = backfill(
            start,
            end,
            content_types=ctypes,
            skip_existing=args.skip_existing,
            continue_on_error=not args.stop_on_error,
            dry_run=args.dry_run,
        )
    except RuntimeError as exc:
        logger.error("%s", exc)
        return 1

    return 1 if summary["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
