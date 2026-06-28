#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
配置驱动同步：db_sync_task.fetch_config / transform_config 控制拉数与字段映射。
仍可通过 @register 覆盖个别任务。
"""
from __future__ import annotations

import logging
import os
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


def _fetch_retry_count() -> int:
    try:
        return max(1, int(os.getenv("TUSHARE_FETCH_RETRIES", "3")))
    except ValueError:
        return 3


def _fetch_retry_sleep() -> float:
    try:
        return max(0.0, float(os.getenv("TUSHARE_FETCH_RETRY_SLEEP", "5")))
    except ValueError:
        return 5.0


def _is_retryable_fetch_error(exc: BaseException) -> bool:
    import requests

    retryable = (
        requests.exceptions.Timeout,
        requests.exceptions.ConnectionError,
        TimeoutError,
    )
    if isinstance(exc, retryable):
        return True
    cause = getattr(exc, "__cause__", None)
    return isinstance(cause, retryable) if cause else False


def fetch_tushare(
    source_table: str, token_type: str = "tushare", **kwargs: Any
) -> pd.DataFrame:
    from tushare_client import get_tushare_pro

    pro = get_tushare_pro(token_type)
    fn = getattr(pro, source_table, None)
    if fn is None or not callable(fn):
        raise ValueError(f"tushare 未找到接口: {source_table}")

    retries = _fetch_retry_count()
    retry_sleep = _fetch_retry_sleep()
    last_exc: BaseException | None = None
    for attempt in range(1, retries + 1):
        try:
            df = fn(**kwargs)
            if df is None:
                return pd.DataFrame()
            if not isinstance(df, pd.DataFrame):
                raise TypeError(f"{source_table} 返回值不是 DataFrame")
            return df
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            if attempt >= retries or not _is_retryable_fetch_error(exc):
                raise
            wait = retry_sleep * attempt
            logger.warning(
                "%s 第 %s/%s 次请求失败(%s)，%.1fs 后重试 params=%s",
                source_table,
                attempt,
                retries,
                exc,
                wait,
                kwargs,
            )
            time.sleep(wait)
    if last_exc:
        raise last_exc
    return pd.DataFrame()


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


def fetch_tushare_paged(
    source_table: str,
    *,
    token_type: str = "tushare",
    page_size: int = 2000,
    max_pages: int | None = None,
    sleep_s: float = 0.3,
    **base_kwargs: Any,
) -> pd.DataFrame:
    """
    Tushare 接口 limit/offset 分页拉全量（如 index_member_all 单次最大 2000 行）。
    max_pages 有值时固定最多拉 N 页（未满 page_size 也继续，以防 API 提前截断）。
    """
    frames: list[pd.DataFrame] = []
    offset = 0
    page = 0
    while True:
        page += 1
        if max_pages is not None and page > max_pages:
            break
        kwargs = dict(base_kwargs)
        kwargs["limit"] = page_size
        kwargs["offset"] = offset
        part = fetch_tushare(source_table, token_type=token_type, **kwargs)
        n = len(part)
        logger.info(
            "%s 分页 %s/%s: offset=%s rows=%s",
            source_table,
            page,
            max_pages or "?",
            offset,
            n,
        )
        if part.empty:
            break
        frames.append(part)
        if max_pages is None and n < page_size:
            break
        if max_pages is not None and page >= max_pages:
            break
        offset += page_size
        if sleep_s > 0:
            time.sleep(sleep_s)
    if not frames:
        return pd.DataFrame()
    if len(frames) == 1:
        return frames[0]
    return pd.concat(frames, ignore_index=True)


def fetch_task_dataframe(task: TaskDict, trade_date: date | None) -> pd.DataFrame:
    proxy = task["proxy_source"]
    api_name = task["source_table"]
    fetch_cfg = get_fetch_config(task)
    token_type = fetch_cfg.get("token_type") or proxy

    param_list = build_api_call_params_list(task, trade_date)
    if not param_list:
        param_list = [{}]

    sleep_s = float(fetch_cfg.get("sleep_seconds") or 0)
    frames: list[pd.DataFrame] = []
    for i, params in enumerate(param_list):
        logger.info("拉取 %s:%s 第%s次 params=%s", proxy, api_name, i + 1, params)
        part = fetch_by_proxy(proxy, api_name, token_type=token_type, **params)
        logger.info("返回 %s 行", len(part))
        if not part.empty:
            frames.append(part)
        if sleep_s > 0 and i + 1 < len(param_list):
            time.sleep(sleep_s)

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


def _snapshot_quarter_periods(trade_date: date, *, count: int = 2) -> list[str]:
    """不晚于 trade_date 的最近 count 个季报报告期末日（YYYYMMDD）。"""
    all_periods = _quarter_period_ends("20180101", trade_date)
    if not all_periods:
        return []
    n = max(1, count)
    return all_periods[-n:]


def _delete_by_date_values(
    database: str, table: str, column: str, values: list[date]
) -> None:
    if not values:
        return
    from mysql_config import get_target_engine

    engine = get_target_engine(database)
    placeholders = ", ".join(f":v{i}" for i in range(len(values)))
    params = {f"v{i}": v for i, v in enumerate(values)}
    with engine.begin() as conn:
        conn.execute(
            text(f"DELETE FROM `{table}` WHERE `{column}` IN ({placeholders})"),
            params,
        )


@register("tushare", "stock_company")
def sync_stock_company(task: TaskDict, trade_date: date | None, dry_run: bool) -> SyncResult:
    """stock_company 按交易所全量拉取；full 模式 TRUNCATE 后写入。"""
    from sync_writer import write_dataframe

    df = fetch_task_dataframe(task, trade_date)
    out = apply_transform(df, task)
    sync_mode = (task.get("sync_mode") or "full").lower()

    logger.info(
        "stock_company id=%s 原始=%s 映射后=%s mode=%s",
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

    if out.empty:
        return SyncResult(
            task_id=task["id"],
            source_table=task["source_table"],
            target_table=task["target_table"],
            rows_affected=0,
            ok=False,
            message="stock_company 返回 0 行，请检查 Tushare 积分与代理 API",
        )

    rows = write_dataframe(
        database=task["target_database"],
        table=task["target_table"],
        df=out,
        sync_mode=sync_mode,
        trade_date=None,
    )
    return SyncResult(
        task_id=task["id"],
        source_table=task["source_table"],
        target_table=task["target_table"],
        rows_affected=rows,
        ok=True,
    )


@register("tushare", "index_member_all")
def sync_index_member_all(
    task: TaskDict, trade_date: date | None, dry_run: bool
) -> SyncResult:
    """index_member_all 单次最大 2000 行，固定最多 4 页 offset 分页拉全量后写入。"""
    from sync_writer import write_dataframe

    fetch_cfg = get_fetch_config(task)
    token_type = fetch_cfg.get("token_type") or "tushare"
    page_size = int(fetch_cfg.get("page_size") or 2000)
    max_pages = int(fetch_cfg.get("max_pages") or 4)
    sleep_s = float(fetch_cfg.get("sleep_seconds") or 0.3)
    base_params = dict(fetch_cfg.get("params") or {})
    sync_mode = (task.get("sync_mode") or "full").lower()

    df = fetch_tushare_paged(
        "index_member_all",
        token_type=token_type,
        page_size=page_size,
        max_pages=max_pages,
        sleep_s=sleep_s,
        **base_params,
    )
    out = apply_transform(df, task)
    stock_cnt = out["ts_code"].nunique() if not out.empty and "ts_code" in out.columns else 0

    logger.info(
        "index_member_all id=%s 原始=%s 映射后=%s stocks=%s mode=%s",
        task["id"],
        len(df),
        len(out),
        stock_cnt,
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

    if out.empty:
        return SyncResult(
            task_id=task["id"],
            source_table=task["source_table"],
            target_table=task["target_table"],
            rows_affected=0,
            ok=False,
            message="index_member_all 返回 0 行，请检查 Tushare 积分(约2000)与代理 API",
        )

    rows = write_dataframe(
        database=task["target_database"],
        table=task["target_table"],
        df=out,
        sync_mode=sync_mode,
        trade_date=None,
    )
    return SyncResult(
        task_id=task["id"],
        source_table=task["source_table"],
        target_table=task["target_table"],
        rows_affected=rows,
        ok=True,
    )


@register("tushare", "fina_mainbz_vip")
def sync_fina_mainbz_vip(
    task: TaskDict, trade_date: date | None, dry_run: bool
) -> SyncResult:
    """fina_mainbz_vip 全市场按报告期拉取；snapshot 默认近 2 季 type=P，full 季末回溯。"""
    from sync_writer import write_dataframe

    fetch_cfg = get_fetch_config(task)
    token_type = fetch_cfg.get("token_type") or "tushare"
    sync_mode = (task.get("sync_mode") or "snapshot").lower()
    td = trade_date or date.today()
    sleep_s = float(fetch_cfg.get("sleep_seconds") or 0.5)
    bz_type = str((fetch_cfg.get("params") or {}).get("type") or "P")
    fields = (fetch_cfg.get("params") or {}).get("fields")
    frames: list[pd.DataFrame] = []

    if sync_mode == "full":
        from_yyyymmdd = str(fetch_cfg.get("full_start") or "20180101")
        periods = _quarter_period_ends(from_yyyymmdd, td)
        for i, period in enumerate(periods):
            logger.info("fina_mainbz_vip 进度 %s/%s period=%s type=%s", i + 1, len(periods), period, bz_type)
            try:
                kwargs: dict[str, Any] = {"period": period, "type": bz_type}
                if fields:
                    kwargs["fields"] = fields
                part = fetch_tushare("fina_mainbz_vip", token_type=token_type, **kwargs)
            except Exception as exc:
                logger.warning("fina_mainbz_vip period=%s 失败: %s", period, exc)
                continue
            if not part.empty:
                frames.append(part)
            if sleep_s > 0:
                time.sleep(sleep_s)
    else:
        snap_n = int(fetch_cfg.get("snapshot_periods") or 2)
        periods = _snapshot_quarter_periods(td, count=snap_n)
        for i, period in enumerate(periods):
            logger.info(
                "fina_mainbz_vip snapshot %s/%s period=%s type=%s",
                i + 1,
                len(periods),
                period,
                bz_type,
            )
            try:
                kwargs = {"period": period, "type": bz_type}
                if fields:
                    kwargs["fields"] = fields
                part = fetch_tushare("fina_mainbz_vip", token_type=token_type, **kwargs)
            except Exception as exc:
                logger.warning("fina_mainbz_vip period=%s 失败: %s", period, exc)
                continue
            if not part.empty:
                frames.append(part)
            if sleep_s > 0 and i + 1 < len(periods):
                time.sleep(sleep_s)

    df = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    out = apply_transform(df, task)

    logger.info(
        "fina_mainbz_vip id=%s 原始=%s 映射后=%s mode=%s periods=%s",
        task["id"],
        len(df),
        len(out),
        sync_mode,
        len(frames),
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

    if sync_mode == "full" and not out.empty:
        from mysql_config import get_target_engine

        engine = get_target_engine(task["target_database"])
        with engine.begin() as conn:
            conn.execute(text(f"TRUNCATE TABLE `{task['target_table']}`"))
    elif sync_mode == "snapshot" and not out.empty and "end_date" in out.columns:
        end_dates: list[date] = []
        for raw in out["end_date"].dropna().unique():
            if isinstance(raw, date):
                end_dates.append(raw)
            else:
                end_dates.append(pd.Timestamp(raw).date())
        _delete_by_date_values(
            task["target_database"],
            task["target_table"],
            "end_date",
            sorted(set(end_dates)),
        )

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


def _delete_ts_codes(database: str, table: str, codes: list[str], *, bz_type: str | None = None) -> None:
    if not codes:
        return
    from mysql_config import get_target_engine

    engine = get_target_engine(database)
    chunk = 400
    for i in range(0, len(codes), chunk):
        part = codes[i : i + chunk]
        placeholders = ", ".join(f":c{j}" for j in range(len(part)))
        params: dict[str, Any] = {f"c{j}": c for j, c in enumerate(part)}
        sql = f"DELETE FROM `{table}` WHERE ts_code IN ({placeholders})"
        if bz_type:
            sql += " AND bz_type = :bz_type"
            params["bz_type"] = bz_type
        with engine.begin() as conn:
            conn.execute(text(sql), params)


def _load_mainbz_stock_codes(task: TaskDict, trade_date: date | None) -> list[str]:
    fetch_cfg = get_fetch_config(task)
    stock_db = str(fetch_cfg.get("stock_database") or task["target_database"])
    stock_table = str(fetch_cfg.get("stock_table") or "ods_stock_company_di")
    td = trade_date or date.today()
    missing_only = bool(fetch_cfg.get("missing_only", True))
    snap_n = int(fetch_cfg.get("snapshot_periods") or 2)
    periods = _snapshot_quarter_periods(td, count=snap_n)
    max_stocks = fetch_cfg.get("max_stocks")

    from mysql_config import get_target_engine

    engine = get_target_engine(stock_db)
    if missing_only and periods:
        from datetime import datetime

        placeholders = ", ".join(f":p{i}" for i in range(len(periods)))
        params: dict[str, Any] = {
            f"p{i}": datetime.strptime(p, "%Y%m%d").date() for i, p in enumerate(periods)
        }
        sql = f"""
            SELECT c.ts_code
            FROM `{stock_table}` c
            WHERE NOT EXISTS (
                SELECT 1 FROM `{task['target_table']}` m
                WHERE m.ts_code = c.ts_code
                  AND m.end_date IN ({placeholders})
            )
            ORDER BY c.ts_code
        """
        with engine.connect() as conn:
            codes = [row[0] for row in conn.execute(text(sql), params).fetchall()]
    else:
        with engine.connect() as conn:
            codes = [row[0] for row in conn.execute(text(f"SELECT ts_code FROM `{stock_table}` ORDER BY ts_code")).fetchall()]

    if max_stocks is not None:
        codes = codes[: int(max_stocks)]
    return codes


@register("tushare", "fina_mainbz")
def sync_fina_mainbz(task: TaskDict, trade_date: date | None, dry_run: bool) -> SyncResult:
    """
    fina_mainbz 按个股循环拉主营业务构成（补 fina_mainbz_vip 单次约 10000 行上限导致的缺失）。
    默认 missing_only：仅补近 N 个报告期在 ods_fina_mainbz_di 中无记录的股票。
    """
    from sync_writer import write_dataframe

    fetch_cfg = get_fetch_config(task)
    token_type = fetch_cfg.get("token_type") or "tushare"
    sleep_s = float(fetch_cfg.get("sleep_seconds") or 0.35)
    log_every = int(fetch_cfg.get("batch_log_every") or 200)
    bz_type = str((fetch_cfg.get("params") or {}).get("type") or "P")
    fields = (fetch_cfg.get("params") or {}).get("fields")
    sync_mode = (task.get("sync_mode") or "incremental").lower()

    codes = _load_mainbz_stock_codes(task, trade_date)
    if not codes:
        return SyncResult(
            task_id=task["id"],
            source_table=task["source_table"],
            target_table=task["target_table"],
            rows_affected=0,
            ok=True,
            message="无待补全股票（missing_only 已覆盖近季报告期）",
        )

    logger.info("fina_mainbz 待拉取 %s 只股票 type=%s", len(codes), bz_type)
    frames: list[pd.DataFrame] = []
    ok_cnt = 0
    for i, ts_code in enumerate(codes, start=1):
        try:
            kwargs: dict[str, Any] = {"ts_code": ts_code, "type": bz_type}
            if fields:
                kwargs["fields"] = fields
            part = fetch_tushare("fina_mainbz", token_type=token_type, **kwargs)
        except Exception as exc:
            logger.warning("fina_mainbz ts_code=%s 失败: %s", ts_code, exc)
            continue
        if not part.empty:
            frames.append(part)
            ok_cnt += 1
        if log_every > 0 and i % log_every == 0:
            logger.info("fina_mainbz 进度 %s/%s ok=%s", i, len(codes), ok_cnt)
        if sleep_s > 0 and i < len(codes):
            time.sleep(sleep_s)

    df = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    out = apply_transform(df, task)
    refreshed = sorted(out["ts_code"].dropna().unique().tolist()) if not out.empty and "ts_code" in out.columns else []

    logger.info(
        "fina_mainbz id=%s 股票=%s 成功=%s 原始行=%s 映射后=%s",
        task["id"],
        len(codes),
        ok_cnt,
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

    if out.empty:
        return SyncResult(
            task_id=task["id"],
            source_table=task["source_table"],
            target_table=task["target_table"],
            rows_affected=0,
            ok=False,
            message=f"fina_mainbz 未拉到数据（待补 {len(codes)} 只）",
        )

    if sync_mode == "full":
        from mysql_config import get_target_engine

        engine = get_target_engine(task["target_database"])
        with engine.begin() as conn:
            conn.execute(text(f"TRUNCATE TABLE `{task['target_table']}`"))
    else:
        _delete_ts_codes(
            task["target_database"],
            task["target_table"],
            refreshed,
            bz_type=bz_type if "bz_type" in out.columns else None,
        )

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
        message=f"补全 {len(refreshed)} 只股票",
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


@register("tushare", "dc_index")
def sync_dc_index(task: TaskDict, trade_date: date | None, dry_run: bool) -> SyncResult:
    """dc_index 按 idx_type 分三次拉取；全空时标失败并提示排查。"""
    from sync_writer import write_dataframe

    td = trade_date or date.today()
    df = fetch_task_dataframe(task, trade_date)
    out = apply_transform(df, task)
    write_td = write_trade_date_for_sync_mode(task, trade_date)

    logger.info(
        "dc_index id=%s 原始=%s 映射后=%s",
        task["id"],
        len(df),
        len(out),
    )

    if out.empty:
        td_str = td.strftime("%Y%m%d")
        msg = (
            f"dc_index 在 {td_str} 返回 0 行。"
            "请核对：① Tushare 积分≥6000；② 代理 API 是否正常；"
            f"③ 对比同日 moneyflow_ind_dc："
            f"run_data_sync {td_str} --source-table moneyflow_ind_dc；"
            "④ 换邻近交易日试跑。"
        )
        logger.error(msg)
        return SyncResult(
            task_id=task["id"],
            source_table=task["source_table"],
            target_table=task["target_table"],
            rows_affected=0,
            ok=False,
            message=msg,
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
        trade_date=write_td,
        snapshot_delete_column=transform_cfg.get("snapshot_delete_column") or "trade_date",
    )
    return SyncResult(
        task_id=task["id"],
        source_table=task["source_table"],
        target_table=task["target_table"],
        rows_affected=rows,
        ok=True,
    )


@register("tushare", "dc_member")
def sync_dc_member(task: TaskDict, trade_date: date | None, dry_run: bool) -> SyncResult:
    """
    dc_member 单次最多 5000 行，按板块 ts_code 循环拉取全量成分。
    板块列表来自当日 ods_industry_fund_flow_di（东财 moneyflow_ind_dc）。
    """
    from mysql_config import get_target_engine
    from sync_writer import write_dataframe

    fetch_cfg = get_fetch_config(task)
    token_type = fetch_cfg.get("token_type") or "tushare"
    sleep_s = float(fetch_cfg.get("sleep_seconds") or 0.2)
    td = trade_date or date.today()
    td_str = td.strftime("%Y%m%d")
    board_table = str(fetch_cfg.get("board_table") or "ods_industry_fund_flow_di")
    board_database = str(fetch_cfg.get("board_database") or task["target_database"])
    content_types = fetch_cfg.get("content_types") or ["行业", "概念", "地域"]

    engine = get_target_engine(board_database)
    placeholders = ", ".join(f":ct{i}" for i in range(len(content_types)))
    params: dict[str, Any] = {"td": td}
    for i, ct in enumerate(content_types):
        params[f"ct{i}"] = ct

    with engine.connect() as conn:
        codes = [
            row[0]
            for row in conn.execute(
                text(
                    f"""
                    SELECT DISTINCT industry_code
                    FROM `{board_table}`
                    WHERE trade_date = :td
                      AND content_type IN ({placeholders})
                    ORDER BY industry_code
                    """
                ),
                params,
            ).fetchall()
        ]
        if not codes:
            fallback_td = conn.execute(
                text(
                    f"""
                    SELECT MAX(trade_date) FROM `{board_table}`
                    WHERE trade_date <= :td
                      AND content_type IN ({placeholders})
                    """
                ),
                params,
            ).scalar()
            if fallback_td:
                params["td"] = fallback_td
                logger.warning(
                    "dc_member %s 无板块列表，回退到 %s", td_str, fallback_td
                )
                codes = [
                    row[0]
                    for row in conn.execute(
                        text(
                            f"""
                            SELECT DISTINCT industry_code
                            FROM `{board_table}`
                            WHERE trade_date = :td
                              AND content_type IN ({placeholders})
                            ORDER BY industry_code
                            """
                        ),
                        params,
                    ).fetchall()
                ]

    if not codes:
        return SyncResult(
            task_id=task["id"],
            source_table=task["source_table"],
            target_table=task["target_table"],
            rows_affected=0,
            ok=False,
            message=(
                f"{board_database}.{board_table} 在 {td_str} 无板块代码，"
                "请先同步 moneyflow_ind_dc"
            ),
        )

    frames: list[pd.DataFrame] = []
    for i, ts_code in enumerate(codes):
        logger.info("dc_member 进度 %s/%s ts_code=%s", i + 1, len(codes), ts_code)
        try:
            part = fetch_tushare(
                "dc_member",
                token_type=token_type,
                trade_date=td_str,
                ts_code=ts_code,
            )
        except Exception as exc:
            logger.warning("dc_member ts_code=%s 失败: %s", ts_code, exc)
            continue
        if not part.empty:
            frames.append(part)
        if sleep_s > 0 and i + 1 < len(codes):
            time.sleep(sleep_s)

    df = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    out = apply_transform(df, task)

    logger.info(
        "dc_member id=%s 板块=%s 原始=%s 映射后=%s",
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

    if out.empty:
        return SyncResult(
            task_id=task["id"],
            source_table=task["source_table"],
            target_table=task["target_table"],
            rows_affected=0,
            ok=False,
            message=f"dc_member {td_str} 全部板块返回空，请检查 Tushare 积分与代理",
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
