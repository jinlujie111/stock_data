#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
配置驱动同步：db_sync_task.fetch_config / transform_config 控制拉数与字段映射。
仍可通过 @register 覆盖个别任务。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from typing import Any, Callable

import pandas as pd

from task_config import (
    apply_transform,
    build_api_call_params_list,
    get_fetch_config,
    write_trade_date_for_sync_mode,
)

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


def fetch_tushare(
    source_table: str, token_type: str = "tushare", **kwargs: Any
) -> pd.DataFrame:
    from tushare_client import get_tushare_pro

    pro = get_tushare_pro(token_type)
    fn = getattr(pro, source_table, None)
    if fn is None or not callable(fn):
        raise ValueError(f"tushare 未找到接口: {source_table}")
    df = fn(**kwargs)
    if df is None:
        return pd.DataFrame()
    if not isinstance(df, pd.DataFrame):
        raise TypeError(f"{source_table} 返回值不是 DataFrame")
    return df


def fetch_akshare(source_table: str, **kwargs: Any) -> pd.DataFrame:
    import akshare as ak

    fn = getattr(ak, source_table, None)
    if fn is None or not callable(fn):
        raise ValueError(f"akshare 未找到接口: {source_table}")
    df = fn(**kwargs)
    if not isinstance(df, pd.DataFrame):
        raise TypeError(f"{source_table} 返回值不是 DataFrame")
    return df


def fetch_by_proxy(
    proxy_source: str,
    source_table: str,
    *,
    token_type: str | None = None,
    **kwargs: Any,
) -> pd.DataFrame:
    proxy = proxy_source.lower()
    if proxy == "tushare":
        return fetch_tushare(source_table, token_type=token_type or "tushare", **kwargs)
    if proxy == "akshare":
        return fetch_akshare(source_table, **kwargs)
    raise ValueError(f"不支持的 proxy_source: {proxy_source}")


def fetch_task_dataframe(task: TaskDict, trade_date: date | None) -> pd.DataFrame:
    proxy = task["proxy_source"]
    api_name = task["source_table"]
    fetch_cfg = get_fetch_config(task)
    token_type = fetch_cfg.get("token_type") or proxy

    param_list = build_api_call_params_list(task, trade_date)
    if not param_list:
        param_list = [{}]

    frames: list[pd.DataFrame] = []
    for i, params in enumerate(param_list):
        logger.info("拉取 %s:%s 第%s次 params=%s", proxy, api_name, i + 1, params)
        part = fetch_by_proxy(proxy, api_name, token_type=token_type, **params)
        logger.info("返回 %s 行", len(part))
        if not part.empty:
            frames.append(part)

    if not frames:
        return pd.DataFrame()
    if len(frames) == 1:
        return frames[0]
    return pd.concat(frames, ignore_index=True)


def sync_generic(task: TaskDict, trade_date: date | None, dry_run: bool) -> SyncResult:
    """通用同步：fetch_config → 拉数 → transform_config → 写库。"""
    from sync_writer import write_dataframe

    sync_mode = (task.get("sync_mode") or "snapshot").lower()
    df = fetch_task_dataframe(task, trade_date)
    out = apply_transform(df, task)
    write_td = write_trade_date_for_sync_mode(task, trade_date)

    logger.info(
        "任务 id=%s 原始=%s 映射后=%s mode=%s",
        task["id"],
        len(df),
        len(out),
        sync_mode,
    )

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
        sync_mode=sync_mode,
        trade_date=write_td,
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
    if key in _HANDLERS:
        return _HANDLERS[key]
    return sync_generic


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
