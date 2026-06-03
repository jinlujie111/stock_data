#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
配置驱动同步：db_sync_task.fetch_config / transform_config 控制拉数与字段映射。
仍可通过 @register 覆盖个别任务。
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import date
from typing import Any, Callable

import pandas as pd
from sqlalchemy import text

from task_config import (
    apply_transform,
    build_api_call_params_list,
    get_fetch_config,
    get_transform_config,
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


def _quarter_period_ends(from_yyyymmdd: str, through: date) -> list[str]:
    """生成不晚于 through 的季报报告期末日列表（YYYYMMDD）。"""
    from datetime import datetime

    start = datetime.strptime(from_yyyymmdd, "%Y%m%d").date()
    year = start.year
    periods: list[str] = []
    while year <= through.year:
        for month_day in ((3, 31), (6, 30), (9, 30), (12, 31)):
            d = date(year, month_day[0], month_day[1])
            if d < start:
                continue
            if d > through:
                return periods
            periods.append(d.strftime("%Y%m%d"))
        year += 1
    return periods


def _delete_by_date_column(
    database: str, table: str, column: str, value: date
) -> None:
    from mysql_config import get_target_engine

    engine = get_target_engine(database)
    with engine.begin() as conn:
        conn.execute(
            text(f"DELETE FROM `{table}` WHERE `{column}` = :v"),
            {"v": value},
        )


@register("tushare", "fina_indicator_vip")
def sync_fina_indicator_vip(
    task: TaskDict, trade_date: date | None, dry_run: bool
) -> SyncResult:
    """fina_indicator_vip 单次拉全市场；snapshot 按 ann_date，full 按 period 季末循环。"""
    from sync_writer import write_dataframe

    fetch_cfg = get_fetch_config(task)
    token_type = fetch_cfg.get("token_type") or "tushare"
    sync_mode = (task.get("sync_mode") or "snapshot").lower()
    td = trade_date or date.today()
    sleep_s = float(fetch_cfg.get("sleep_seconds") or 0.5)
    frames: list[pd.DataFrame] = []

    if sync_mode == "full":
        from_yyyymmdd = str(fetch_cfg.get("full_start") or "20180101")
        periods = _quarter_period_ends(from_yyyymmdd, td)
        for i, period in enumerate(periods):
            logger.info("fina_indicator_vip 进度 %s/%s period=%s", i + 1, len(periods), period)
            try:
                part = fetch_tushare(
                    "fina_indicator_vip", token_type=token_type, period=period
                )
            except Exception as exc:
                logger.warning("fina_indicator_vip period=%s 失败: %s", period, exc)
                continue
            if not part.empty:
                frames.append(part)
            if sleep_s > 0:
                time.sleep(sleep_s)
    else:
        param_list = build_api_call_params_list(task, trade_date)
        for params in param_list:
            part = fetch_tushare("fina_indicator_vip", token_type=token_type, **params)
            if not part.empty:
                frames.append(part)

    df = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    out = apply_transform(df, task)
    write_td = write_trade_date_for_sync_mode(task, trade_date)

    logger.info(
        "fina_indicator_vip id=%s 原始=%s 映射后=%s mode=%s",
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

    if not out.empty and sync_mode == "snapshot" and write_td is not None:
        _delete_by_date_column(
            task["target_database"],
            task["target_table"],
            "ann_date",
            write_td,
        )
    elif sync_mode == "full" and not out.empty:
        from mysql_config import get_target_engine

        engine = get_target_engine(task["target_database"])
        with engine.begin() as conn:
            conn.execute(text(f"TRUNCATE TABLE `{task['target_table']}`"))

    rows = write_dataframe(
        database=task["target_database"],
        table=task["target_table"],
        df=out,
        sync_mode="append",
        trade_date=None,
    )
    return SyncResult(
        task_id=task["id"],
        source_table=task["source_table"],
        target_table=task["target_table"],
        rows_affected=rows,
        ok=True,
    )


@register("tushare", "ths_member")
def sync_ths_member(
    task: TaskDict, trade_date: date | None, dry_run: bool
) -> SyncResult:
    """ths_member 需按板块 ts_code 循环；指数列表来自 ods_ths_index_di。"""
    from mysql_config import get_target_engine
    from sync_writer import write_dataframe

    fetch_cfg = get_fetch_config(task)
    token_type = fetch_cfg.get("token_type") or "tushare"
    sleep_s = float(fetch_cfg.get("sleep_seconds") or 0.35)
    index_table = str(fetch_cfg.get("index_table") or "ods_ths_index_di")
    index_database = str(fetch_cfg.get("index_database") or task["target_database"])
    index_exchange = fetch_cfg.get("index_exchange")

    engine = get_target_engine(index_database)
    sql = f"SELECT ts_code FROM `{index_table}`"
    params: dict[str, Any] = {}
    if index_exchange:
        sql += " WHERE exchange = :ex"
        params["ex"] = index_exchange
    sql += " ORDER BY ts_code"

    with engine.connect() as conn:
        codes = [row[0] for row in conn.execute(text(sql), params).fetchall()]

    if not codes:
        return SyncResult(
            task_id=task["id"],
            source_table=task["source_table"],
            target_table=task["target_table"],
            rows_affected=0,
            ok=False,
            message=f"{index_database}.{index_table} 无 ts_code，请先同步 ths_index",
        )

    frames: list[pd.DataFrame] = []
    for i, ts_code in enumerate(codes):
        logger.info("ths_member 进度 %s/%s ts_code=%s", i + 1, len(codes), ts_code)
        try:
            part = fetch_tushare("ths_member", token_type=token_type, ts_code=ts_code)
        except Exception as exc:
            logger.warning("ths_member ts_code=%s 失败: %s", ts_code, exc)
            continue
        if not part.empty:
            frames.append(part)
        if sleep_s > 0 and i + 1 < len(codes):
            time.sleep(sleep_s)

    df = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    out = apply_transform(df, task)

    logger.info(
        "ths_member id=%s 板块=%s 原始=%s 映射后=%s",
        task["id"],
        len(codes),
        len(df),
        len(out),
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

    if not out.empty:
        target_engine = get_target_engine(task["target_database"])
        with target_engine.begin() as conn:
            conn.execute(text(f"TRUNCATE TABLE `{task['target_table']}`"))

    rows = write_dataframe(
        database=task["target_database"],
        table=task["target_table"],
        df=out,
        sync_mode="append",
        trade_date=None,
    )
    return SyncResult(
        task_id=task["id"],
        source_table=task["source_table"],
        target_table=task["target_table"],
        rows_affected=rows,
        ok=True,
    )


@register("tushare", "ths_hot")
def sync_ths_hot(task: TaskDict, trade_date: date | None, dry_run: bool) -> SyncResult:
    """ths_hot 需按 market 热榜类型循环；接口不返回 market 字段，拉取后注入。"""
    from sync_writer import write_dataframe

    fetch_cfg = get_fetch_config(task)
    token_type = fetch_cfg.get("token_type") or "tushare"
    sleep_s = float(fetch_cfg.get("sleep_seconds") or 0.2)
    td = trade_date or date.today()
    td_str = td.strftime("%Y%m%d")

    base_params = dict(fetch_cfg.get("params") or {})
    base_params.setdefault("trade_date", td_str)
    base_params.setdefault("is_new", "Y")

    markets = fetch_cfg.get("market_list") or [
        "热股",
        "ETF",
        "可转债",
        "行业板块",
        "概念板块",
        "期货",
        "港股",
        "热基",
        "美股",
    ]

    frames: list[pd.DataFrame] = []
    for i, market in enumerate(markets):
        params = dict(base_params)
        params["market"] = market
        logger.info("ths_hot 进度 %s/%s market=%s params=%s", i + 1, len(markets), market, params)
        try:
            part = fetch_tushare("ths_hot", token_type=token_type, **params)
        except Exception as exc:
            logger.warning("ths_hot market=%s 失败: %s", market, exc)
            continue
        if not part.empty:
            part = part.copy()
            part["market"] = market
            frames.append(part)
        if sleep_s > 0 and i + 1 < len(markets):
            time.sleep(sleep_s)

    df = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    out = apply_transform(df, task)

    logger.info(
        "ths_hot id=%s markets=%s 原始=%s 映射后=%s",
        task["id"],
        len(markets),
        len(df),
        len(out),
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

    transform_cfg = get_transform_config(task)
    rows = write_dataframe(
        database=task["target_database"],
        table=task["target_table"],
        df=out,
        sync_mode="snapshot",
        trade_date=td,
        snapshot_delete_column=transform_cfg.get("snapshot_delete_column") or "trade_date",
    )
    return SyncResult(
        task_id=task["id"],
        source_table=task["source_table"],
        target_table=task["target_table"],
        rows_affected=rows,
        ok=True,
    )


@register("tushare", "dc_hot")
def sync_dc_hot(task: TaskDict, trade_date: date | None, dry_run: bool) -> SyncResult:
    """dc_hot 需按 market × hot_type 循环；接口不返回 market/hot_type 字段，拉取后注入。"""
    from sync_writer import write_dataframe

    fetch_cfg = get_fetch_config(task)
    token_type = fetch_cfg.get("token_type") or "tushare"
    sleep_s = float(fetch_cfg.get("sleep_seconds") or 0.2)
    td = trade_date or date.today()
    td_str = td.strftime("%Y%m%d")

    base_params = dict(fetch_cfg.get("params") or {})
    base_params.setdefault("trade_date", td_str)
    base_params.setdefault("is_new", "Y")

    markets = fetch_cfg.get("market_list") or [
        "A股市场",
        "ETF基金",
        "港股市场",
        "美股市场",
    ]
    hot_types = fetch_cfg.get("hot_type_list") or ["人气榜", "飙升榜"]

    frames: list[pd.DataFrame] = []
    total_calls = len(markets) * len(hot_types)
    call_idx = 0
    for market in markets:
        for hot_type in hot_types:
            call_idx += 1
            params = dict(base_params)
            params["market"] = market
            params["hot_type"] = hot_type
            logger.info(
                "dc_hot 进度 %s/%s market=%s hot_type=%s",
                call_idx,
                total_calls,
                market,
                hot_type,
            )
            try:
                part = fetch_tushare("dc_hot", token_type=token_type, **params)
            except Exception as exc:
                logger.warning(
                    "dc_hot market=%s hot_type=%s 失败: %s", market, hot_type, exc
                )
                continue
            if not part.empty:
                part = part.copy()
                part["market"] = market
                part["hot_type"] = hot_type
                frames.append(part)
            if sleep_s > 0 and call_idx < total_calls:
                time.sleep(sleep_s)

    df = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    out = apply_transform(df, task)

    logger.info(
        "dc_hot id=%s calls=%s 原始=%s 映射后=%s",
        task["id"],
        total_calls,
        len(df),
        len(out),
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

    transform_cfg = get_transform_config(task)
    rows = write_dataframe(
        database=task["target_database"],
        table=task["target_table"],
        df=out,
        sync_mode="snapshot",
        trade_date=td,
        snapshot_delete_column=transform_cfg.get("snapshot_delete_column") or "trade_date",
    )
    return SyncResult(
        task_id=task["id"],
        source_table=task["source_table"],
        target_table=task["target_table"],
        rows_affected=rows,
        ok=True,
    )


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

    transform_cfg = get_transform_config(task)
    rows = write_dataframe(
        database=task["target_database"],
        table=task["target_table"],
        df=out,
        sync_mode=sync_mode,
        trade_date=write_td,
        snapshot_delete_column=transform_cfg.get("snapshot_delete_column"),
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
