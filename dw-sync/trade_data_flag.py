#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
根据 stock_data.ods_trading_day 判断是否为交易日。

规则：指定日期存在于 ods_trading_day.trade_date 中 → 交易日，返回 1；否则返回 0。

用法（须 source dw-utils/func.sh 或经 sync_runner.sh）：
  python dw-sync/trade_data_flag.py              # 检查今天，stdout 输出 0 或 1
  python dw-sync/trade_data_flag.py 20260529
"""
from __future__ import annotations

import argparse
import sys
from datetime import date, datetime
from pathlib import Path

_DW_ROOT = Path(__file__).resolve().parent.parent
_DW_UTILS = _DW_ROOT / "dw-utils"
if str(_DW_UTILS) not in sys.path:
    sys.path.insert(0, str(_DW_UTILS))

from sqlalchemy import text  # noqa: E402

from mysql_config import get_engine  # noqa: E402


def parse_check_date(s: str | None) -> date:
    if not s:
        return date.today()
    s = s.strip()
    if len(s) == 8 and s.isdigit():
        return datetime.strptime(s, "%Y%m%d").date()
    return datetime.strptime(s, "%Y-%m-%d").date()


def get_trade_day_flag(check_date: date | None = None) -> int:
    """
    查询 ods_trading_day，日期在表中返回 1（交易日），否则 0（非交易日）。
    """
    d = check_date or date.today()
    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT 1 FROM ods_trading_day WHERE trade_date = :d LIMIT 1"
            ),
            {"d": d},
        ).first()
    return 1 if row else 0


def is_trading_day(check_date: date | None = None) -> bool:
    return get_trade_day_flag(check_date) == 1


def get_trading_dates(start: date, end: date) -> list[date]:
    """返回 [start, end] 内 ods_trading_day 的交易日列表（升序）。"""
    if end < start:
        start, end = end, start
    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT trade_date
                FROM ods_trading_day
                WHERE trade_date >= :s AND trade_date <= :e
                ORDER BY trade_date
                """
            ),
            {"s": start, "e": end},
        ).fetchall()
    return [r[0] for r in rows]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="交易日标识：1=ods_trading_day 中存在，0=不存在"
    )
    parser.add_argument(
        "check_date",
        nargs="?",
        default=None,
        help="待检查日期 YYYYMMDD 或 YYYY-MM-DD，默认今天",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    print(get_trade_day_flag(parse_check_date(args.check_date)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
