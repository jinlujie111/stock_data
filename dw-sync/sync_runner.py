#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
配置驱动的统一同步入口：从 data_config.db_sync_task 读取任务，按依赖调度各 ETL。

必须通过 dw/sync/sync_runner.sh 启动（内部 source dw/utils/func.sh），
禁止直接 python 运行（配置不得写死在代码中）。
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
import uuid
from datetime import date, datetime
from pathlib import Path

from func_env import FuncEnvError, ensure_func_loaded, require_env

LOG = logging.getLogger(__name__)

_SYNC_DIR = Path(__file__).resolve().parent


def _setup_path() -> Path:
    ensure_func_loaded()
    root = require_env("STOCK_DATA_ROOT")
    stock_root = Path(root)
    if not stock_root.is_dir():
        raise FileNotFoundError(f"STOCK_DATA_ROOT 不存在: {stock_root}")
    root_str = str(stock_root.resolve())
    if root_str not in sys.path:
        sys.path.insert(0, root_str)
    if str(_SYNC_DIR) not in sys.path:
        sys.path.insert(0, str(_SYNC_DIR))
    return stock_root


def _parse_trade_date_arg(raw: str | None) -> date | None:
    if not raw:
        return None
    s = raw.strip()
    if len(s) == 8 and s.isdigit():
        return datetime.strptime(s, "%Y%m%d").date()
    return datetime.strptime(s, "%Y-%m-%d").date()


def _make_run_id() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:8]


def run_sync(
    *,
    trade_date: str | None = None,
    task_codes: list[str] | None = None,
    dry_run: bool = False,
    stop_on_error: bool = True,
) -> int:
    _setup_path()

    from db_config import (
        SyncTask,
        apply_tokens_to_env,
        insert_sync_log,
        load_sync_tasks,
        mark_task_finished,
        mark_task_running,
        topological_sort,
    )
    from task_registry import get_runner

    if not dry_run:
        apply_tokens_to_env()

    try:
        tasks = load_sync_tasks(task_codes=task_codes)
    except FuncEnvError:
        raise
    except Exception as exc:  # noqa: BLE001
        LOG.error("读取 db_sync_task 失败，请先执行: source dw/utils/func.sh && init_data_config_schema: %s", exc)
        return 1

    if not tasks:
        LOG.warning("没有可执行的同步任务（检查 db_sync_task.status 或 --task-code）")
        return 0

    ordered = topological_sort(tasks)
    run_id = _make_run_id()
    biz_date = _parse_trade_date_arg(trade_date)
    trade_date_str = trade_date or (biz_date.strftime("%Y%m%d") if biz_date else None)

    LOG.info("批次 %s：共 %d 个任务", run_id, len(ordered))
    for t in ordered:
        LOG.info(
            "  [%03d] %s (%s) → %s.%s",
            t.sort_order,
            t.task_code,
            t.script_key,
            t.target_database,
            t.target_table,
        )

    if dry_run:
        LOG.info("dry-run 模式，不实际执行")
        return 0

    failed = 0
    for task in ordered:
        if not _run_one_task(
            task=task,
            run_id=run_id,
            trade_date_str=trade_date_str,
            biz_date=biz_date,
            get_runner=get_runner,
            mark_task_running=mark_task_running,
            mark_task_finished=mark_task_finished,
            insert_sync_log=insert_sync_log,
        ):
            failed += 1
            if stop_on_error:
                LOG.error("任务 %s 失败，停止后续任务", task.task_code)
                break

    if failed:
        LOG.error("同步结束：失败 %d / %d", failed, len(ordered))
        return 1
    LOG.info("同步全部成功：%d 个任务", len(ordered))
    return 0


def _run_one_task(
    *,
    task: SyncTask,
    run_id: str,
    trade_date_str: str | None,
    biz_date: date | None,
    get_runner,
    mark_task_running,
    mark_task_finished,
    insert_sync_log,
) -> bool:
    started = datetime.now()
    LOG.info(
        ">>> 开始 %s — %s [%s → %s.%s]",
        task.task_code,
        task.task_name,
        task.source_channel,
        task.target_database,
        task.target_table,
    )
    mark_task_running(task.task_code)
    rows: int | None = None
    err: str | None = None
    try:
        fn = get_runner(task.script_key)
        result = fn(
            trade_date=trade_date_str,
            script_args=task.script_args,
            target_database=task.target_database,
            target_table=task.target_table,
            source_channel=task.source_channel,
            sync_mode=task.sync_mode,
            task_code=task.task_code,
        )
        rows = int(result) if result is not None else None
        mark_task_finished(task.task_code, success=True)
        insert_sync_log(
            run_id=run_id,
            task_code=task.task_code,
            trade_date=biz_date,
            status="success",
            rows_affected=rows,
            started_at=started,
            finished_at=datetime.now(),
            error_msg=None,
        )
        LOG.info("<<< 完成 %s rows=%s", task.task_code, rows)
        return True
    except Exception as exc:  # noqa: BLE001
        err = str(exc)
        LOG.exception("<<< 失败 %s: %s", task.task_code, err)
        mark_task_finished(task.task_code, success=False, error_msg=err[:4000])
        insert_sync_log(
            run_id=run_id,
            task_code=task.task_code,
            trade_date=biz_date,
            status="failed",
            rows_affected=rows,
            started_at=started,
            finished_at=datetime.now(),
            error_msg=err[:4000],
        )
        return False


def _cmd_list() -> None:
    _setup_path()
    from db_config import get_config_connection, load_sync_tasks

    tasks = load_sync_tasks(include_disabled=True)
    meta_map: dict[str, dict] = {}
    try:
        with get_config_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT task_code, status, last_sync_status, last_sync_time FROM db_sync_task"
                )
                for row in cur.fetchall():
                    meta_map[row["task_code"]] = row
    except Exception as exc:  # noqa: BLE001
        LOG.warning("无法读取任务状态元数据: %s", exc)

    print(f"{'启用':<4} {'顺序':<5} {'task_code':<30} {'script_key':<28} {'目标表'}")
    print("-" * 100)
    for t in tasks:
        meta = meta_map.get(t.task_code, {})
        on = "Y" if meta.get("status") == 1 else "N"
        last = ""
        if meta.get("last_sync_time"):
            last = f" | {meta.get('last_sync_status')} @ {meta['last_sync_time']}"
        print(f"{on:<4} {t.sort_order:<5} {t.task_code:<30} {t.script_key:<28} {t.target_table}{last}")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    parser = argparse.ArgumentParser(
        description="从 data_config 配置表驱动数据源→MySQL 同步（须通过 sync_runner.sh 启动）"
    )
    parser.add_argument("--trade-date", default=None, help="业务日期 YYYYMMDD 或 YYYY-MM-DD")
    parser.add_argument("--task-code", action="append", dest="task_codes", help="仅执行指定任务")
    parser.add_argument("--dry-run", action="store_true", help="只打印任务列表不执行")
    parser.add_argument("--continue-on-error", action="store_true", help="失败后继续")
    parser.add_argument("--list", action="store_true", help="列出配置表中的全部任务")
    args = parser.parse_args()

    try:
        if args.list:
            _cmd_list()
            return
        code = run_sync(
            trade_date=args.trade_date,
            task_codes=args.task_codes,
            dry_run=args.dry_run,
            stop_on_error=not args.continue_on_error,
        )
    except FuncEnvError as exc:
        LOG.error("%s", exc)
        raise SystemExit(2) from exc

    raise SystemExit(code)


if __name__ == "__main__":
    main()
