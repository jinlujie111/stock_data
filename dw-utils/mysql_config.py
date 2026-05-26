#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
项目统一配置：MySQL 连接。
环境变量由 dw-utils/func.sh 注入，禁止在代码中写死账号密码。
"""
from __future__ import annotations

import os
import urllib.parse
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

# --- stock_data 业务库（func.sh 导出为 MYSQL_*）---
MYSQL_HOST = os.getenv("MYSQL_HOST", "localhost")
MYSQL_PORT = int(os.getenv("MYSQL_PORT", "3306"))
MYSQL_USER = os.getenv("MYSQL_USER", "app_user")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "")
MYSQL_DATABASE = os.getenv("MYSQL_DATABASE", "stock_data")

# --- data_config 配置库（db_sync_task、db_token）---
CONFIG_MYSQL_HOST = os.getenv("CONFIG_MYSQL_HOST", "localhost")
CONFIG_MYSQL_PORT = int(os.getenv("CONFIG_MYSQL_PORT", "3306"))
CONFIG_MYSQL_USER = os.getenv("CONFIG_MYSQL_USER", "data_config")
CONFIG_MYSQL_PASSWORD = os.getenv("CONFIG_MYSQL_PASSWORD", "")
CONFIG_MYSQL_DATABASE = os.getenv("CONFIG_MYSQL_DATABASE", "data_config")

STOCK_FUND_FLOW_TABLE = os.getenv("STOCK_FUND_FLOW_TABLE", "stock_fund_flow_di")
MYSQL_DRIVER = os.getenv("MYSQL_DRIVER", "pymysql")


def _build_url(
    host: str,
    port: int,
    user: str,
    password: str,
    database: str,
    driver: str = "pymysql",
) -> str:
    pwd = urllib.parse.quote_plus(password)
    user_q = urllib.parse.quote_plus(user)
    return (
        f"mysql+{driver}://{user_q}:{pwd}@{host}:{port}/"
        f"{database}?charset=utf8mb4"
    )


def get_sqlalchemy_url_pymysql(database: str | None = None) -> str:
    db = database or MYSQL_DATABASE
    return _build_url(MYSQL_HOST, MYSQL_PORT, MYSQL_USER, MYSQL_PASSWORD, db)


def get_config_sqlalchemy_url() -> str:
    return _build_url(
        CONFIG_MYSQL_HOST,
        CONFIG_MYSQL_PORT,
        CONFIG_MYSQL_USER,
        CONFIG_MYSQL_PASSWORD,
        CONFIG_MYSQL_DATABASE,
        MYSQL_DRIVER,
    )


def get_engine(database: str | None = None) -> Engine:
    """业务库 engine；database 为空时用 MYSQL_DATABASE。"""
    db = database or MYSQL_DATABASE
    return create_engine(get_sqlalchemy_url_pymysql(db), pool_pre_ping=True)


def get_config_engine() -> Engine:
    return create_engine(get_config_sqlalchemy_url(), pool_pre_ping=True)


def get_target_engine(target_database: str) -> Engine:
    if target_database == CONFIG_MYSQL_DATABASE:
        return get_config_engine()
    return get_engine(target_database)


def load_db_token(token_type: str = "tushare") -> dict[str, Any] | None:
    """
    从 db_token 读取当前有效的 token（status=1，且在 start_date~end_date 内）。
    返回 token_id、api_url 等字段；无有效记录时返回 None。
    """
    sql = """
        SELECT id, token_type, token_id, api_url, status, remark, start_date, end_date
        FROM db_token
        WHERE token_type = :token_type
          AND status = 1
          AND (start_date IS NULL OR start_date <= NOW())
          AND (end_date IS NULL OR end_date >= NOW())
        ORDER BY id DESC
        LIMIT 1
    """
    engine = get_config_engine()
    with engine.connect() as conn:
        row = conn.execute(text(sql), {"token_type": token_type}).mappings().first()
    return dict(row) if row else None


def load_sync_tasks(
    *,
    task_id: int | None = None,
    source_table: str | None = None,
    status: int = 1,
) -> list[dict[str, Any]]:
    """从 data_config.db_sync_task 读取启用中的同步任务。"""
    sql = """
        SELECT id, proxy_source, source_table, target_database, target_table,
               target_table_describe, sync_mode, status, remark,
               fetch_config, transform_config
        FROM db_sync_task
        WHERE status = :status
    """
    params: dict[str, Any] = {"status": status}
    if task_id is not None:
        sql += " AND id = :task_id"
        params["task_id"] = task_id
    if source_table:
        sql += " AND source_table = :source_table"
        params["source_table"] = source_table
    sql += " ORDER BY id"

    engine = get_config_engine()
    with engine.connect() as conn:
        rows = conn.execute(text(sql), params).mappings().all()
    return [dict(r) for r in rows]


def db_connect_mysql():
    con_string = (
        f"mysql+mysqlconnector://{MYSQL_USER}:{MYSQL_PASSWORD}@{MYSQL_HOST}:"
        f"{MYSQL_PORT}/{MYSQL_DATABASE}?charset=utf8"
    )
    engine = create_engine(con_string)
    return engine.connect()


def db_clost_mysql(connect):
    connect.close()
