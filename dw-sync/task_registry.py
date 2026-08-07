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
    out = _normalize_mainbz_df(apply_transform(df, task))

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


_MAINBZ_UK_ITEM_LEN = 128


def _normalize_mainbz_df(df: pd.DataFrame) -> pd.DataFrame:
    """与 uk_fina_mainbz(ts_code,end_date,bz_type,bz_item(128)) 对齐，避免前缀冲突导致 Duplicate entry。"""
    if df.empty or "bz_item" not in df.columns:
        return df
    out = df.copy()
    items = out["bz_item"]
    truncated = items.astype("string").str.slice(0, _MAINBZ_UK_ITEM_LEN)
    out["bz_item"] = truncated.where(items.notna(), None)
    keys = [c for c in ("ts_code", "end_date", "bz_type", "bz_item") if c in out.columns]
    if keys:
        before = len(out)
        out = out.drop_duplicates(subset=keys, keep="last")
        if before != len(out):
            logger.info("mainbz 去重 %s -> %s（uk 含 bz_item 前 %s 字）", before, len(out), _MAINBZ_UK_ITEM_LEN)
    return out


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

        period_dates = [datetime.strptime(p, "%Y%m%d").date() for p in periods]
        params: dict[str, Any] = {
            f"p{i}": d for i, d in enumerate(period_dates)
        }
        missing_any = " OR ".join(
            f"NOT EXISTS (SELECT 1 FROM `{task['target_table']}` m"
            f" WHERE m.ts_code = c.ts_code AND m.end_date = :p{i})"
            for i in range(len(period_dates))
        )
        sql = f"""
            SELECT c.ts_code
            FROM `{stock_table}` c
            WHERE {missing_any}
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

    if dry_run:
        preview_rows = 0
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
                preview_rows += len(_normalize_mainbz_df(apply_transform(part, task)))
                ok_cnt += 1
            if log_every > 0 and i % log_every == 0:
                logger.info("fina_mainbz 进度 %s/%s ok=%s", i, len(codes), ok_cnt)
            if sleep_s > 0 and i < len(codes):
                time.sleep(sleep_s)
        return SyncResult(
            task_id=task["id"],
            source_table=task["source_table"],
            target_table=task["target_table"],
            rows_affected=preview_rows,
            ok=True,
            message="dry-run",
        )

    if sync_mode == "full":
        from mysql_config import get_target_engine

        engine = get_target_engine(task["target_database"])
        with engine.begin() as conn:
            conn.execute(text(f"TRUNCATE TABLE `{task['target_table']}`"))

    total_rows = 0
    ok_cnt = 0
    write_fail = 0
    for i, ts_code in enumerate(codes, start=1):
        try:
            kwargs = {"ts_code": ts_code, "type": bz_type}
            if fields:
                kwargs["fields"] = fields
            part = fetch_tushare("fina_mainbz", token_type=token_type, **kwargs)
        except Exception as exc:
            logger.warning("fina_mainbz ts_code=%s 拉取失败: %s", ts_code, exc)
            continue
        if part.empty:
            continue
        out = _normalize_mainbz_df(apply_transform(part, task))
        if out.empty:
            continue
        try:
            if sync_mode != "full":
                _delete_ts_codes(
                    task["target_database"],
                    task["target_table"],
                    [ts_code],
                    bz_type=bz_type if "bz_type" in out.columns else None,
                )
            total_rows += write_dataframe(
                database=task["target_database"],
                table=task["target_table"],
                df=out,
                sync_mode="append",
                trade_date=None,
            )
            ok_cnt += 1
        except Exception as exc:
            write_fail += 1
            logger.warning("fina_mainbz ts_code=%s 写入失败: %s", ts_code, exc)
        if log_every > 0 and i % log_every == 0:
            logger.info(
                "fina_mainbz 进度 %s/%s 写入成功=%s 行=%s 失败=%s",
                i,
                len(codes),
                ok_cnt,
                total_rows,
                write_fail,
            )
        if sleep_s > 0 and i < len(codes):
            time.sleep(sleep_s)

    logger.info(
        "fina_mainbz id=%s 股票=%s 写入成功=%s 行=%s 写入失败=%s",
        task["id"],
        len(codes),
        ok_cnt,
        total_rows,
        write_fail,
    )

    if ok_cnt == 0:
        return SyncResult(
            task_id=task["id"],
            source_table=task["source_table"],
            target_table=task["target_table"],
            rows_affected=0,
            ok=write_fail == 0,
            message=f"fina_mainbz 未写入数据（待补 {len(codes)} 只，写入失败 {write_fail}）",
        )

    return SyncResult(
        task_id=task["id"],
        source_table=task["source_table"],
        target_table=task["target_table"],
        rows_affected=total_rows,
        ok=write_fail == 0,
        message=f"补全 {ok_cnt} 只股票" + (f"，{write_fail} 只写入失败" if write_fail else ""),
    )


def _sync_vip_by_period(
    task: TaskDict,
    trade_date: date | None,
    dry_run: bool,
    *,
    api_name: str | None = None,
    delete_column: str = "end_date",
) -> SyncResult:
    """按报告期 period 循环拉全市场 VIP/季频接口；snapshot 默认近 N 季，full 季末回溯。

    删除策略：snapshot 按 delete_column（默认 end_date）覆盖写入；full 先 TRUNCATE。
    """
    from sync_writer import write_dataframe

    source = api_name or str(task["source_table"])
    fetch_cfg = get_fetch_config(task)
    token_type = fetch_cfg.get("token_type") or "tushare"
    sync_mode = (task.get("sync_mode") or "snapshot").lower()
    td = trade_date or date.today()
    sleep_s = float(fetch_cfg.get("sleep_seconds") or 0.5)
    base_params = dict(fetch_cfg.get("params") or {})
    # period 由本函数注入，避免配置里残留占位符
    base_params.pop("period", None)
    fields = base_params.pop("fields", None)
    frames: list[pd.DataFrame] = []

    if sync_mode == "full":
        from_yyyymmdd = str(fetch_cfg.get("full_start") or "20180101")
        periods = _quarter_period_ends(from_yyyymmdd, td)
    else:
        snap_n = int(fetch_cfg.get("snapshot_periods") or 2)
        periods = _snapshot_quarter_periods(td, count=snap_n)

    for i, period in enumerate(periods):
        logger.info("%s 进度 %s/%s period=%s mode=%s", source, i + 1, len(periods), period, sync_mode)
        try:
            kwargs: dict[str, Any] = {**base_params, "period": period}
            if fields:
                kwargs["fields"] = fields
            part = fetch_tushare(source, token_type=token_type, **kwargs)
        except Exception as exc:
            logger.warning("%s period=%s 失败: %s", source, period, exc)
            continue
        if not part.empty:
            frames.append(part)
        if sleep_s > 0 and i + 1 < len(periods):
            time.sleep(sleep_s)

    df = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    out = apply_transform(df, task)

    logger.info(
        "%s id=%s 原始=%s 映射后=%s mode=%s periods=%s",
        source,
        task["id"],
        len(df),
        len(out),
        sync_mode,
        len(periods),
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
    elif sync_mode == "snapshot" and not out.empty and delete_column in out.columns:
        end_dates: list[date] = []
        for raw in out[delete_column].dropna().unique():
            if isinstance(raw, date):
                end_dates.append(raw)
            else:
                end_dates.append(pd.Timestamp(raw).date())
        _delete_by_date_values(
            task["target_database"],
            task["target_table"],
            delete_column,
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


@register("tushare", "income_vip")
def sync_income_vip(task: TaskDict, trade_date: date | None, dry_run: bool) -> SyncResult:
    """利润表 VIP：按报告期全市场拉取。"""
    return _sync_vip_by_period(task, trade_date, dry_run)


@register("tushare", "cashflow_vip")
def sync_cashflow_vip(task: TaskDict, trade_date: date | None, dry_run: bool) -> SyncResult:
    """现金流量表 VIP：按报告期全市场拉取（含 CapEx）。"""
    return _sync_vip_by_period(task, trade_date, dry_run)


@register("tushare", "balancesheet_vip")
def sync_balancesheet_vip(
    task: TaskDict, trade_date: date | None, dry_run: bool
) -> SyncResult:
    """资产负债表 VIP：按报告期全市场拉取。"""
    return _sync_vip_by_period(task, trade_date, dry_run)


@register("tushare", "forecast_vip")
def sync_forecast_vip(task: TaskDict, trade_date: date | None, dry_run: bool) -> SyncResult:
    """业绩预告 VIP：按报告期全市场拉取。"""
    return _sync_vip_by_period(task, trade_date, dry_run)


@register("tushare", "express_vip")
def sync_express_vip(task: TaskDict, trade_date: date | None, dry_run: bool) -> SyncResult:
    """业绩快报 VIP：按报告期全市场拉取。"""
    return _sync_vip_by_period(task, trade_date, dry_run)


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

    # ths_hot 与 dc_hot 相同：接口可能返回多日快照，snapshot 只删业务日，须过滤
    if not out.empty and "trade_date" in out.columns:
        before_filter = len(out)
        out = out[out["trade_date"] == td].copy()
        if before_filter != len(out):
            logger.info(
                "ths_hot id=%s 过滤 trade_date=%s: %s -> %s",
                task["id"],
                td,
                before_filter,
                len(out),
            )

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

    # dc_hot 按 trade_date 入参拉数，但接口会返回多日快照；snapshot 只删业务日，须过滤
    if not out.empty and "trade_date" in out.columns:
        before_filter = len(out)
        out = out[out["trade_date"] == td].copy()
        if before_filter != len(out):
            logger.info(
                "dc_hot id=%s 过滤 trade_date=%s: %s -> %s",
                task["id"],
                td,
                before_filter,
                len(out),
            )

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


def _delete_cyq_stock_date(database: str, table: str, ts_code: str, trade_date: date) -> None:
    from mysql_config import get_target_engine

    engine = get_target_engine(database)
    with engine.begin() as conn:
        conn.execute(
            text(f"DELETE FROM `{table}` WHERE ts_code = :tc AND trade_date = :td"),
            {"tc": ts_code, "td": trade_date},
        )


def _load_cyq_stock_codes(task: TaskDict, trade_date: date | None) -> list[str]:
    fetch_cfg = get_fetch_config(task)
    stock_db = str(fetch_cfg.get("stock_database") or task["target_database"])
    stock_table = str(fetch_cfg.get("stock_table") or "ods_stock_detail_di")
    td = trade_date or date.today()
    missing_only = bool(fetch_cfg.get("missing_only", True))
    max_stocks = fetch_cfg.get("max_stocks")

    from mysql_config import get_target_engine

    engine = get_target_engine(stock_db)
    if missing_only:
        sql = f"""
            SELECT d.ts_code
            FROM `{stock_table}` d
            WHERE d.trade_date = :td
              AND NOT EXISTS (
                  SELECT 1 FROM `{task['target_table']}` c
                  WHERE c.ts_code = d.ts_code AND c.trade_date = :td
              )
            ORDER BY d.ts_code
        """
    else:
        sql = f"""
            SELECT ts_code FROM `{stock_table}`
            WHERE trade_date = :td
            ORDER BY ts_code
        """
    with engine.connect() as conn:
        codes = [row[0] for row in conn.execute(text(sql), {"td": td}).fetchall()]

    if max_stocks is not None:
        codes = codes[: int(max_stocks)]
    return codes


@register("tushare", "cyq_chips")
def sync_cyq_chips(task: TaskDict, trade_date: date | None, dry_run: bool) -> SyncResult:
    """cyq_chips 按个股循环拉取当日筹码分布；股票列表来自 ods_stock_detail_di。"""
    from sync_writer import write_dataframe

    fetch_cfg = get_fetch_config(task)
    token_type = fetch_cfg.get("token_type") or "tushare"
    sleep_s = float(fetch_cfg.get("sleep_seconds") or 0.35)
    log_every = int(fetch_cfg.get("batch_log_every") or 200)
    td = trade_date or date.today()
    td_str = td.strftime("%Y%m%d")

    codes = _load_cyq_stock_codes(task, td)
    if not codes:
        return SyncResult(
            task_id=task["id"],
            source_table=task["source_table"],
            target_table=task["target_table"],
            rows_affected=0,
            ok=True,
            message=f"cyq_chips {td_str} 无待同步股票（missing_only 已覆盖或当日无行情）",
        )

    logger.info("cyq_chips 待拉取 %s 只股票 trade_date=%s", len(codes), td_str)

    if dry_run:
        preview_rows = 0
        ok_cnt = 0
        for i, ts_code in enumerate(codes, start=1):
            try:
                part = fetch_tushare(
                    "cyq_chips",
                    token_type=token_type,
                    ts_code=ts_code,
                    trade_date=td_str,
                )
            except Exception as exc:
                logger.warning("cyq_chips ts_code=%s 失败: %s", ts_code, exc)
                continue
            if not part.empty:
                preview_rows += len(apply_transform(part, task))
                ok_cnt += 1
            if log_every > 0 and i % log_every == 0:
                logger.info("cyq_chips 进度 %s/%s ok=%s", i, len(codes), ok_cnt)
            if sleep_s > 0 and i < len(codes):
                time.sleep(sleep_s)
        return SyncResult(
            task_id=task["id"],
            source_table=task["source_table"],
            target_table=task["target_table"],
            rows_affected=preview_rows,
            ok=True,
            message="dry-run",
        )

    total_rows = 0
    ok_cnt = 0
    write_fail = 0
    for i, ts_code in enumerate(codes, start=1):
        try:
            part = fetch_tushare(
                "cyq_chips",
                token_type=token_type,
                ts_code=ts_code,
                trade_date=td_str,
            )
        except Exception as exc:
            logger.warning("cyq_chips ts_code=%s 拉取失败: %s", ts_code, exc)
            continue
        if part.empty:
            continue
        out = apply_transform(part, task)
        if out.empty:
            continue
        try:
            _delete_cyq_stock_date(
                task["target_database"],
                task["target_table"],
                ts_code,
                td,
            )
            total_rows += write_dataframe(
                database=task["target_database"],
                table=task["target_table"],
                df=out,
                sync_mode="append",
                trade_date=None,
            )
            ok_cnt += 1
        except Exception as exc:
            write_fail += 1
            logger.warning("cyq_chips ts_code=%s 写入失败: %s", ts_code, exc)
        if log_every > 0 and i % log_every == 0:
            logger.info(
                "cyq_chips 进度 %s/%s 写入成功=%s 行=%s 失败=%s",
                i,
                len(codes),
                ok_cnt,
                total_rows,
                write_fail,
            )
        if sleep_s > 0 and i < len(codes):
            time.sleep(sleep_s)

    logger.info(
        "cyq_chips id=%s 股票=%s 写入成功=%s 行=%s 写入失败=%s",
        task["id"],
        len(codes),
        ok_cnt,
        total_rows,
        write_fail,
    )

    if ok_cnt == 0:
        return SyncResult(
            task_id=task["id"],
            source_table=task["source_table"],
            target_table=task["target_table"],
            rows_affected=0,
            ok=write_fail == 0,
            message=f"cyq_chips 未写入数据（待拉 {len(codes)} 只，写入失败 {write_fail}）",
        )

    return SyncResult(
        task_id=task["id"],
        source_table=task["source_table"],
        target_table=task["target_table"],
        rows_affected=total_rows,
        ok=write_fail == 0,
        message=f"同步 {ok_cnt} 只股票筹码" + (f"，{write_fail} 只写入失败" if write_fail else ""),
    )


_EM_MONITOR_MARKET = {"1": "SH", "0": "SZ", "B": "BJ"}
_EM_MONITOR_DEFAULT_URL = (
    "https://mobappconfig.securities.eastmoney.com/emcfg/stock_monitor.json"
)


def _em_monitor_ts_code(stk_code: str, market_raw: str) -> str | None:
    code = str(stk_code or "").strip()
    if not code:
        return None
    mkt = _EM_MONITOR_MARKET.get(str(market_raw or "").strip().upper())
    if not mkt:
        return None
    return f"{code}.{mkt}"


def fetch_em_stock_monitor(task: TaskDict) -> pd.DataFrame:
    """拉取东财重点监控池 JSON → DataFrame。"""
    import requests

    cfg = get_fetch_config(task)
    url = str(cfg.get("url") or _EM_MONITOR_DEFAULT_URL)
    referer = str(cfg.get("referer") or "https://vipmoney.eastmoney.com/")
    try:
        timeout = float(cfg.get("timeout") or 20)
    except (TypeError, ValueError):
        timeout = 20.0

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Referer": referer,
        "Accept": "application/json,text/plain,*/*",
    }
    resp = requests.get(url, headers=headers, timeout=timeout)
    resp.raise_for_status()
    payload = resp.json()
    if payload is None:
        return pd.DataFrame()
    if not isinstance(payload, list):
        raise TypeError(f"stock_monitor 返回非列表: {type(payload).__name__}")
    if not payload:
        return pd.DataFrame()
    return pd.DataFrame(payload)


def normalize_em_stock_monitor(df: pd.DataFrame, trade_date: date) -> pd.DataFrame:
    """映射东财字段 → ODS 列。"""
    if df.empty:
        return pd.DataFrame(
            columns=[
                "trade_date",
                "ts_code",
                "stk_code",
                "name",
                "market",
                "start_date",
                "end_date",
                "link_url",
            ]
        )

    rows: list[dict[str, Any]] = []
    for _, raw in df.iterrows():
        stk = str(raw.get("STKCODE") or "").strip()
        market_raw = str(raw.get("MARKET") or "").strip().upper()
        ts_code = _em_monitor_ts_code(stk, market_raw)
        if not ts_code:
            logger.warning(
                "stock_monitor 跳过无法映射市场的记录 code=%s market=%s",
                stk,
                market_raw,
            )
            continue
        start = pd.to_datetime(raw.get("VALIDATESTARTDATE"), errors="coerce")
        end = pd.to_datetime(raw.get("VALIDATEENDDATE"), errors="coerce")
        if pd.isna(start) or pd.isna(end):
            logger.warning(
                "stock_monitor 跳过缺起止日记录 code=%s start=%s end=%s",
                stk,
                raw.get("VALIDATESTARTDATE"),
                raw.get("VALIDATEENDDATE"),
            )
            continue
        rows.append(
            {
                "trade_date": trade_date,
                "ts_code": ts_code,
                "stk_code": stk,
                "name": (str(raw.get("STKNAME")).strip() if raw.get("STKNAME") is not None else None),
                "market": _EM_MONITOR_MARKET[market_raw],
                "start_date": start.date(),
                "end_date": end.date(),
                "link_url": (
                    str(raw.get("LINK_URL")).strip()
                    if raw.get("LINK_URL") not in (None, "")
                    else None
                ),
            }
        )

    out = pd.DataFrame(rows)
    if out.empty:
        return out
    out = out.drop_duplicates(subset=["trade_date", "ts_code"], keep="last")
    return out


@register("eastmoney", "stock_monitor")
def sync_em_stock_monitor(task: TaskDict, trade_date: date | None, dry_run: bool) -> SyncResult:
    """东财重点监控证券池日快照（含监控开始/预计截止）。"""
    from sync_writer import write_dataframe

    td = trade_date or date.today()
    if td < date.today():
        logger.warning(
            "stock_monitor 源为当前池快照；trade_date=%s 早于今天，"
            "写入内容仍是此刻名单，不能代表该历史日的真实池",
            td.isoformat(),
        )

    raw = fetch_em_stock_monitor(task)
    out = normalize_em_stock_monitor(raw, td)
    logger.info(
        "任务 id=%s stock_monitor 原始=%s 映射后=%s trade_date=%s",
        task["id"],
        len(raw),
        len(out),
        td.isoformat(),
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
            message="stock_monitor 返回 0 行，请检查东财 JSON 是否可访问",
        )

    transform_cfg = get_transform_config(task)
    rows = write_dataframe(
        database=task["target_database"],
        table=task["target_table"],
        df=out,
        sync_mode=(task.get("sync_mode") or "snapshot").lower(),
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
    out = apply_transform(df, task, trade_date=trade_date)
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
