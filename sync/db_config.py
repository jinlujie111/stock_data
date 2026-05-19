#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""读取 data_config 库：Token、同步任务配置、写执行日志。连接信息仅来自 func.sh 导出的环境变量。"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

import pymysql

from func_env import require_env, require_env_int


def get_config_connection() -> pymysql.connections.Connection:
    return pymysql.connect(
        host=require_env("CONFIG_MYSQL_HOST"),
        port=require_env_int("CONFIG_MYSQL_PORT"),
        user=require_env("CONFIG_MYSQL_USER"),
        password=require_env("CONFIG_MYSQL_PASSWORD"),
        database=require_env("CONFIG_MYSQL_DATABASE"),
        charset="utf8mb4",
        autocommit=False,
        cursorclass=pymysql.cursors.DictCursor,
    )


def load_active_tokens() -> dict[str, str]:
    sql = """
        SELECT token_type, token_id
        FROM db_token
        WHERE status = 1
    """
    with get_config_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
            rows = cur.fetchall()
    return {str(r["token_type"]): str(r["token_id"]) for r in rows}


def apply_tokens_to_env(*, strict: bool = False) -> None:
    import logging
    import os

    log = logging.getLogger(__name__)
    try:
        tokens = load_active_tokens()
    except Exception as exc:  # noqa: BLE001
        if strict:
            raise
        log.warning("无法从 data_config.db_token 读取 Token: %s", exc)
        return
    for token_type, token_id in tokens.items():
        key = token_type.strip().upper()
        if key == "TUSHARE":
            os.environ["TUSHARE_TOKEN"] = token_id
        else:
            os.environ[f"{key}_TOKEN"] = token_id


@dataclass
class SyncTask:
    task_code: str
    task_name: str
    source_channel: str
    target_database: str
    target_table: str
    sync_mode: str
    script_key: str
    script_args: dict[str, Any]
    depends_on: list[str]
    sort_order: int


def _parse_depends(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [x.strip() for x in raw.split(",") if x.strip()]


def _parse_script_args(raw: Any) -> dict[str, Any]:
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, (bytes, bytearray)):
        raw = raw.decode("utf-8")
    if isinstance(raw, str):
        return json.loads(raw) if raw.strip() else {}
    return {}


def load_sync_tasks(
    *,
    task_codes: list[str] | None = None,
    include_disabled: bool = False,
) -> list[SyncTask]:
    where = ["1=1"]
    params: list[Any] = []
    if not include_disabled:
        where.append("status = 1")
    if task_codes:
        placeholders = ",".join(["%s"] * len(task_codes))
        where.append(f"task_code IN ({placeholders})")
        params.extend(task_codes)

    sql = f"""
        SELECT task_code, task_name, source_channel, target_database, target_table,
               sync_mode, script_key, script_args, depends_on, sort_order
        FROM db_sync_task
        WHERE {' AND '.join(where)}
        ORDER BY sort_order ASC, id ASC
    """
    with get_config_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()

    return [
        SyncTask(
            task_code=r["task_code"],
            task_name=r["task_name"],
            source_channel=r["source_channel"],
            target_database=r["target_database"],
            target_table=r["target_table"],
            sync_mode=r["sync_mode"],
            script_key=r["script_key"],
            script_args=_parse_script_args(r.get("script_args")),
            depends_on=_parse_depends(r.get("depends_on")),
            sort_order=int(r["sort_order"]),
        )
        for r in rows
    ]


def topological_sort(tasks: list[SyncTask]) -> list[SyncTask]:
    code_set = {t.task_code for t in tasks}
    by_code = {t.task_code: t for t in tasks}
    indegree = {t.task_code: 0 for t in tasks}
    graph: dict[str, list[str]] = {t.task_code: [] for t in tasks}

    for t in tasks:
        for dep in t.depends_on:
            if dep not in code_set:
                continue
            graph[dep].append(t.task_code)
            indegree[t.task_code] += 1

    queue = sorted([c for c, d in indegree.items() if d == 0], key=lambda c: by_code[c].sort_order)
    ordered: list[SyncTask] = []
    while queue:
        code = queue.pop(0)
        ordered.append(by_code[code])
        for nxt in sorted(graph[code], key=lambda c: by_code[c].sort_order):
            indegree[nxt] -= 1
            if indegree[nxt] == 0:
                queue.append(nxt)

    if len(ordered) != len(tasks):
        remaining = [t.task_code for t in tasks if t not in ordered]
        raise RuntimeError(f"同步任务存在循环依赖或未满足的依赖: {remaining}")
    return ordered


def mark_task_running(task_code: str) -> None:
    sql = """
        UPDATE db_sync_task
        SET last_sync_status = 'running',
            last_sync_time = NOW(),
            last_error_msg = NULL
        WHERE task_code = %s
    """
    with get_config_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (task_code,))
        conn.commit()


def mark_task_finished(task_code: str, *, success: bool, error_msg: str | None = None) -> None:
    status = "success" if success else "failed"
    sql = """
        UPDATE db_sync_task
        SET last_sync_status = %s,
            last_sync_time = NOW(),
            last_error_msg = %s
        WHERE task_code = %s
    """
    with get_config_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (status, error_msg, task_code))
        conn.commit()


def insert_sync_log(
    *,
    run_id: str,
    task_code: str,
    trade_date: date | None,
    status: str,
    rows_affected: int | None,
    started_at: datetime,
    finished_at: datetime | None,
    error_msg: str | None,
) -> None:
    sql = """
        INSERT INTO db_sync_log
            (run_id, task_code, trade_date, status, rows_affected,
             started_at, finished_at, error_msg)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    """
    with get_config_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                sql,
                (
                    run_id,
                    task_code,
                    trade_date,
                    status,
                    rows_affected,
                    started_at,
                    finished_at,
                    error_msg,
                ),
            )
        conn.commit()
