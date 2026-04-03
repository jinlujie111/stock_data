#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
申万行业全层级信息与成分股入库（乐咕乐股 / AkShare）。

- 行业：sw_index_first_info / sw_index_second_info / sw_index_third_info
- 成分：对各行业代码调用 sw_index_third_cons（接口名虽为 third，URL 为 index-composition，
  一级、二级指数代码同样适用）

见 industry_indicator/schema.sql 中 sw_industry_info_di / sw_industry_constituent_di 注释块。
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

SOURCE_LEGU = "legulegu_sw"
INFO_TABLE_DEFAULT = "sw_industry_info_di"
CONS_TABLE_DEFAULT = "sw_industry_constituent_di"


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
            getattr(cfg, "SW_INDUSTRY_INFO_TABLE", INFO_TABLE_DEFAULT),
            getattr(cfg, "SW_INDUSTRY_CONSTITUENT_TABLE", CONS_TABLE_DEFAULT),
        )
    except Exception:
        return (
            os.getenv("MYSQL_HOST", "localhost"),
            int(os.getenv("MYSQL_PORT", "3306")),
            os.getenv("MYSQL_USER", "root"),
            os.getenv("MYSQL_PASSWORD", ""),
            os.getenv("MYSQL_DATABASE", "stock_data"),
            os.getenv("SW_INDUSTRY_INFO_TABLE", INFO_TABLE_DEFAULT),
            os.getenv("SW_INDUSTRY_CONSTITUENT_TABLE", CONS_TABLE_DEFAULT),
        )


def _normalize_industry_code(val: object) -> str | None:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    s = str(val).strip()
    if not s:
        return None
    if s.upper().endswith(".SI"):
        s = s[:-3].strip()
    return s or None


def _to_si_code(normalized: str) -> str:
    return f"{normalized.strip().zfill(6)}.SI"


def _category_for_level(level: int) -> str:
    return {1: "SW_L1", 2: "SW_L2", 3: "SW_L3"}[level]


def _fetch_info_frames() -> dict[int, pd.DataFrame]:
    return {
        1: ak.sw_index_first_info(),
        2: ak.sw_index_second_info(),
        3: ak.sw_index_third_info(),
    }


def _create_info_table(conn: pymysql.connections.Connection, table: str) -> None:
    ddl = f"""
    CREATE TABLE IF NOT EXISTS `{table}` (
        id BIGINT PRIMARY KEY AUTO_INCREMENT,
        source VARCHAR(64) NOT NULL,
        trade_date DATE NOT NULL,
        level TINYINT NOT NULL COMMENT '1一级/2二级/3三级',
        category_symbol VARCHAR(16) NOT NULL COMMENT 'SW_L1/SW_L2/SW_L3',
        industry_code VARCHAR(16) NOT NULL COMMENT '6位不含.SI',
        industry_code_si VARCHAR(20) NOT NULL COMMENT '如801010.SI',
        industry_name VARCHAR(128) NULL,
        parent_name VARCHAR(128) NULL COMMENT '上级行业名,L1为空',
        constituent_count INT NULL COMMENT '成份个数(源站)',
        pe_static DECIMAL(20, 6) NULL,
        pe_ttm DECIMAL(20, 6) NULL,
        pb DECIMAL(20, 6) NULL,
        dividend_yield DECIMAL(20, 6) NULL,
        raw_json JSON NOT NULL,
        created_at DATETIME NOT NULL,
        updated_at DATETIME NOT NULL,
        UNIQUE KEY uniq_sw_info (source, trade_date, level, industry_code)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='申万行业信息快照,见schema';
    """
    with conn.cursor() as cur:
        cur.execute(ddl)
    conn.commit()


def _create_cons_table(conn: pymysql.connections.Connection, table: str) -> None:
    ddl = f"""
    CREATE TABLE IF NOT EXISTS `{table}` (
        id BIGINT PRIMARY KEY AUTO_INCREMENT,
        source VARCHAR(64) NOT NULL,
        trade_date DATE NOT NULL,
        level TINYINT NOT NULL,
        industry_code VARCHAR(16) NOT NULL COMMENT '所属行业6位',
        industry_name VARCHAR(128) NULL,
        stock_code VARCHAR(16) NOT NULL COMMENT '6位证券代码',
        stock_name VARCHAR(64) NULL,
        sort_no INT NULL,
        include_date VARCHAR(32) NULL COMMENT '纳入时间,源站原样',
        raw_json JSON NOT NULL,
        created_at DATETIME NOT NULL,
        updated_at DATETIME NOT NULL,
        UNIQUE KEY uniq_sw_cons (source, trade_date, level, industry_code, stock_code)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='申万行业成分股,见schema';
    """
    with conn.cursor() as cur:
        cur.execute(ddl)
    conn.commit()


