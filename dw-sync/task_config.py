#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
解析 db_sync_task.fetch_config / transform_config，构建 API 参数与 DataFrame 转换。
"""
from __future__ import annotations

import json
import os
from datetime import date, datetime, timedelta
from typing import Any

import pandas as pd

_NOW_FMT = "%Y-%m-%d %H:%M:%S"

TaskDict = dict[str, Any]


def _parse_json_field(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        return json.loads(value)
    return {}


def get_fetch_config(task: TaskDict) -> dict[str, Any]:
    return _parse_json_field(task.get("fetch_config"))


def get_transform_config(task: TaskDict) -> dict[str, Any]:
    return _parse_json_field(task.get("transform_config"))


def _resolve_template(value: Any, ctx: dict[str, str]) -> Any:
    if not isinstance(value, str):
        return value
    if value in ctx:
        return ctx[value]
    if value.startswith("$") and value[1:] in ctx:
        return ctx[value[1:]]
    if value.startswith("{{") and value.endswith("}}"):
        key = value[2:-2].strip()
        return ctx.get(key, value)
    return value


def _resolve_params(params: dict[str, Any], ctx: dict[str, str]) -> dict[str, Any]:
    return {k: _resolve_template(v, ctx) for k, v in params.items()}


def build_template_context(task: TaskDict, trade_date: date | None) -> dict[str, str]:
    td = trade_date or date.today()
    sync_mode = (task.get("sync_mode") or "snapshot").lower()
    fetch_cfg = get_fetch_config(task)
    dr = fetch_cfg.get("date_range") or {}

    full_cfg = dr.get("full") or {}
    day_cfg = dr.get("day") or dr.get("incremental") or {}

    def _start_end(cfg: dict[str, Any], default_start: str, default_end: str) -> tuple[str, str]:
        start = cfg.get("start_date") or default_start
        end = cfg.get("end_date") or default_end
        return str(start), str(end)

    plus_days = int(fetch_cfg.get("full_end_offset_days") or 365)
    default_full_end = (date.today() + timedelta(days=plus_days)).strftime("%Y%m%d")
    default_full_start = os.getenv(
        "TUSHARE_TRADE_CAL_START_DATE",
        str(fetch_cfg.get("full_start") or "19900101"),
    )

    if sync_mode == "full":
        full_start, full_end = _start_end(full_cfg, default_full_start, default_full_end)
    else:
        full_start, full_end = default_full_start, default_full_end

    td_str = td.strftime("%Y%m%d")
    day_start, day_end = _start_end(day_cfg, td_str, td_str)

    ctx = {
        "trade_date": td_str,
        "today": date.today().strftime("%Y%m%d"),
        "full_start": full_start,
        "full_end": full_end,
        "day_start": day_start,
        "day_end": day_end,
        "today_plus_365": default_full_end,
        "$trade_date": td_str,
        "$today": date.today().strftime("%Y%m%d"),
        "$full_start": full_start,
        "$full_end": full_end,
        "$day_start": day_start,
        "$day_end": day_end,
        "$today_plus_365": default_full_end,
    }
    return ctx


def build_api_call_params_list(task: TaskDict, trade_date: date | None) -> list[dict[str, Any]]:
    """
    根据 fetch_config 生成每次 API 调用的参数字典列表。
    支持：
      - calls: 显式多次调用
      - exchange_list + params + date_range：按交易所展开
      - params：单次调用
    """
    fetch_cfg = get_fetch_config(task)
    ctx = build_template_context(task, trade_date)
    sync_mode = (task.get("sync_mode") or "snapshot").lower()

    if fetch_cfg.get("calls"):
        result = []
        for call in fetch_cfg["calls"]:
            base = dict(fetch_cfg.get("params") or {})
            base.update(call.get("params") or {})
            # calls 项顶层字段亦作为 API 参数（如 index_classify 的 src、index_daily 的 ts_code）
            for key, val in call.items():
                if key != "params":
                    base[key] = val
            result.append(_resolve_params(base, ctx))
        return result

    base_params = dict(fetch_cfg.get("params") or {})
    if fetch_cfg.get("inject_date_range", True) and fetch_cfg.get("date_range"):
        if sync_mode == "full":
            base_params.setdefault("start_date", "$full_start")
            base_params.setdefault("end_date", "$full_end")
        else:
            base_params.setdefault("start_date", "$day_start")
            base_params.setdefault("end_date", "$day_end")

    exchange_list = fetch_cfg.get("exchange_list")
    if exchange_list:
        calls = []
        for ex in exchange_list:
            p = dict(base_params)
            p["exchange"] = ex
            calls.append(_resolve_params(p, ctx))
        return calls

    return [_resolve_params(base_params, ctx)]


def apply_transform(df: pd.DataFrame, task: TaskDict) -> pd.DataFrame:
    """按 transform_config 重命名、解析日期、筛选列、去重。"""
    if df.empty:
        return df

    cfg = get_transform_config(task)
    out = df.copy()

    if cfg.get("add_raw_json"):
        out["raw_json"] = df.apply(
            lambda row: json.dumps(row.to_dict(), ensure_ascii=False, default=str),
            axis=1,
        )

    rename = cfg.get("rename") or {}
    if rename:
        out = out.rename(columns=rename)

    date_columns = cfg.get("date_columns") or {}
    for col, fmt in date_columns.items():
        if col not in out.columns:
            continue
        if fmt:
            out[col] = pd.to_datetime(out[col], format=fmt, errors="coerce").dt.date
        else:
            out[col] = pd.to_datetime(out[col], errors="coerce").dt.date

    constants = cfg.get("constants") or {}
    for col, val in constants.items():
        out[col] = val

    rank_cfg = cfg.get("rank_by")
    if rank_cfg:
        col = rank_cfg.get("column", "main_net_inflow")
        part = rank_cfg.get("partition_by", ["trade_date"])
        ascending = rank_cfg.get("ascending", False)
        keys = [c for c in part if c in out.columns]
        if col in out.columns and keys:
            out["ranking_no"] = (
                out.groupby(keys, dropna=False)[col]
                .rank(ascending=ascending, method="min")
                .astype("Int64")
            )

    dropna = cfg.get("dropna")
    if dropna:
        out = out.dropna(subset=dropna)

    dedupe = cfg.get("dedupe")
    if dedupe:
        keys = [c for c in dedupe if c in out.columns]
        if keys:
            out = out.drop_duplicates(subset=keys, keep="last")

    if cfg.get("add_timestamps"):
        now = datetime.now().strftime(_NOW_FMT)
        out["created_at"] = now
        out["updated_at"] = now

    keep = cfg.get("keep_columns")
    if keep:
        cols = [c for c in keep if c in out.columns]
        out = out[cols]

    return out


def write_trade_date_for_sync_mode(task: TaskDict, trade_date: date | None) -> date | None:
    """full 模式写库不按日删；incremental/snapshot 用业务日。"""
    sync_mode = (task.get("sync_mode") or "snapshot").lower()
    if sync_mode == "full":
        return None
    return trade_date or date.today()
