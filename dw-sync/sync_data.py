#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
按 data_config.db_sync_task 配置，将外部数据源每日同步到目标 MySQL 表。

用法（须通过 sync_runner.sh，以加载 dw-utils/func.sh 环境变量）：
  bash dw-sync/sync_runner.sh [YYYYMMDD] [--task-id ID] [--source-table NAME] [--dry-run]

示例：
  bash dw-sync/sync_runner.sh                    # 跑全部 status=1 任务
  bash dw-sync/sync_runner.sh 20260525 --source-table tool_trade_date_hist_sina
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import date, datetime
from pathlib import Path

_DW_ROOT = Path(__file__).resolve().parent.parent
_DW_UTILS = _DW_ROOT / "dw-utils"
_DW_SYNC = _DW_ROOT / "dw-sync"
for _p in (_DW_UTILS, _DW_SYNC):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from mysql_config import load_sync_tasks  # noqa: E402
from task_registry import SyncResult, run_task  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def ensure_dw_loaded() -> None:
    if os.getenv("DW_FUNC_LOADED") != "1":
        logger.warning(
            "未检测到 DW_FUNC_LOADED=1，将使用环境变量默认值；"
            "请先 source dw-utils/func.sh（或 DW_ENV=pre source ...）再执行"
        )


def parse_trade_date(s: str | None) -> date | None:
    if not s:
        return date.today()
    s = s.strip()
    if len(s) == 8 and s.isdigit():
        return datetime.strptime(s, "%Y%m%d").date()
    return datetime.strptime(s, "%Y-%m-%d").date()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="db_sync_task 配置驱动数据同步")
    parser.add_argument(
        "trade_date",
        nargs="?",
        default=None,
        help="业务日期 YYYYMMDD 或 YYYY-MM-DD，默认今天",
    )
    parser.add_argument("--task-id", type=int, default=None, help="仅执行指定任务 id")
    parser.add_argument("--source-table", default=None, help="仅执行指定 source_table")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只拉取并统计行数，不写库",
    )
    return parser.parse_args(argv)


def run_sync(
    trade_date: date | None,
    *,
    task_id: int | None = None,
    source_table: str | None = None,
    dry_run: bool = False,
) -> list[SyncResult]:
    tasks = load_sync_tasks(task_id=task_id, source_table=source_table)
    if not tasks:
        logger.warning("未找到符合条件的 db_sync_task（status=1）")
        return []

    results: list[SyncResult] = []
    failed = 0
    for task in tasks:
        try:
            result = run_task(task, trade_date, dry_run)
            results.append(result)
            if result.ok:
                logger.info(
                    "完成 id=%s %s -> %s.%s rows=%s %s",
                    result.task_id,
                    result.source_table,
                    task["target_database"],
                    result.target_table,
                    result.rows_affected,
                    result.message or "",
                )
            else:
                failed += 1
                logger.error(
                    "跳过 id=%s %s: %s",
                    result.task_id,
                    result.source_table,
                    result.message,
                )
        except Exception as exc:
            failed += 1
            logger.exception(
                "失败 id=%s %s -> %s.%s: %s",
                task["id"],
                task["source_table"],
                task["target_database"],
                task["target_table"],
                exc,
            )
            results.append(
                SyncResult(
                    task_id=task["id"],
                    source_table=task["source_table"],
                    target_table=task["target_table"],
                    rows_affected=0,
                    ok=False,
                    message=str(exc),
                )
            )

    ok_count = sum(1 for r in results if r.ok)
    logger.info("同步结束: 成功 %s / 共 %s", ok_count, len(results))
    if failed:
        raise SystemExit(1)
    return results


def main(argv: list[str] | None = None) -> None:
    ensure_dw_loaded()
    args = parse_args(argv)
    td = parse_trade_date(args.trade_date)
    logger.info("业务日期: %s dry_run=%s", td, args.dry_run)
    run_sync(
        td,
        task_id=args.task_id,
        source_table=args.source_table,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