def _upsert_info(
    conn: pymysql.connections.Connection,
    table: str,
    rows: list[tuple[Any, ...]],
) -> int:
    if not rows:
        return 0
    sql = f"""
    INSERT INTO `{table}` (
        source, trade_date, level, category_symbol, industry_code, industry_code_si,
        industry_name, parent_name, constituent_count, pe_static, pe_ttm, pb, dividend_yield,
        raw_json, created_at, updated_at
    ) VALUES (
        %s, %s, %s, %s, %s, %s,
        %s, %s, %s, %s, %s, %s, %s,
        CAST(%s AS JSON), %s, %s
    )
    ON DUPLICATE KEY UPDATE
        industry_name = VALUES(industry_name),
        parent_name = VALUES(parent_name),
        constituent_count = VALUES(constituent_count),
        pe_static = VALUES(pe_static),
        pe_ttm = VALUES(pe_ttm),
        pb = VALUES(pb),
        dividend_yield = VALUES(dividend_yield),
        raw_json = VALUES(raw_json),
        updated_at = VALUES(updated_at);
    """
    with conn.cursor() as cur:
        cur.executemany(sql, rows)
    conn.commit()
    return len(rows)


def _upsert_cons(
    conn: pymysql.connections.Connection,
    table: str,
    rows: list[tuple[Any, ...]],
) -> int:
    if not rows:
        return 0
    sql = f"""
    INSERT INTO `{table}` (
        source, trade_date, level, industry_code, industry_name,
        stock_code, stock_name, sort_no, include_date, raw_json, created_at, updated_at
    ) VALUES (
        %s, %s, %s, %s, %s,
        %s, %s, %s, %s, CAST(%s AS JSON), %s, %s
    )
    ON DUPLICATE KEY UPDATE
        industry_name = VALUES(industry_name),
        stock_name = VALUES(stock_name),
        sort_no = VALUES(sort_no),
        include_date = VALUES(include_date),
        raw_json = VALUES(raw_json),
        updated_at = VALUES(updated_at);
    """
    with conn.cursor() as cur:
        cur.executemany(sql, rows)
    conn.commit()
    return len(rows)


def _serialize_row(row: pd.Series) -> dict[str, Any]:
    d: dict[str, Any] = {}
    for k, v in row.items():
        if pd.isna(v):
            d[str(k)] = None
        else:
            d[str(k)] = v
    return d


