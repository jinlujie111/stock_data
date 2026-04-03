#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
行业「订单量」代理指标入库。

计算方法：见 industry_indicator/schema.sql 中 industry_order_volume_di 注释块。
摘要：对申万三级行业成分股（按市值截断样本）的最新资产负债表「合同负债」求和，
作为行业层面订单蓄水/在手订单规模的货币化代理（非物理件数）。
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

SOURCE_THS_CL_SW3 = "ths_contract_liab_sum_sw3"
METHOD_KEY = "contract_liab_latest_sum"
DEFAULT_TABLE = "industry_order_volume_di"


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
            getattr(cfg, "INDUSTRY_ORDER_VOLUME_TABLE", DEFAULT_TABLE),
        )
    except Exception:
        return (
            os.getenv("MYSQL_HOST", "localhost"),
            int(os.getenv("MYSQL_PORT", "3306")),
            os.getenv("MYSQL_USER", "root"),
            os.getenv("MYSQL_PASSWORD", ""),
            os.getenv("MYSQL_DATABASE", "stock_data"),
            os.getenv("INDUSTRY_ORDER_VOLUME_TABLE", DEFAULT_TABLE),
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


def _symbol_for_ths(code6: str) -> str:
    c = str(code6).strip().zfill(6)
    return c


def _find_col(df: pd.DataFrame, substr: str) -> str | None:
    for c in df.columns:
        if substr in str(c):
            return str(c)
    return None


def _parse_contract_liab_cell(val: object) -> float | None:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    v = pd.to_numeric(val, errors="coerce")
    if pd.notna(v):
        return float(v)
    s = str(val).strip().replace(",", "")
    if s in {"", "-", "--"}:
        return None
    # 常见「xx亿」简写（源站格式不一，尽力解析）
    if "亿" in s:
        s = s.replace("亿元", "").replace("亿", "").strip()
        try:
            return float(s)
        except ValueError:
            return None
    try:
        return float(s)
    except ValueError:
        return None


def _latest_contract_liab_level(symbol6: str) -> float | None:
    """最新一期资产负债表「合同负债」余额（与源站单位一致，多为亿元）。"""
    try:
        df = ak.stock_financial_debt_ths(symbol=_symbol_for_ths(symbol6), indicator="按报告期")
    except Exception as exc:  # noqa: BLE001
        LOG.debug("debt %s: %s", symbol6, exc)
        return None
    if df is None or df.empty:
        return None
    cl_col = _find_col(df, "合同负债")
    if not cl_col:
        return None
    date_col = _find_col(df, "报告期") or str(df.columns[0])
    sub = df[[date_col, cl_col]].copy()
    sub["_d"] = pd.to_datetime(sub[date_col], errors="coerce")
    sub = sub.dropna(subset=["_d"]).sort_values("_d")
    if sub.empty:
        return None
    last = sub.iloc[-1]
    return _parse_contract_liab_cell(last[cl_col])


def _sample_symbols(cons: pd.DataFrame, max_stocks: int) -> list[str]:
    if cons is None or cons.empty:
        return []
    code_col = "股票代码" if "股票代码" in cons.columns else None
    if not code_col:
        return []
    mv_col = "市值" if "市值" in cons.columns else None
    sub = cons.copy()
    if mv_col:
        sub["_mv"] = pd.to_numeric(sub[mv_col], errors="coerce")
        sub = sub.sort_values("_mv", ascending=False)
    else:
        sub = sub.reset_index(drop=True)
    out: list[str] = []
    for _, r in sub.iterrows():
        c = str(r[code_col]).strip().zfill(6)
        if c.isdigit():
            out.append(c)
        if max_stocks > 0 and len(out) >= max_stocks:
            break
    return out


def _create_table_if_not_exists(conn: pymysql.connections.Connection, table_name: str) -> None:
    ddl = f"""
    CREATE TABLE IF NOT EXISTS `{table_name}` (
        id BIGINT PRIMARY KEY AUTO_INCREMENT,
        source VARCHAR(64) NOT NULL COMMENT '数据来源标识',
        trade_date DATE NOT NULL COMMENT '计算快照日期',
        industry_code VARCHAR(32) NOT NULL COMMENT '申万三级代码无.SI',
        industry_name VARCHAR(128) NOT NULL COMMENT '申万三级行业名称',
        order_volume_proxy DECIMAL(24, 6) NULL COMMENT '订单量代理=成分合同负债合计',
        value_unit VARCHAR(16) NULL DEFAULT '亿元' COMMENT '与源站解析一致,多为亿元',
        stocks_sampled INT NULL COMMENT '参与加总的成分股数(截断后)',
        stocks_with_contract_liab INT NULL COMMENT '成功解析合同负债的股数',
        calculation_method VARCHAR(64) NOT NULL COMMENT '固定: contract_liab_latest_sum',
        raw_json JSON NOT NULL,
        created_at DATETIME NOT NULL,
        updated_at DATETIME NOT NULL,
        UNIQUE KEY uniq_order_vol (source, trade_date, industry_code)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='行业订单量代理(合同负债合计),见schema计算说明';
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
        order_volume_proxy, value_unit, stocks_sampled, stocks_with_contract_liab,
        calculation_method, raw_json, created_at, updated_at
    )
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, CAST(%s AS JSON), %s, %s)
    ON DUPLICATE KEY UPDATE
        industry_name = VALUES(industry_name),
        order_volume_proxy = VALUES(order_volume_proxy),
        value_unit = VALUES(value_unit),
        stocks_sampled = VALUES(stocks_sampled),
        stocks_with_contract_liab = VALUES(stocks_with_contract_liab),
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
    max_stocks: int,
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
            LOG.warning("成分 %s: %s", code_si, exc)
            continue
        if cons is None or cons.empty:
            continue

        syms = _sample_symbols(cons, max_stocks)
        if not syms:
            continue

        levels: list[float] = []
        for i, sym in enumerate(syms):
            if i > 0 and sleep_seconds > 0:
                time.sleep(sleep_seconds)
            lv = _latest_contract_liab_level(sym)
            if lv is not None:
                levels.append(lv)

        total = float(sum(levels)) if levels else None
        raw = {
            "method": METHOD_KEY,
            "max_stocks": max_stocks,
            "description": "sum(latest 合同负债 per stock), proxy for industry order backlog",
            "stocks": syms[:20],
        }

        rows_out.append(
            (
                SOURCE_THS_CL_SW3,
                run_date,
                code,
                name,
                total,
                "亿元",
                len(syms),
                len(levels),
                METHOD_KEY,
                json.dumps(raw, ensure_ascii=False),
                now,
                now,
            )
        )
        processed += 1

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
        n = _upsert(conn, table_name, rows_out)
    finally:
        conn.close()
    LOG.info("行业订单量代理入库 %s 行", n)
    return n


def _parse_args() -> argparse.Namespace:
    h, p, u, pw, db, tbl = _mysql_defaults()
    parser = argparse.ArgumentParser(description="行业订单量代理(合同负债合计) → MySQL")
    parser.add_argument("--host", default=h)
    parser.add_argument("--port", type=int, default=p)
    parser.add_argument("--user", default=u)
    parser.add_argument("--password", default=pw)
    parser.add_argument("--database", default=db)
    parser.add_argument("--table-name", default=tbl)
    parser.add_argument("--trade-date", default=None, help="快照日期 YYYY-MM-DD")
    parser.add_argument("--max-industries", type=int, default=None)
    parser.add_argument(
        "--max-stocks",
        type=int,
        default=60,
        help="每行业按市值取前 N 只成分股加总; 0 表示不截断(很慢)",
    )
    parser.add_argument("--sleep-seconds", type=float, default=0.12)
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
        trade_date=args.trade_date,
        max_industries=args.max_industries,
        max_stocks=args.max_stocks,
        sleep_seconds=args.sleep_seconds,
    )
    LOG.info("完成 %s 行", n)
