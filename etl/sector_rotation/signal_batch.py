"""每日板块轮动信号批处理。

用法:
  python -m etl.sector_rotation.signal_batch
  python -m etl.sector_rotation.signal_batch 20260715
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import date
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
for _p in (_ROOT, _ROOT / "dw-utils"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from etl.db_util import (  # noqa: E402
    get_industry_engine,
    get_stock_engine,
    latest_trade_date,
    list_trading_days,
    parse_trade_date,
    trading_days_before,
)
from etl.sector_rotation.factors import load_panel_from_mysql  # noqa: E402
from etl.sector_rotation.signals import generate_all  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def run(start: date, end: date) -> int:
    stock_engine = get_stock_engine()
    industry_engine = get_industry_engine()
    days = list_trading_days(stock_engine, start, end)
    if not days:
        logger.error("区间无交易日: %s ~ %s", start, end)
        return 1
    pad = trading_days_before(stock_engine, days[0], 130)
    panel_start = pad[0] if pad else days[0]
    panel = load_panel_from_mysql(stock_engine, panel_start, days[-1])
    for d in days:
        stats = generate_all(d, stock_engine, industry_engine, panel)
        logger.info("轮动信号完成 %s: %s", d, stats)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="每日板块轮动信号")
    parser.add_argument("start", nargs="?", help="YYYYMMDD")
    parser.add_argument("end", nargs="?", help="YYYYMMDD")
    args = parser.parse_args(argv)
    stock_engine = get_stock_engine()
    if args.start and args.end:
        start, end = parse_trade_date(args.start), parse_trade_date(args.end)
    elif args.start:
        start = end = parse_trade_date(args.start)
    else:
        latest = latest_trade_date(stock_engine)
        if not latest:
            logger.error("无法确定最新交易日")
            return 1
        start = end = latest
    return run(start, end)


if __name__ == "__main__":
    raise SystemExit(main())
