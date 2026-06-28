#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
按 Tushare fina_indicator_vip 的 period 单季回补 ods_fina_indicator。

只删除并重写指定报告期（end_date），不 TRUNCATE 全表。

用法（须经 backfill_fina_indicator_period.sh 或已 source func.sh 且设置 PYTHONPATH）：
  python dw-sync/backfill_fina_indicator_period.py 20251231
  python dw-sync/backfill_fina_indicator_period.py 20251231 --dry-run
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from sqlalchemy import text

_DW_ROOT = Path(__file__).resolve().parent.parent
_DW_UTILS = _DW_ROOT / "dw-utils"
_DW_SYNC = _DW_ROOT / "dw-sync"
for _p in (_DW_UTILS, _DW_SYNC):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from mysql_config import get_target_engine, load_sync_tasks  # noqa: E402
from task_config import apply_transform  # noqa: E402
from tushare_client import get_tushare_pro  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def parse_period(s: str) -> tuple[str, str]:
    s = s.strip().replace("-", "")
    if len(s) != 8 or not s.isdigit():
        raise ValueError("period 格式应为 YYYYMMDD，如 20251231")
    end_date = f"{s[0:4]}-{s[4:6]}-{s[6:8]}"
    return s, end_date


def backfill_period(period: str, *, dry_run: bool = False) -> int:
    period_yyyymmdd, end_date = parse_period(period)
    tasks = load_sync_tasks(source_table="fina_indicator_vip")
    if not tasks:
        raise RuntimeError("db_sync_task 中未找到 fina_indicator_vip（status=1）")
    task = tasks[0]

    logger.info("拉取 fina_indicator_vip period=%s", period_yyyymmdd)
    pro = get_tushare_pro()
    df = pro.fina_indicator_vip(period=period_yyyymmdd)
    if df is None or df.empty:
        logger.warning("Tushare 返回 0 行，period=%s", period_yyyymmdd)
        return 0

    stock_cnt = df["ts_code"].nunique()
    logger.info(
        "Tushare 返回 %s 行，%s 只股票",
        len(df),
        stock_cnt,
    )

    out = apply_transform(df, task)
    logger.info("映射后 %s 行", len(out))

    if dry_run:
        logger.info("dry-run：不写库")
        return len(out)

    engine = get_target_engine(task["target_database"])
    table = task["target_table"]
    with engine.begin() as conn:
        result = conn.execute(
            text(f"DELETE FROM `{table}` WHERE end_date = :end_date"),
            {"end_date": end_date},
        )
        deleted = result.rowcount
        logger.info("已删除 end_date=%s 旧数据 %s 行", end_date, deleted)

    out.to_sql(
        table,
        engine,
        if_exists="append",
        index=False,
        method="multi",
        chunksize=500,
    )
    logger.info("已写入 end_date=%s 共 %s 行", end_date, len(out))
    return len(out)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="按 period 单季回补 ods_fina_indicator（不 TRUNCATE 全表）"
    )
    parser.add_argument(
        "period",
        help="报告期 YYYYMMDD，如 20251231",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只拉取并统计，不写库",
    )
    args = parser.parse_args(argv)
    backfill_period(args.period, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