def run(
    host: str,
    port: int,
    user: str,
    password: str,
    database: str,
    info_table: str,
    cons_table: str,
    trade_date: str | None,
    levels: set[int],
    sleep_seconds: float,
    max_industries: int | None,
    skip_constituents: bool,
) -> tuple[int, int]:
    run_date = trade_date or datetime.now().strftime("%Y-%m-%d")
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    frames = _fetch_info_frames()
    info_rows: list[tuple[Any, ...]] = []
    cons_rows: list[tuple[Any, ...]] = []

    processed = 0
    for level in (1, 2, 3):
        if level not in levels:
            continue
        df = frames.get(level)
        if df is None or df.empty:
            LOG.warning("level=%s 行业表为空", level)
            continue
        cat = _category_for_level(level)
        for _, ir in df.iterrows():
            if max_industries is not None and processed >= max_industries:
                break
            code_raw = ir.get("行业代码")
            code = _normalize_industry_code(code_raw)
            if not code:
                continue
            code_si = _to_si_code(code)
            name = str(ir.get("行业名称", "") or "").strip() or None
            parent = None
            if level > 1 and "上级行业" in ir.index:
                p = ir.get("上级行业")
                if p is not None and not (isinstance(p, float) and pd.isna(p)):
                    parent = str(p).strip() or None

            cnt = pd.to_numeric(ir.get("成份个数"), errors="coerce")
            pe_s = pd.to_numeric(ir.get("静态市盈率"), errors="coerce")
            pe_t = pd.to_numeric(ir.get("TTM(滚动)市盈率"), errors="coerce")
            pb = pd.to_numeric(ir.get("市净率"), errors="coerce")
            dy = pd.to_numeric(ir.get("静态股息率"), errors="coerce")

            raw = _serialize_row(ir)
            info_rows.append(
                (
                    SOURCE_LEGU,
                    run_date,
                    level,
                    cat,
                    code,
                    code_si,
                    name,
                    parent,
                    int(cnt) if pd.notna(cnt) else None,
                    float(pe_s) if pd.notna(pe_s) else None,
                    float(pe_t) if pd.notna(pe_t) else None,
                    float(pb) if pd.notna(pb) else None,
                    float(dy) if pd.notna(dy) else None,
                    json.dumps(raw, ensure_ascii=False, default=str),
                    now,
                    now,
                )
            )

            if not skip_constituents:
                try:
                    cdf = ak.sw_index_third_cons(symbol=code_si)
                except Exception as exc:  # noqa: BLE001
                    LOG.warning("成分 %s: %s", code_si, exc)
                    cdf = None
                if cdf is not None and not cdf.empty:
                    sc_col = "股票代码" if "股票代码" in cdf.columns else None
                    sn_col = "股票简称" if "股票简称" in cdf.columns else None
                    so_col = "序号" if "序号" in cdf.columns else None
                    inc_col = "纳入时间" if "纳入时间" in cdf.columns else None
                    for _, cr in cdf.iterrows():
                        sc = str(cr[sc_col]).strip().zfill(6) if sc_col else ""
                        if not sc:
                            continue
                        sort_v = None
                        if so_col:
                            vnum = pd.to_numeric(cr[so_col], errors="coerce")
                            if pd.notna(vnum):
                                sort_v = int(vnum)
                        cons_rows.append(
                            (
                                SOURCE_LEGU,
                                run_date,
                                level,
                                code,
                                name,
                                sc,
                                str(cr[sn_col]).strip() if sn_col else None,
                                sort_v,
                                str(cr[inc_col]).strip()
                                if inc_col and cr[inc_col] is not None
                                else None,
                                json.dumps(
                                    _serialize_row(cr),
                                    ensure_ascii=False,
                                    default=str,
                                ),
                                now,
                                now,
                            )
                        )
                if sleep_seconds > 0:
                    time.sleep(sleep_seconds)

            processed += 1
            if max_industries is not None and processed >= max_industries:
                break
        if max_industries is not None and processed >= max_industries:
            break

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
        _create_info_table(conn, info_table)
        _create_cons_table(conn, cons_table)
        n_info = _upsert_info(conn, info_table, info_rows)
        n_cons = _upsert_cons(conn, cons_table, cons_rows)
    finally:
        conn.close()

    LOG.info(
        "申万行业入库: info=%s 行, constituent=%s 行, trade_date=%s",
        n_info,
        n_cons,
        run_date,
    )
    return n_info, n_cons


def _parse_args() -> argparse.Namespace:
    h, p, u, pw, db, t_info, t_cons = _mysql_defaults()
    parser = argparse.ArgumentParser(description="申万行业信息+成分股 → MySQL")
    parser.add_argument("--host", default=h)
    parser.add_argument("--port", type=int, default=p)
    parser.add_argument("--user", default=u)
    parser.add_argument("--password", default=pw)
    parser.add_argument("--database", default=db)
    parser.add_argument("--info-table", default=t_info)
    parser.add_argument("--cons-table", default=t_cons)
    parser.add_argument("--trade-date", default=None)
    parser.add_argument(
        "--levels",
        default="1,2,3",
        help="逗号分隔 1/2/3，默认全部三级",
    )
    parser.add_argument("--sleep-seconds", type=float, default=0.15)
    parser.add_argument("--max-industries", type=int, default=None, help="调试:最多处理行业条数(跨level累计)")
    parser.add_argument(
        "--skip-constituents",
        action="store_true",
        help="只入库行业信息,不拉成分(快)",
    )
    return parser.parse_args()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = _parse_args()
    lv = {int(x.strip()) for x in args.levels.split(",") if x.strip().isdigit()}
    lv = lv.intersection({1, 2, 3})
    if not lv:
        lv = {1, 2, 3}
    n1, n2 = run(
        host=args.host,
        port=args.port,
        user=args.user,
        password=args.password,
        database=args.database,
        info_table=args.info_table,
        cons_table=args.cons_table,
        trade_date=args.trade_date,
        levels=lv,
        sleep_seconds=args.sleep_seconds,
        max_industries=args.max_industries,
        skip_constituents=args.skip_constituents,
    )
    raise SystemExit(0 if n1 >= 0 else 1)
