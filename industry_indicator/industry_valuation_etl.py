from __future__ import annotations

import argparse
import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, List

import akshare as ak
import pandas as pd
import pymysql


LOG = logging.getLogger(__name__)

DEFAULT_INDICATORS = ["市盈率", "市净率", "股息率"]
DEFAULT_TABLE_NAME = "industry_indicator_valuation"


@dataclass
class DBConfig:
    host: str
    port: int
    user: str
    password: str
    database: str
    table_name: str


def _safe_float(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, str):
        value = value.strip()
        if not value or value in {"--", "nan", "None"}:
            return None
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _pick_value(row: pd.Series, candidates: list[str]) -> object:
    for col in candidates:
        if col in row.index:
            return row[col]
    return None


def _create_table_if_not_exists(conn: pymysql.connections.Connection, table_name: str) -> None:
    ddl = f"""
    CREATE TABLE IF NOT EXISTS {table_name} (
        id BIGINT PRIMARY KEY AUTO_INCREMENT,
        source VARCHAR(64) NOT NULL,
        category_symbol VARCHAR(64) NOT NULL,
        trade_date DATE NOT NULL,
        industry_name VARCHAR(128) NULL,
        industry_code VARCHAR(64) NULL,
        pe_value DECIMAL(20, 6) NULL,
        rank_desc VARCHAR(64) NULL,
        raw_json JSON NOT NULL,
        created_at DATETIME NOT NULL,
        updated_at DATETIME NOT NULL,
        UNIQUE KEY uniq_industry_pe (source, category_symbol, trade_date, industry_name)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """
    with conn.cursor() as cursor:
        cursor.execute(ddl)
    conn.commit()


def _get_category_symbols() -> List[str]:
    # 当前 AkShare 版本下，行业市盈率接口可用分类
    return ["证监会行业分类", "国证行业分类"]


def _normalize_records(category_symbol: str, trade_date: str, df: pd.DataFrame) -> List[tuple]:
    if df is None or df.empty:
        return []

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    rows: List[tuple] = []
    for _, row in df.iterrows():
        industry_name = _pick_value(row, ["行业名称", "行业", "名称"])
        industry_code = _pick_value(row, ["行业编码", "行业代码", "代码"])
        pe_value = _pick_value(row, ["市盈率", "行业市盈率", "PE", "pe"])
        rank_desc = _pick_value(row, ["排名", "排序", "分位", "估值水平"])
        rows.append(
            (
                "akshare.stock_industry_pe_ratio_cninfo",
                category_symbol,
                str(pd.to_datetime(trade_date).date()),
                None if pd.isna(industry_name) else str(industry_name),
                None if pd.isna(industry_code) else str(industry_code),
                _safe_float(pe_value),
                None if pd.isna(rank_desc) else str(rank_desc),
                json.dumps({k: (None if pd.isna(v) else v) for k, v in row.items()}, ensure_ascii=False, default=str),
                now,
                now,
            )
        )
    return rows


def _upsert_rows(conn: pymysql.connections.Connection, table_name: str, rows: Iterable[tuple]) -> int:
    sql = f"""
    INSERT INTO {table_name} (
        source, category_symbol, trade_date, industry_name, industry_code,
        pe_value, rank_desc, raw_json, created_at, updated_at
    )
    VALUES (%s, %s, %s, %s, %s, %s, %s, CAST(%s AS JSON), %s, %s)
    ON DUPLICATE KEY UPDATE
        industry_code = VALUES(industry_code),
        pe_value = VALUES(pe_value),
        rank_desc = VALUES(rank_desc),
        raw_json = VALUES(raw_json),
        updated_at = VALUES(updated_at);
    """
    rows = list(rows)
    if not rows:
        return 0
    with conn.cursor() as cursor:
        cursor.executemany(sql, rows)
    conn.commit()
    return len(rows)


def run(
    host: str,
    port: int,
    user: str,
    password: str,
    database: str,
    trade_date: str,
    table_name: str = DEFAULT_TABLE_NAME,
    category_symbols: list[str] | None = None,
) -> int:
    category_symbols = category_symbols or _get_category_symbols()
    if not category_symbols:
        raise RuntimeError("未获取到任何行业分类，无法抓取行业估值数据。")

    db_cfg = DBConfig(
        host=host,
        port=port,
        user=user,
        password=password,
        database=database,
        table_name=table_name,
    )
    conn = pymysql.connect(
        host=db_cfg.host,
        port=db_cfg.port,
        user=db_cfg.user,
        password=db_cfg.password,
        database=db_cfg.database,
        charset="utf8mb4",
        autocommit=False,
    )
    _create_table_if_not_exists(conn, db_cfg.table_name)

    total = 0
    for category_symbol in category_symbols:
        try:
            df = ak.stock_industry_pe_ratio_cninfo(symbol=category_symbol, date=trade_date)
            rows = _normalize_records(category_symbol=category_symbol, trade_date=trade_date, df=df)
            inserted = _upsert_rows(conn, db_cfg.table_name, rows)
            total += inserted
            LOG.info("category=%s date=%s 写入/更新 %s 条", category_symbol, trade_date, inserted)
        except Exception as exc:  # noqa: BLE001
            LOG.warning("抓取失败 category=%s date=%s: %s", category_symbol, trade_date, exc)
    conn.close()
    return total


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="抓取 AkShare 行业估值数据并写入 MySQL。")
    parser.add_argument(
        "--host",
        default=os.getenv("MYSQL_HOST", "10.100.151.202"),
        help="MySQL 主机地址",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("MYSQL_PORT", "9030")),
        help="MySQL 端口",
    )
    parser.add_argument(
        "--user",
        default=os.getenv("MYSQL_USER", "u_da_insight"),
        help="MySQL 用户名",
    )
    parser.add_argument(
        "--password",
        default=os.getenv("MYSQL_PASSWORD", "insight123456"),
        help="MySQL 密码",
    )
    parser.add_argument(
        "--database",
        default=os.getenv("MYSQL_DATABASE", "data_insight"),
        help="MySQL 数据库名",
    )
    parser.add_argument(
        "--trade-date",
        default=datetime.now().strftime("%Y%m%d"),
        help="查询日期，格式 YYYYMMDD，例如 20210910",
    )
    parser.add_argument(
        "--table-name",
        default=os.getenv("INDUSTRY_TABLE_NAME", DEFAULT_TABLE_NAME),
        help=f"数据库表名，默认 {DEFAULT_TABLE_NAME}",
    )
    parser.add_argument(
        "--category-symbols",
        nargs="+",
        default=None,
        help="行业分类，可选: 证监会行业分类 国证行业分类；不传则默认两者都抓。",
    )
    parser.add_argument(
        "--category-symbol",
        action="append",
        default=None,
        help="可重复追加单个行业分类，例如 --category-symbol 证监会行业分类",
    )
    return parser.parse_args()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = _parse_args()
    merged_category_symbols = args.category_symbols or []
    if args.category_symbol:
        merged_category_symbols.extend(args.category_symbol)
    if not merged_category_symbols:
        merged_category_symbols = None
    count = run(
        host=args.host,
        port=args.port,
        user=args.user,
        password=args.password,
        database=args.database,
        trade_date=args.trade_date,
        table_name=args.table_name,
        category_symbols=merged_category_symbols,
    )
    LOG.info("任务完成，总写入/更新: %s", count)
