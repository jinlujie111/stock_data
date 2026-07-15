"""量化模块：数据库引擎与通用查询工具。

- 因子/行情来源：stock_data（只读），复用 mysql_config.get_engine()
- 结果写入：data_industry，凭 INDUSTRY_MYSQL_* / IFF_MYSQL_* 环境变量构建
"""
from __future__ import annotations

import os
import urllib.parse
from datetime import date, datetime

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

_industry_engine: Engine | None = None


def get_stock_engine() -> Engine:
    """stock_data 业务库（ODS/DWM 因子来源）。

    延迟导入 mysql_config，避免 web 侧复用回测模块时强依赖 dw-utils 环境。
    """
    from mysql_config import get_engine as _get_stock_engine

    return _get_stock_engine()


def _industry_env(key: str, default: str = "") -> str:
    # 与 web 侧 config 对齐：优先 IFF_MYSQL_*，回退 INDUSTRY_MYSQL_*
    return (
        os.getenv(f"IFF_MYSQL_{key}")
        or os.getenv(f"INDUSTRY_MYSQL_{key}")
        or default
    )


def get_industry_engine() -> Engine:
    """data_industry 库（策略/信号/回测结果写入）。"""
    global _industry_engine
    if _industry_engine is None:
        host = _industry_env("HOST", "localhost")
        port = int(_industry_env("PORT", "3306"))
        user = _industry_env("USER", "data_industry")
        password = _industry_env("PASSWORD", "")
        database = _industry_env("DATABASE", "data_industry")
        pwd = urllib.parse.quote_plus(password)
        u = urllib.parse.quote_plus(user)
        url = f"mysql+pymysql://{u}:{pwd}@{host}:{port}/{database}?charset=utf8mb4"
        _industry_engine = create_engine(url, pool_pre_ping=True)
    return _industry_engine


def parse_trade_date(s: str | date | datetime) -> date:
    if isinstance(s, datetime):
        return s.date()
    if isinstance(s, date):
        return s
    raw = str(s).strip().replace("-", "")
    if len(raw) != 8:
        raise ValueError(f"invalid trade_date: {s}")
    return datetime.strptime(raw, "%Y%m%d").date()


def iso(d: date) -> str:
    return d.strftime("%Y-%m-%d")


def list_trading_days(
    engine: Engine, start: date, end: date
) -> list[date]:
    """[start, end] 升序交易日；优先 ods_trading_day，回退个股行情去重。"""
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT trade_date FROM ods_trading_day
                WHERE trade_date BETWEEN :s AND :e
                ORDER BY trade_date ASC
                """
            ),
            {"s": iso(start), "e": iso(end)},
        ).fetchall()
    if rows:
        return [_as_date(r[0]) for r in rows]
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT DISTINCT trade_date FROM ods_stock_detail_di
                WHERE trade_date BETWEEN :s AND :e
                ORDER BY trade_date ASC
                """
            ),
            {"s": iso(start), "e": iso(end)},
        ).fetchall()
    return [_as_date(r[0]) for r in rows]


def trading_days_before(engine: Engine, end: date, n: int) -> list[date]:
    """返回 <= end 的最近 n 个交易日（升序）。"""
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT trade_date FROM ods_trading_day
                WHERE trade_date <= :e
                ORDER BY trade_date DESC
                LIMIT :n
                """
            ),
            {"e": iso(end), "n": int(n)},
        ).fetchall()
    if rows:
        return sorted(_as_date(r[0]) for r in rows)
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT DISTINCT trade_date FROM ods_stock_detail_di
                WHERE trade_date <= :e
                ORDER BY trade_date DESC
                LIMIT :n
                """
            ),
            {"e": iso(end), "n": int(n)},
        ).fetchall()
    return sorted(_as_date(r[0]) for r in rows)


def latest_trade_date(engine: Engine) -> date | None:
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT MAX(trade_date) FROM ods_stock_detail_di")
        ).scalar()
    return _as_date(row) if row else None


def _as_date(v) -> date:
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    return parse_trade_date(str(v))
