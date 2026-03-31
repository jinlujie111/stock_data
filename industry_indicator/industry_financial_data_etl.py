#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
行业财务数据（成分聚合）：申万三级行业 × 乐咕成分表 sw_index_third_cons，
按日快照写入 MySQL。含市值合计、市盈率/市净率/股息率及营收、归母净利同比等聚合值，
明细列统计在 raw_json。

与 industry_financial_indicator_etl 区别：本程序仅请求 legulegu 成分表，不逐股拉同花顺财报，速度较快。
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import akshare as ak
import pandas as pd
import pymysql

LOG = logging.getLogger(__name__)

SOURCE_LEGU = "akshare_legu_sw3_cons"
DEFAULT_TABLE = "industry_financial_data_di"


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
            getattr(cfg, "INDUSTRY_FINANCIAL_DATA_TABLE", DEFAULT_TABLE),
        )
    except Exception:
        return (
            os.getenv("MYSQL_HOST", "localhost"),
            int(os.getenv("MYSQL_PORT", "3306")),
            os.getenv("MYSQL_USER", "root"),
            os.getenv("MYSQL_PASSWORD", ""),
            os.getenv("MYSQL_DATABASE", "stock_data"),
            os.getenv("INDUSTRY_FINANCIAL_DATA_TABLE", DEFAULT_TABLE),
        )


def _normalize_sw_code(val: object) -> str | None:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    s = str(val).strip()
    if not s:
        return None
    if s.upper().endswith(".SI"):
        s = s[:-3].strip()
    return s or None


def _to_num_series(ser: pd.Series) -> pd.Series:
    def one(v: object) -> float | None:
        if v is None or (isinstance(v, float) and pd.isna(v)):
            return None
        s = str(v).strip().replace(",", "").replace("%", "")
        if s in {"", "-", "--", "nan"}:
            return None
        try:
            return float(s)
        except ValueError:
            return None

    return ser.map(one)


def _mean_col(df: pd.DataFrame, col: str | None) -> float | None:
    if not col or col not in df.columns:
        return None
    s = _to_num_series(df[col])
    s = s.dropna()
    if s.empty:
        return None
    return float(s.mean())


def _sum_col(df: pd.DataFrame, col: str | None) -> float | None:
    if not col or col not in df.columns:
        return None
    s = _to_num_series(df[col])
    s = s.dropna()
    if s.empty:
        return None
    return float(s.sum())


def _find_col(df: pd.DataFrame, contains: str, exclude: str | None = None) -> str | None:
    for c in df.columns:
        sc = str(c)
        if contains in sc and (exclude is None or exclude.lower() not in sc.lower()):
            return sc
    return None


def _best_revenue_yoy_col(df: pd.DataFrame) -> str | None:
    best_c, best_n = None, -1
    for c in df.columns:
        sc = str(c)
        if "营业收入同比" in sc or "营业总收入同比" in sc:
            n = _to_num_series(df[c]).notna().sum()
            if n > best_n:
                best_n = n
                best_c = c
    return best_c


def _best_netprofit_yoy_col(df: pd.DataFrame) -> str | None:
    best_c, best_n = None, -1
    for c in df.columns:
        sc = str(c)
        if "归母净利润同比" in sc or "净利润同比" in sc:
            n = _to_num_series(df[c]).notna().sum()
            if n > best_n:
                best_n = n
                best_c = c
    return best_c


def _column_means_snapshot(df: pd.DataFrame) -> dict[str, float]:
    out: dict[str, float] = {}
    for c in df.columns:
        if c in ("序号", "股票代码", "股票简称", "纳入时间"):
            continue
        s = _to_num_series(df[c]).dropna()
        if s.empty:
            continue
        out[str(c)] = float(s.mean())
    return out


def _create_table_if_not_exists(conn: pymysql.connections.Connection, table_name: str) -> None:
    ddl = f"""
    CREATE TABLE IF NOT EXISTS `{table_name}` (
        id BIGINT PRIMARY KEY AUTO_INCREMENT,
        source VARCHAR(64) NOT NULL COMMENT '数据来源',
        trade_date DATE NOT NULL COMMENT '快照业务日期',
        industry_code VARCHAR(32) NOT NULL COMMENT '申万三级等,无.SI',
        industry_name VARCHAR(128) NOT NULL COMMENT '行业名称',
        stock_count INT NULL COMMENT '成分股数量',
        total_market_cap DECIMAL(24, 4) NULL COMMENT '成分市值合计',
        avg_pe DECIMAL(20, 6) NULL COMMENT '市盈率(不含ttm列)均值',
        avg_pe_ttm DECIMAL(20, 6) NULL COMMENT '市盈率TTM均值',
        avg_pb DECIMAL(20, 6) NULL COMMENT '市净率均值',
        avg_dividend_yield DECIMAL(20, 6) NULL COMMENT '股息率均值(%)',
        avg_revenue_yoy DECIMAL(20, 6) NULL COMMENT '营收同比(百分比口径):最佳同比列全成分算术平均,见schema快照说明块',
        avg_netprofit_yoy DECIMAL(20, 6) NULL COMMENT '净利同比(百分比口径):最佳净利同比列全成分算术平均,见schema',
        raw_json JSON NOT NULL COMMENT '列均值等扩展,见schema快照说明块',
        created_at DATETIME NOT NULL,
        updated_at DATETIME NOT NULL,
        UNIQUE KEY uniq_ifd (source, trade_date, industry_code)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='行业财务数据快照(成分聚合),计算逻辑见 schema.sql 注释块';
    """
    with conn.cursor() as cur:
        cur.execute(ddl)
    conn.commit()


