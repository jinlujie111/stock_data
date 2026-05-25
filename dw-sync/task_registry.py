#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
同步任务处理器注册表。
键格式：{proxy_source}:{source_table}，与 db_sync_task 中字段对应。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Callable

import pandas as pd

logger = logging.getLogger(__name__)

TaskDict = dict[str, Any]
TaskHandler = Callable[[TaskDict, date | None, bool], "SyncResult"]

_HANDLERS: dict[str, TaskHandler] = {}


@dataclass
class SyncResult:
    task_id: int
    source_table: str
    target_table: str
    rows_affected: int
    ok: bool
    message: str = ""


def task_key(proxy_source: str, source_table: str) -> str:
    return f"{proxy_source}:{source_table}"


def register(proxy_source: str, source_table: str) -> Callable[[TaskHandler], TaskHandler]:
    def decorator(fn: TaskHandler) -> TaskHandler:
        _HANDLERS[task_key(proxy_source, source_table)] = fn
        return fn

    return decorator


def get_handler(task: TaskDict) -> TaskHandler | None:
    return _HANDLERS.get(task_key(task["proxy_source"], task["source_table"]))


def fetch_akshare(source_table: str) -> pd.DataFrame:
    import akshare as ak

    fn = getattr(ak, source_table, None)
    if fn is None or not callable(fn):
        raise ValueError(f"akshare 未找到接口: {source_table}")
    df = fn()
    if not isinstance(df, pd.DataFrame):
        raise TypeError(f"{source_table} 返回值不是 DataFrame")
    return df


def _normalize_trade_date_series(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, errors="coerce").dt.date


@register("akshare", "tool_trade_date_hist_sina")
def sync_trading_day(task: TaskDict, trade_date: date | None, dry_run: bool) -> SyncResult:
    """全量同步交易日历 → ods_trading_day。"""
    from sync_writer import write_dataframe

    df = fetch_akshare(task["source_table"])
    if "trade_date" not in df.columns:
        raise ValueError(f"接口 {task['source_table']} 缺少 trade_date 列")

    out = pd.DataFrame({"trade_date": _normalize_trade_date_series(df["trade_date"])})
    out = out.dropna(subset=["trade_date"]).drop_duplicates(subset=["trade_date"])

    if dry_run:
        return SyncResult(
            task_id=task["id"],
            source_table=task["source_table"],
            target_table=task["target_table"],
            rows_affected=len(out),
            ok=True,
            message="dry-run",
        )

    rows = write_dataframe(
        database=task["target_database"],
        table=task["target_table"],
        df=out,
        sync_mode=task["sync_mode"],
        trade_date=trade_date,
    )
    return SyncResult(
        task_id=task["id"],
        source_table=task["source_table"],
        target_table=task["target_table"],
        rows_affected=rows,
        ok=True,
    )


@register("akshare", "_default")
def sync_akshare_default(task: TaskDict, trade_date: date | None, dry_run: bool) -> SyncResult:
    """
    未单独注册时的 AkShare 通用拉取：列名与目标表一致时直接写入。
    复杂映射请在上方用 @register 增加专用处理器。
    """
    from sync_writer import write_dataframe

    df = fetch_akshare(task["source_table"])
    if dry_run:
        return SyncResult(
            task_id=task["id"],
            source_table=task["source_table"],
            target_table=task["target_table"],
            rows_affected=len(df),
            ok=True,
            message="dry-run",
        )
    rows = write_dataframe(
        database=task["target_database"],
        table=task["target_table"],
        df=df,
        sync_mode=task["sync_mode"],
        trade_date=trade_date,
    )
    return SyncResult(
        task_id=task["id"],
        source_table=task["source_table"],
        target_table=task["target_table"],
        rows_affected=rows,
        ok=True,
    )


def resolve_handler(task: TaskDict) -> TaskHandler:
    key = task_key(task["proxy_source"], task["source_table"])
    handler = _HANDLERS.get(key)
    if handler is not None:
        return handler
    if task["proxy_source"] == "akshare":
        return _HANDLERS[task_key("akshare", "_default")]
    raise KeyError(
        f"未注册同步处理器: {key}（请在 task_registry.py 中 @register 或扩展 proxy_source）"
    )


def run_task(task: TaskDict, trade_date: date | None, dry_run: bool) -> SyncResult:
    sync_mode = (task.get("sync_mode") or "snapshot").lower()
    if sync_mode == "derivative":
        return SyncResult(
            task_id=task["id"],
            source_table=task["source_table"],
            target_table=task["target_table"],
            rows_affected=0,
            ok=False,
            message="sync_mode=derivative 需独立 ETL 脚本，不在本同步框架内执行",
        )

    handler = resolve_handler(task)
    logger.info(
        "执行任务 id=%s %s -> %s.%s mode=%s",
        task["id"],
        task_key(task["proxy_source"], task["source_table"]),
        task["target_database"],
        task["target_table"],
        sync_mode,
    )
    return handler(task, trade_date, dry_run)
