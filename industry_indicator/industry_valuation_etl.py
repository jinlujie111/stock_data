#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
行业估值：AkShare 申万行业（乐咕乐股）静态/TTM 市盈率、市净率、股息率 → MySQL industry_indicator_valuation。

数据源：akshare.sw_index_first_info / sw_index_second_info / sw_index_third_info
说明：为当日网站快照，非任意历史日回放；历史分位需自行按日累积本表后计算。
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import akshare as ak
import pandas as pd
import pymysql

LOG = logging.getLogger(__name__)

SOURCE_LEGU = "legulegu_sw"
DEFAULT_TABLE = "industry_indicator_valuation"

_FETCHERS = {
    1: (ak.sw_index_first_info, "SW_L1", "申万一级"),
    2: (ak.sw_index_second_info, "SW_L2", "申万二级"),
    3: (ak.sw_index_third_info, "SW_L3", "申万三级"),
}


def _load_config():
    _here = Path(__file__).resolve().parent
    if str(_here) not in sys.path:
        sys.path.insert(0, str(_here))
    import config as cfg  # noqa: E402

    return cfg


def _mysql_defaults():
    try:
        cfg = _load_config()
        return (
            cfg.MYSQL_HOST,
            cfg.MYSQL_PORT,
            cfg.MYSQL_USER,
            cfg.MYSQL_PASSWORD,
            cfg.MYSQL_DATABASE,
            getattr(cfg, "INDUSTRY_VALUATION_TABLE", DEFAULT_TABLE),
        )
    except Exception:
        return (
            os.getenv("MYSQL_HOST", "localhost"),
            int(os.getenv("MYSQL_PORT", "3306")),
            os.getenv("MYSQL_USER", "root"),
            os.getenv("MYSQL_PASSWORD", ""),
            os.getenv("MYSQL_DATABASE", "stock_data"),
            os.getenv("INDUSTRY_VALUATION_TABLE", DEFAULT_TABLE),
        )


def _normalize_industry_code(val: object) -> str | None:
    """
    申万指数源常为 801010.SI；入库统一为 6 位数字（如 801010），与 industry_fund_flow_di 等表对齐。
    raw_json 仍保留接口原始字段。
    """
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    s = str(val).strip()
    if not s:
        return None
    suf = s.upper()
    if suf.endswith(".SI"):
        s = s[:-3].strip()
    return s or None


def _create_table_if_not_exists(conn: pymysql.connections.Connection, table_name: str) -> None:
    ddl = f"""
    CREATE TABLE IF NOT EXISTS `{table_name}` (
        id BIGINT PRIMARY KEY AUTO_INCREMENT,
        source VARCHAR(64) NOT NULL COMMENT '数据来源标识',
        category_symbol VARCHAR(64) NOT NULL COMMENT '分类维度，如 SW_L1/SW_L2/SW_L3',
        trade_date DATE NOT NULL COMMENT '入库业务日期(快照按抓取日)',
        industry_name VARCHAR(128) NULL COMMENT '行业名称',
        industry_code VARCHAR(64) NULL COMMENT '行业代码',
        pe_value DECIMAL(20, 6) NULL COMMENT 'TTM滚动市盈率',
        pe_static DECIMAL(20, 6) NULL COMMENT '静态市盈率',
        pb_value DECIMAL(20, 6) NULL COMMENT '市净率',
        ps_value DECIMAL(20, 6) NULL COMMENT '市销率(预留)',
        dividend_yield DECIMAL(20, 6) NULL COMMENT '静态股息率',
        rank_desc VARCHAR(64) NULL COMMENT '层级说明',
        raw_json JSON NOT NULL,
        created_at DATETIME NOT NULL,
        updated_at DATETIME NOT NULL,
        UNIQUE KEY uniq_industry_pe (source, category_symbol, trade_date, industry_name)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='行业估值快照';
    """
    with conn.cursor() as cur:
        cur.execute(ddl)
    conn.commit()


def _ensure_extra_columns(conn: pymysql.connections.Connection, table_name: str) -> None:
    """旧表缺列时补齐。"""
    alters: list[tuple[str, str]] = [
        ("pe_static", "ADD COLUMN pe_static DECIMAL(20, 6) NULL COMMENT '静态市盈率' AFTER pe_value"),
        ("pb_value", "ADD COLUMN pb_value DECIMAL(20, 6) NULL COMMENT '市净率' AFTER pe_static"),
        ("ps_value", "ADD COLUMN ps_value DECIMAL(20, 6) NULL COMMENT '市销率(预留)' AFTER pb_value"),
        (
            "dividend_yield",
            "ADD COLUMN dividend_yield DECIMAL(20, 6) NULL COMMENT '静态股息率' AFTER ps_value",
        ),
    ]
    with conn.cursor() as cur:
        for col, alter_sql in alters:
            cur.execute(f"SHOW COLUMNS FROM `{table_name}` LIKE %s", (col,))
            if not cur.fetchone():
                cur.execute(f"ALTER TABLE `{table_name}` {alter_sql}")
    conn.commit()


