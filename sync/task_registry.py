#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
同步任务执行注册表：script_key → 可调用对象。
与 db_sync_task.script_key 一一对应，新增任务时需同时改 SQL 与本文件。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Callable

TaskFn = Callable[..., int | None]


def _cfg():
    from utils import mysql_config as cfg

    return cfg


def _mysql_kw(database: str | None = None) -> dict[str, Any]:
    c = _cfg()
    return {
        "host": c.MYSQL_HOST,
        "port": c.MYSQL_PORT,
        "user": c.MYSQL_USER,
        "password": c.MYSQL_PASSWORD,
        "database": database or c.MYSQL_DATABASE,
    }


def _resolve_target(
    *,
    target_database: str | None,
    target_table: str | None,
    default_database: str | None = None,
    default_table: str | None = None,
) -> tuple[str, str]:
    c = _cfg()
    database = (target_database or default_database or c.MYSQL_DATABASE).strip()
    table = (target_table or default_table or "").strip()
    if not table:
        raise ValueError("db_sync_task.target_table 未配置")
    return database, table


def _norm_trade_date(trade_date: str | None) -> str | None:
    if not trade_date:
        return None
    s = trade_date.strip()
    if len(s) == 8 and s.isdigit():
        return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
    return s


def run_trading_day(
    trade_date: str | None = None,
    script_args: dict | None = None,
    *,
    target_database: str | None = None,
    target_table: str | None = None,
    **_,
) -> int:
    from trading_day.trading_day_etl import TradingDayETL

    args = script_args or {}
    database, table = _resolve_target(
        target_database=target_database,
        target_table=target_table,
        default_table="trading_day_di",
    )
    start_year = int(args.get("start_year", 2020))
    end_year = int(args.get("end_year", 2026))
    etl = TradingDayETL(table_name=table, database=database)
    return etl.run(
        datetime(start_year, 1, 1).date(),
        datetime(end_year, 12, 31).date(),
    )


def run_stock_fund_flow(
    trade_date: str | None = None,
    script_args: dict | None = None,
    *,
    target_database: str | None = None,
    target_table: str | None = None,
    source_channel: str | None = None,
    **_,
) -> int:
    from stock_data.stock_fund_flow_etl import run

    args = script_args or {}
    c = _cfg()
    database, table = _resolve_target(
        target_database=target_database,
        target_table=target_table,
        default_table=c.STOCK_FUND_FLOW_TABLE,
    )
    channel = (source_channel or "akshare").lower()
    if channel != "akshare":
        raise ValueError(f"stock_fund_flow 仅支持 akshare 数据源，当前: {source_channel}")
    periods = args.get("periods", ["即时"])
    return run(
        **_mysql_kw(database=database),
        table_name=table,
        periods=periods,
        trade_date=_norm_trade_date(trade_date),
    )


TASK_REGISTRY: dict[str, TaskFn] = {
    "trading_day": run_trading_day,
    "stock_fund_flow": run_stock_fund_flow,
}


def get_runner(script_key: str) -> TaskFn:
    fn = TASK_REGISTRY.get(script_key)
    if fn is None:
        raise KeyError(
            f"未注册的 script_key={script_key!r}，请在 sync/task_registry.py 的 TASK_REGISTRY 中补充"
        )
    return fn
