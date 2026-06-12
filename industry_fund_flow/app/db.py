from __future__ import annotations

import urllib.parse
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from app.config import (
    MYSQL_DATABASE,
    MYSQL_HOST,
    MYSQL_PASSWORD,
    MYSQL_PORT,
    MYSQL_USER,
    STOCK_MYSQL_DATABASE,
    STOCK_MYSQL_HOST,
    STOCK_MYSQL_PASSWORD,
    STOCK_MYSQL_PORT,
    STOCK_MYSQL_USER,
)

_ROOT = Path(__file__).resolve().parent.parent
_user_engine: Engine | None = None
_stock_engine: Engine | None = None


def _build_engine(host: str, port: int, user: str, password: str, database: str) -> Engine:
    pwd = urllib.parse.quote_plus(password)
    u = urllib.parse.quote_plus(user)
    url = f"mysql+pymysql://{u}:{pwd}@{host}:{port}/{database}?charset=utf8mb4"
    return create_engine(url, pool_pre_ping=True)


def get_engine() -> Engine:
    global _user_engine
    if _user_engine is None:
        _user_engine = _build_engine(
            MYSQL_HOST, MYSQL_PORT, MYSQL_USER, MYSQL_PASSWORD, MYSQL_DATABASE
        )
    return _user_engine


def get_stock_engine() -> Engine:
    global _stock_engine
    if _stock_engine is None:
        _stock_engine = _build_engine(
            STOCK_MYSQL_HOST,
            STOCK_MYSQL_PORT,
            STOCK_MYSQL_USER,
            STOCK_MYSQL_PASSWORD,
            STOCK_MYSQL_DATABASE,
        )
    return _stock_engine


def init_schema() -> None:
    sql_file = _ROOT / "sql" / "app_user.sql"
    ddl = sql_file.read_text(encoding="utf-8")
    with get_engine().begin() as conn:
        for stmt in ddl.split(";"):
            s = stmt.strip()
            if s:
                conn.execute(text(s))


def fetch_one(sql: str, params: dict | None = None) -> dict | None:
    with get_engine().connect() as conn:
        row = conn.execute(text(sql), params or {}).mappings().first()
    return dict(row) if row else None


def fetch_all_stock(sql: str, params: dict | None = None) -> list[dict]:
    with get_stock_engine().connect() as conn:
        rows = conn.execute(text(sql), params or {}).mappings().all()
    return [dict(r) for r in rows]


def fetch_one_stock(sql: str, params: dict | None = None) -> dict | None:
    with get_stock_engine().connect() as conn:
        row = conn.execute(text(sql), params or {}).mappings().first()
    return dict(row) if row else None


def execute(sql: str, params: dict | None = None) -> int:
    with get_engine().begin() as conn:
        result = conn.execute(text(sql), params or {})
        return result.rowcount