def _row_to_tuple(
    row: pd.Series,
    trade_date: str,
    category_symbol: str,
    rank_desc: str,
    now: str,
) -> tuple[Any, ...]:
    name = row.get("行业名称")
    if name is None or (isinstance(name, float) and pd.isna(name)):
        name = None
    else:
        name = str(name).strip() or None

    code = _normalize_industry_code(row.get("行业代码"))

    pe_static = pd.to_numeric(row.get("静态市盈率"), errors="coerce")
    pe_ttm = pd.to_numeric(row.get("TTM(滚动)市盈率"), errors="coerce")
    pb = pd.to_numeric(row.get("市净率"), errors="coerce")
    divy = pd.to_numeric(row.get("静态股息率"), errors="coerce")

    pe_static_f = float(pe_static) if pd.notna(pe_static) else None
    pe_ttm_f = float(pe_ttm) if pd.notna(pe_ttm) else None
    pb_f = float(pb) if pd.notna(pb) else None
    divy_f = float(divy) if pd.notna(divy) else None

    raw = {k: (None if pd.isna(v) else v) for k, v in row.items()}
    raw_json = json.dumps(raw, ensure_ascii=False, default=str)

    return (
        SOURCE_LEGU,
        category_symbol,
        trade_date,
        name,
        code,
        pe_ttm_f,
        pe_static_f,
        pb_f,
        None,
        divy_f,
        rank_desc,
        raw_json,
        now,
        now,
    )


def _upsert(
    conn: pymysql.connections.Connection,
    table_name: str,
    rows: list[tuple[Any, ...]],
) -> int:
    if not rows:
        return 0
    sql = f"""
    INSERT INTO `{table_name}` (
        source, category_symbol, trade_date, industry_name, industry_code,
        pe_value, pe_static, pb_value, ps_value, dividend_yield,
        rank_desc, raw_json, created_at, updated_at
    )
    VALUES (
        %s, %s, %s, %s, %s,
        %s, %s, %s, %s, %s,
        %s, CAST(%s AS JSON), %s, %s
    )
    ON DUPLICATE KEY UPDATE
        industry_code = VALUES(industry_code),
        pe_value = VALUES(pe_value),
        pe_static = VALUES(pe_static),
        pb_value = VALUES(pb_value),
        ps_value = VALUES(ps_value),
        dividend_yield = VALUES(dividend_yield),
        rank_desc = VALUES(rank_desc),
        raw_json = VALUES(raw_json),
        updated_at = VALUES(updated_at);
    """
    with conn.cursor() as cur:
        cur.executemany(sql, rows)
    conn.commit()
    return len(rows)


def run(
    host: str,
    port: int,
    user: str,
    password: str,
    database: str,
    table_name: str,
    level: int = 3,
    trade_date: str | None = None,
) -> int:
    if level not in _FETCHERS:
        raise ValueError("level 须为 1、2 或 3（申万一级/二级/三级）")

    fetcher, cat_sym, rank_desc = _FETCHERS[level]
    run_date = trade_date or datetime.now().strftime("%Y-%m-%d")
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    try:
        df = fetcher()
    except Exception as exc:  # noqa: BLE001 — 乐咕 504/改版等导致 akshare 解析失败
        LOG.warning(
            "申万行业估值抓取失败（站点不可用或页面与 akshare 不匹配）: level=%s %s, %s",
            level,
            rank_desc,
            exc,
        )
        return 0
    if df is None or df.empty:
        LOG.warning("申万行业估值接口返回空: level=%s", level)
        return 0

    tuples = [_row_to_tuple(row, run_date, cat_sym, rank_desc, now) for _, row in df.iterrows()]

    conn = pymysql.connect(
        host=host,
        port=port,
        user=user,
        password=password,
        database=database,
        charset="utf8mb4",
        autocommit=False,
    )
    try:
        _create_table_if_not_exists(conn, table_name)
        _ensure_extra_columns(conn, table_name)
        n = _upsert(conn, table_name, tuples)
    finally:
        conn.close()

    LOG.info(
        "行业估值入库完成: level=%s %s, trade_date=%s, 行数=%s",
        level,
        rank_desc,
        run_date,
        n,
    )
    return n


def _parse_args() -> argparse.Namespace:
    h, p, u, pw, db, tbl = _mysql_defaults()
    parser = argparse.ArgumentParser(description="申万行业估值 → MySQL（AkShare 乐咕乐股）")
    parser.add_argument("--host", default=h)
    parser.add_argument("--port", type=int, default=p)
    parser.add_argument("--user", default=u)
    parser.add_argument("--password", default=pw)
    parser.add_argument("--database", default=db)
    parser.add_argument("--table-name", default=tbl)
    parser.add_argument(
        "--level",
        type=int,
        choices=[1, 2, 3],
        default=3,
        help="申万行业层级：1 一级 / 2 二级 / 3 三级（默认）",
    )
    parser.add_argument(
        "--trade-date",
        default=None,
        help="入库业务日期 YYYY-MM-DD，默认今天",
    )
    parser.add_argument(
        "--all-levels",
        action="store_true",
        help="依次写入申万一级、二级、三级（忽略 --level）",
    )
    return parser.parse_args()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = _parse_args()
    total = 0
    levels = [1, 2, 3] if args.all_levels else [args.level]
    for lv in levels:
        total += run(
            host=args.host,
            port=args.port,
            user=args.user,
            password=args.password,
            database=args.database,
            table_name=args.table_name,
            level=lv,
            trade_date=args.trade_date,
        )
    LOG.info("任务结束，合计写入/更新 %s 行", total)