def _upsert(
    conn: pymysql.connections.Connection,
    table_name: str,
    rows: list[tuple[Any, ...]],
) -> int:
    if not rows:
        return 0
    sql = f"""
    INSERT INTO `{table_name}` (
        source, trade_date, industry_code, industry_name,
        stock_count, total_market_cap, avg_pe, avg_pe_ttm, avg_pb, avg_dividend_yield,
        avg_revenue_yoy, avg_netprofit_yoy, raw_json, created_at, updated_at
    )
    VALUES (
        %s, %s, %s, %s,
        %s, %s, %s, %s, %s, %s,
        %s, %s, CAST(%s AS JSON), %s, %s
    )
    ON DUPLICATE KEY UPDATE
        industry_name = VALUES(industry_name),
        stock_count = VALUES(stock_count),
        total_market_cap = VALUES(total_market_cap),
        avg_pe = VALUES(avg_pe),
        avg_pe_ttm = VALUES(avg_pe_ttm),
        avg_pb = VALUES(avg_pb),
        avg_dividend_yield = VALUES(avg_dividend_yield),
        avg_revenue_yoy = VALUES(avg_revenue_yoy),
        avg_netprofit_yoy = VALUES(avg_netprofit_yoy),
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
    trade_date: str | None,
    max_industries: int | None,
    sleep_seconds: float,
) -> int:
    run_date = trade_date or datetime.now().strftime("%Y-%m-%d")
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    info = ak.sw_index_third_info()
    if info is None or info.empty:
        LOG.error("sw_index_third_info 为空")
        return 0

    rows_out: list[tuple[Any, ...]] = []
    processed = 0
    for _, ir in info.iterrows():
        if max_industries is not None and processed >= max_industries:
            break
        name = str(ir.get("行业名称", "")).strip()
        code_si = str(ir.get("行业代码", "")).strip()
        if not name or not code_si:
            continue
        code = _normalize_sw_code(code_si) or code_si.replace(".SI", "").replace(".si", "")

        try:
            cons = ak.sw_index_third_cons(symbol=code_si)
        except Exception as exc:  # noqa: BLE001
            LOG.warning("成分表失败 %s %s: %s", code_si, name, exc)
            continue
        if cons is None or cons.empty:
            continue

        mv_col = _find_col(cons, "市值")
        pe_col = _find_col(cons, "市盈率", "ttm")
        pettm_col = _find_col(cons, "市盈率ttm") or _find_col(cons, "市盈率TTM")
        pb_col = _find_col(cons, "市净率")
        div_col = _find_col(cons, "股息率")
        rev_col = _best_revenue_yoy_col(cons)
        np_col = _best_netprofit_yoy_col(cons)

        raw = {
            "industry_code_si": code_si,
            "column_means": _column_means_snapshot(cons),
            "revenue_yoy_column": rev_col,
            "netprofit_yoy_column": np_col,
        }

        rows_out.append(
            (
                SOURCE_LEGU,
                run_date,
                code,
                name,
                int(len(cons)),
                _sum_col(cons, mv_col),
                _mean_col(cons, pe_col),
                _mean_col(cons, pettm_col),
                _mean_col(cons, pb_col),
                _mean_col(cons, div_col),
                _mean_col(cons, rev_col),
                _mean_col(cons, np_col),
                json.dumps(raw, ensure_ascii=False, default=str),
                now,
                now,
            )
        )
        processed += 1
        if sleep_seconds > 0:
            time.sleep(sleep_seconds)

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
        cnt = _upsert(conn, table_name, rows_out)
    finally:
        conn.close()
    LOG.info("行业财务数据快照入库 %s 行 trade_date=%s", cnt, run_date)
    return cnt


def _parse_args() -> argparse.Namespace:
    h, p, u, pw, db, tbl = _mysql_defaults()
    p_ = argparse.ArgumentParser(description="申万三级行业财务数据(成分聚合) → MySQL")
    p_.add_argument("--host", default=h)
    p_.add_argument("--port", type=int, default=p)
    p_.add_argument("--user", default=u)
    p_.add_argument("--password", default=pw)
    p_.add_argument("--database", default=db)
    p_.add_argument("--table-name", default=tbl)
    p_.add_argument("--trade-date", default=None, help="快照日期 YYYY-MM-DD，默认今天")
    p_.add_argument("--max-industries", type=int, default=None, help="仅前 N 个行业(调试)")
    p_.add_argument("--sleep-seconds", type=float, default=0.12, help="请求间隔")
    return p_.parse_args()


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
        trade_date=args.trade_date,
        max_industries=args.max_industries,
        sleep_seconds=args.sleep_seconds,
    )
    LOG.info("完成，写入/更新 %s 行", n)
