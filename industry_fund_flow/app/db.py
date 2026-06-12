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
)

_ROOT = Path(__file__).resolve().parent.parent
_engine: Engine | None = None


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        pwd = urllib.parse.quote_plus(MYSQL_PASSWORD)
        user = urllib.parse.quote_plus(MYSQL_USER)
        url = (
            f"mysql+pymysql://{user}:{pwd}@{MYSQL_HOST}:{MYSQL_PORT}/"
            f"{MYSQL_DATABASE}?charset=utf8mb4"
        )
        _engine = create_engine(url, pool_pre_ping=True)
    return _engine


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


def execute(sql: str, params: dict | None = None) -> int:
    with get_engine().begin() as conn:
        result = conn.execute(text(sql), params or {})
        return result.rowcount
