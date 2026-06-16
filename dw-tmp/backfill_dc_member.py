#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
【临时脚本 · 用完可删】
按交易日 + 板块代码循环拉取 Tushare dc_member，补全 ods_dc_member_di。

不接入 func.sh / run_data_sync；仅 dw-tmp 本地使用。

用法（须先 source dw-utils/func.sh）:
  bash dw-tmp/backfill_dc_member.sh
  bash dw-tmp/backfill_dc_member.sh --start 20250101 --end 20260611
  bash dw-tmp/backfill_dc_member.sh --start 20250601 --end 20260611 --dry-run
  bash dw-tmp/backfill_dc_member.sh --force          # 覆盖已有日期

依赖:
  - ods_trading_day 交易日历
  - 板块列表优先 ods_industry_fund_flow_di，否则 ods_dc_index_di
  - Tushare 积分≥6000、代理可用
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import date, datetime
from pathlib import Path

import pandas as pd
from sqlalchemy import text

_ROOT = Path(__file__).resolve().parent.parent
for _p in (_ROOT / "dw-utils", _ROOT / "dw-sync"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from mysql_config import get_engine  # noqa: E402
from sync_writer import write_dataframe  # noqa: E402
from task_config import apply_transform  # noqa: E402
from task_registry import fetch_tushare  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

TARGET_DB = "stock_data"
TARGET_TABLE = "ods_dc_member_di"
DEFAULT_START = "20250101"
DEFAULT_END = "20260611"

_TRANSFORM_TASK = {
    "transform_config": {
        "date_columns": {"trade_date": "%Y%m%d"},
        "dedupe": ["trade_date", "ts_code", "con_code"],
        "dropna": ["trade_date", "ts_code", "con_code"],
        "keep_columns": ["trade_date", "ts_code", "con_code", "name"],
    }
}


def _parse_yyyymmdd(s: str) -> date:
    s = s.strip().replace("-", "")
    return datetime.strptime(s, "%Y%m%d").date()


def list_trading_days(start: date, end: date) -> list[date]:
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
    if rows:
        return [r[0] for r in rows]
    logger.warning("ods_trading_day 无记录，按自然日遍历（较慢）")
    days: list[date] = []
    cur = start
    while cur <= end:
        if cur.weekday() < 5:
            days.append(cur)
        from datetime import timedelta

        cur += timedelta(days=1)
    return days


def board_codes_for_date(td: date) -> list[str]:
    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT DISTINCT industry_code AS code
                FROM ods_industry_fund_flow_di
                WHERE trade_date = :td
                UNION
                SELECT DISTINCT ts_code AS code
                FROM ods_dc_index_di
                WHERE trade_date = :td
                ORDER BY code
                """
            ),
            {"td": td},
        ).fetchall()
    return [r[0] for r in rows if r[0]]


def day_already_filled(td: date, min_boards: int) -> bool:
    engine = get_engine()
    with engine.connect() as conn:
        cnt = conn.execute(
            text(
                """
                SELECT COUNT(DISTINCT ts_code)
                FROM ods_dc_member_di
                WHERE trade_date = :td
                """
            ),
            {"td": td},
        ).scalar()
    return int(cnt or 0) >= min_boards


def fetch_day_members(td: date, codes: list[str], sleep_s: float) -> pd.DataFrame:
    td_str = td.strftime("%Y%m%d")
    frames: list[pd.DataFrame] = []
    for i, ts_code in enumerate(codes):
        if (i + 1) % 50 == 0 or i == 0:
            logger.info("  dc_member %s 进度 %s/%s", td_str, i + 1, len(codes))
        try:
            part = fetch_tushare(
                "dc_member",
                token_type="tushare",
                trade_date=td_str,
                ts_code=ts_code,
            )
        except Exception as exc:
            logger.warning("  dc_member %s %s 失败: %s", td_str, ts_code, exc)
            continue
        if not part.empty:
            frames.append(part)
        if sleep_s > 0 and i + 1 < len(codes):
            time.sleep(sleep_s)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def backfill(
    start: date,
    end: date,
    *,
    sleep_s: float = 0.2,
    min_boards_skip: int = 80,
    force: bool = False,
    dry_run: bool = False,
) -> None:
    days = list_trading_days(start, end)
    logger.info(
        "补数区间 %s ~ %s，交易日 %s 天，dry_run=%s force=%s",
        start,
        end,
        len(days),
        dry_run,
        force,
    )

    ok_days = 0
    skip_days = 0
    empty_days = 0

    for di, td in enumerate(days, start=1):
        td_str = td.strftime("%Y%m%d")
        if not force and day_already_filled(td, min_boards_skip):
            logger.info("[%s/%s] %s 已有数据(≥%s板块)，跳过", di, len(days), td_str, min_boards_skip)
            skip_days += 1
            continue

        codes = board_codes_for_date(td)
        if not codes:
            logger.warning("[%s/%s] %s 无板块列表，跳过", di, len(days), td_str)
            empty_days += 1
            continue

        logger.info("[%s/%s] %s 板块数=%s", di, len(days), td_str, len(codes))
        raw = fetch_day_members(td, codes, sleep_s)
        out = apply_transform(raw, _TRANSFORM_TASK)
        logger.info("[%s/%s] %s 拉取 %s 行，写入 %s 行", di, len(days), td_str, len(raw), len(out))

        if dry_run or out.empty:
            if out.empty:
                empty_days += 1
            continue

        rows = write_dataframe(
            database=TARGET_DB,
            table=TARGET_TABLE,
            df=out,
            sync_mode="snapshot",
            trade_date=td,
            snapshot_delete_column="trade_date",
        )
        logger.info("[%s/%s] %s 落库 %s 行", di, len(days), td_str, rows)
        ok_days += 1

    logger.info(
        "补数结束: 写入=%s 跳过=%s 空/失败日=%s 总交易日=%s",
        ok_days,
        skip_days,
        empty_days,
        len(days),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="临时补数 ods_dc_member_di")
    parser.add_argument("--start", default=DEFAULT_START, help="YYYYMMDD，默认 20250101")
    parser.add_argument("--end", default=DEFAULT_END, help="YYYYMMDD，默认 20260611")
    parser.add_argument("--sleep", type=float, default=0.2, help="板块间休眠秒数")
    parser.add_argument(
        "--min-boards-skip",
        type=int,
        default=80,
        help="当日已有不少于该板块数则跳过（--force 时无效）",
    )
    parser.add_argument("--force", action="store_true", help="覆盖已有日期")
    parser.add_argument("--dry-run", action="store_true", help="只拉数不写库")
    args = parser.parse_args()

    start = _parse_yyyymmdd(args.start)
    end = _parse_yyyymmdd(args.end)
    if start > end:
        logger.error("start > end")
        return 1

    try:
        backfill(
            start,
            end,
            sleep_s=args.sleep,
            min_boards_skip=args.min_boards_skip,
            force=args.force,
            dry_run=args.dry_run,
        )
    except Exception as exc:
        logger.exception("补数失败: %s", exc)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
