#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
同花顺个股资金流向快照 → MySQL（AkShare stock_fund_flow_individual）。

与 industry_fund_flow_etl（行业）同源；本任务默认仅抓取「即时」快照。
"""
from __future__ import annotations

import argparse
import json
import logging
import math
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Iterable

import akshare as ak
import pandas as pd
import pymysql

LOG = logging.getLogger(__name__)

DEFAULT_TABLE_NAME = "stock_fund_flow_di"

DEFAULT_PERIODS = ["\u5373\u65f6"]

PERIOD_ALIAS = {
    "now": "\u5373\u65f6",
    "real": "\u5373\u65f6",
    "3d": "3\u65e5\u6392\u884c",
    "5d": "5\u65e5\u6392\u884c",
    "10d": "10\u65e5\u6392\u884c",
    "20d": "20\u65e5\u6392\u884c",
}


def _load_config():
    """配置在 utils/mysql_config.py（项目根由 sync_runner 注入 STOCK_DATA_ROOT）。"""
    root = Path(__file__).resolve().parent.parent
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from utils import mysql_config as cfg  # noqa: E402

    return cfg


def _mysql_defaults_from_config():
    try:
        cfg = _load_config()
        return (
            cfg.MYSQL_HOST,
            cfg.MYSQL_PORT,
            cfg.MYSQL_USER,
            cfg.MYSQL_PASSWORD,
            cfg.MYSQL_DATABASE,
            getattr(cfg, "STOCK_FUND_FLOW_TABLE", DEFAULT_TABLE_NAME),
        )
    except Exception:
        return (
            os.getenv("MYSQL_HOST", "localhost"),
            int(os.getenv("MYSQL_PORT", "3306")),
            os.getenv("MYSQL_USER", "root"),
            os.getenv("MYSQL_PASSWORD", "jinlujie"),
            os.getenv("MYSQL_DATABASE", "stock_data"),
            os.getenv("STOCK_FUND_FLOW_TABLE", DEFAULT_TABLE_NAME),
        )


def _safe_float(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    if isinstance(value, str):
        text = value.strip().replace(",", "").replace("，", "").replace("%", "")
        if text in {"", "--", "nan", "None"}:
            return None
        value = text
    try:
        out = float(value)  # type: ignore[arg-type]
        if math.isnan(out) or math.isinf(out):
            return None
        return out
    except (TypeError, ValueError):
        return None


def _parse_amount_yi(value: object) -> float | None:
    """
    同花顺资金列常见格式：「12.19亿」「6419.00万」「-1.51亿」→ 统一为 float 亿元。
    已是纯数字时按亿元数值直接解析。
    """
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        x = float(value)
        if math.isnan(x) or math.isinf(x):
            return None
        return x
    s = str(value).strip().replace(",", "").replace("，", "")
    if not s or s in {"--", "nan", "None"}:
        return None
    sign = 1.0
    if s[0] == "-":
        sign = -1.0
        s = s[1:].strip()
    elif s[0] == "+":
        s = s[1:].strip()
    if s.endswith("亿"):
        num = _safe_float(s[:-1])
        return None if num is None else sign * num
    if s.endswith("万"):
        num = _safe_float(s[:-1])
        return None if num is None else sign * (num / 10000.0)
    num = _safe_float(s)
    return None if num is None else sign * num


def _safe_int(value: object) -> int | None:
    num = _safe_float(value)
    if num is None:
        return None
    return int(num)


def _norm_stock_code(value: object) -> str | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    s = str(value).strip()
    if not s or s == "--":
        return None
    digits = "".join(c for c in s if c.isdigit())
    if len(digits) >= 6:
        return digits[-6:]
    return digits.zfill(6) if digits else None


def _create_table_if_not_exists(conn: pymysql.connections.Connection, table_name: str) -> None:
    ddl = f"""
    CREATE TABLE IF NOT EXISTS {table_name} (
        id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '自增主键',
        trade_date DATE NOT NULL COMMENT '数据日期(入库业务日)',
        period_type VARCHAR(32) NOT NULL COMMENT '周期: 即时/3日排行/5日排行/10日排行/20日排行',
        ranking_no INT NULL COMMENT '排名(同花顺序号)',
        stock_code VARCHAR(16) NOT NULL COMMENT '股票代码(6位)',
        stock_name VARCHAR(64) NOT NULL COMMENT '股票简称',
        latest_price DECIMAL(20, 6) NULL COMMENT '最新价',
        change_pct DECIMAL(20, 6) NULL COMMENT '涨跌幅或阶段涨跌幅(%)',
        turnover_rate DECIMAL(20, 6) NULL COMMENT '换手率或连续换手率(%)',
        inflow_amt DECIMAL(20, 6) NULL COMMENT '流入资金(亿元)，即时口径',
        outflow_amt DECIMAL(20, 6) NULL COMMENT '流出资金(亿元)，即时口径',
        net_amt DECIMAL(20, 6) NULL COMMENT '净额或资金流入净额(亿元)',
        turnover_amt DECIMAL(20, 6) NULL COMMENT '成交额(亿元)，仅即时口径有',
        raw_json JSON NOT NULL COMMENT '原始行JSON',
        created_at DATETIME NOT NULL COMMENT '创建时间',
        updated_at DATETIME NOT NULL COMMENT '更新时间',
        UNIQUE KEY uniq_stock_fund_flow (trade_date, period_type, stock_code)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='个股资金流向日报(同花顺)';
    """
    with conn.cursor() as cursor:
        cursor.execute(ddl)
    conn.commit()


def _normalize_period(period: str) -> str:
    key = period.strip().lower()
    return PERIOD_ALIAS.get(key, period.strip())


def _row_to_fields(row: pd.Series, period_type: str) -> dict | None:
    code = _norm_stock_code(row.get("股票代码"))
    name = row.get("股票简称")
    if code is None or name is None or (isinstance(name, float) and pd.isna(name)):
        return None
    name_s = str(name).strip()
    if not name_s:
        return None

    rank = _safe_int(row.get("序号"))

    if period_type == "\u5373\u65f6":
        return {
            "ranking_no": rank,
            "stock_code": code,
            "stock_name": name_s,
            "latest_price": _safe_float(row.get("最新价")),
            "change_pct": _safe_float(row.get("涨跌幅")),
            "turnover_rate": _safe_float(row.get("换手率")),
            "inflow_amt": _parse_amount_yi(row.get("流入资金")),
            "outflow_amt": _parse_amount_yi(row.get("流出资金")),
            "net_amt": _parse_amount_yi(row.get("净额")),
            "turnover_amt": _parse_amount_yi(row.get("成交额")),
        }

    return {
        "ranking_no": rank,
        "stock_code": code,
        "stock_name": name_s,
        "latest_price": _safe_float(row.get("最新价")),
        "change_pct": _safe_float(row.get("阶段涨跌幅")),
        "turnover_rate": _safe_float(row.get("连续换手率")),
        "inflow_amt": None,
        "outflow_amt": None,
        "net_amt": _parse_amount_yi(row.get("资金流入净额")),
        "turnover_amt": None,
    }


def _normalize_records(
    period_type: str,
    trade_date: str,
    df: pd.DataFrame,
    max_rows: int | None,
) -> list[tuple]:
    if df is None or df.empty:
        return []
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    rows: list[tuple] = []
    for _, row in df.iterrows():
        m = _row_to_fields(row, period_type)
        if not m:
            continue
        rows.append(
            (
                trade_date,
                period_type,
                m["ranking_no"],
                m["stock_code"],
                m["stock_name"],
                m["latest_price"],
                m["change_pct"],
                m["turnover_rate"],
                m["inflow_amt"],
                m["outflow_amt"],
                m["net_amt"],
                m["turnover_amt"],
                json.dumps(
                    {k: (None if pd.isna(v) else v) for k, v in row.items()},
                    ensure_ascii=False,
                    default=str,
                ),
                now,
                now,
            )
        )
        if max_rows is not None and len(rows) >= max_rows:
            break
    return rows


def _upsert_rows(conn: pymysql.connections.Connection, table_name: str, rows: Iterable[tuple]) -> int:
    rows = list(rows)
    if not rows:
        return 0
    sql = f"""
    INSERT INTO {table_name} (
        trade_date, period_type, ranking_no, stock_code, stock_name, latest_price, change_pct,
        turnover_rate, inflow_amt, outflow_amt, net_amt, turnover_amt, raw_json, created_at, updated_at
    )
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, CAST(%s AS JSON), %s, %s)
    ON DUPLICATE KEY UPDATE
        ranking_no = VALUES(ranking_no),
        stock_name = VALUES(stock_name),
        latest_price = VALUES(latest_price),
        change_pct = VALUES(change_pct),
        turnover_rate = VALUES(turnover_rate),
        inflow_amt = VALUES(inflow_amt),
        outflow_amt = VALUES(outflow_amt),
        net_amt = VALUES(net_amt),
        turnover_amt = VALUES(turnover_amt),
        raw_json = VALUES(raw_json),
        updated_at = VALUES(updated_at);
    """
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
    table_name: str = DEFAULT_TABLE_NAME,
    periods: list[str] | None = None,
    trade_date: str | None = None,
    max_rows: int | None = None,
) -> int:
    periods = periods or DEFAULT_PERIODS
    periods = [_normalize_period(p) for p in periods]
    run_date = trade_date or datetime.now().strftime("%Y-%m-%d")

    conn = pymysql.connect(
        host=host,
        port=port,
        user=user,
        password=password,
        database=database,
        charset="utf8mb4",
        autocommit=False,
    )
    _create_table_if_not_exists(conn, table_name)

    total = 0
    for period in periods:
        try:
            df = ak.stock_fund_flow_individual(symbol=period)
            batch = _normalize_records(period, run_date, df, max_rows)
            n = _upsert_rows(conn, table_name, batch)
            total += n
            LOG.info("period=%s 写入/更新 %s 条", period, n)
        except Exception as exc:  # noqa: BLE001
            LOG.warning("period=%s 抓取失败: %s", period, exc)
    conn.close()
    return total


def _parse_args() -> argparse.Namespace:
    h, p, u, pw, db, tbl = _mysql_defaults_from_config()
    parser = argparse.ArgumentParser(
        description="抓取同花顺个股资金流向(AkShare stock_fund_flow_individual)并写入 MySQL。"
    )
    parser.add_argument("--host", default=h)
    parser.add_argument("--port", type=int, default=p)
    parser.add_argument("--user", default=u)
    parser.add_argument("--password", default=pw)
    parser.add_argument("--database", default=db)
    parser.add_argument("--table-name", default=tbl)
    parser.add_argument(
        "--periods",
        nargs="+",
        default=DEFAULT_PERIODS,
        help="即时 3日排行 5日排行 10日排行 20日排行",
    )
    parser.add_argument("--trade-date", default=None, help="入库日期 YYYY-MM-DD，默认今天")
    parser.add_argument(
        "--max-rows",
        type=int,
        default=None,
        help="每个 period 最多入库条数(调试用；默认不限制)",
    )
    return parser.parse_args()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = _parse_args()
    n = run(
        host=args.host,
        port=args.port,
        user=args.user,
        password=args.password,
        database=args.database,
        table_name=args.table_name,
        periods=args.periods,
        trade_date=args.trade_date,
        max_rows=args.max_rows,
    )
    LOG.info("任务完成，总写入/更新: %s", n)
