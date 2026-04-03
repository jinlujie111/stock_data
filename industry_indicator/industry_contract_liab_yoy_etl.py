#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
行业合同负债同比增速入库。

计算方法见 industry_indicator/schema.sql 中 industry_contract_liab_yoy_di 注释块。
与「订单量」关系：合同负债反映未履约义务/订单蓄水，其同比增速刻画行业层面订单池的扩张或收缩（代理指标）。
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

SOURCE_THS_YOY_SW3 = "ths_contract_liab_yoy_sw3"
DEFAULT_TABLE = "industry_contract_liab_yoy_di"


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
            getattr(cfg, "INDUSTRY_CONTRACT_LIAB_YOY_TABLE", DEFAULT_TABLE),
        )
    except Exception:
        return (
            os.getenv("MYSQL_HOST", "localhost"),
            int(os.getenv("MYSQL_PORT", "3306")),
            os.getenv("MYSQL_USER", "root"),
            os.getenv("MYSQL_PASSWORD", ""),
            os.getenv("MYSQL_DATABASE", "stock_data"),
            os.getenv("INDUSTRY_CONTRACT_LIAB_YOY_TABLE", DEFAULT_TABLE),
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
    return str(code6).strip().zfill(6)


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


def _contract_liab_yoy_detail(
    symbol6: str,
) -> tuple[float | None, float | None, float | None]:
    """
    单股合同负债同比增速(%)及当期、同比基期余额。
    最近一期相对「不晚于当期日期减 1 年」区间内最后一期。
    """
    try:
        df = ak.stock_financial_debt_ths(symbol=_symbol_for_ths(symbol6), indicator="按报告期")
    except Exception as exc:  # noqa: BLE001
        LOG.debug("debt %s: %s", symbol6, exc)
        return None, None, None
    if df is None or df.empty:
        return None, None, None
    date_col = _find_col(df, "报告期") or str(df.columns[0])
    cl_col = _find_col(df, "合同负债")
    if not cl_col:
        return None, None, None
    sub = df[[date_col, cl_col]].copy()
    sub["_d"] = pd.to_datetime(sub[date_col], errors="coerce")
    sub = sub.dropna(subset=["_d"]).sort_values("_d")
    if len(sub) < 2:
        return None, None, None
    cur_row = sub.iloc[-1]
    cur_t = cur_row["_d"]
    target = cur_t - pd.DateOffset(years=1)
    prev_candidates = sub[sub["_d"] <= target]
    if prev_candidates.empty:
        return None, None, None
    prev_row = prev_candidates.iloc[-1]
    v_cur = _parse_contract_liab_cell(cur_row[cl_col])
    v_prev = _parse_contract_liab_cell(prev_row[cl_col])
    if v_cur is None or v_prev is None or abs(v_prev) < 1e-9:
        return None, v_cur, v_prev
    yoy = (v_cur - v_prev) / abs(v_prev) * 100.0
    return float(yoy), v_cur, v_prev


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
        source VARCHAR(64) NOT NULL,
        trade_date DATE NOT NULL COMMENT '计算快照日期',
        industry_code VARCHAR(32) NOT NULL,
        industry_name VARCHAR(128) NOT NULL,
        cl_yoy_mean_pct DECIMAL(20, 6) NULL COMMENT '成分股同比增速算术平均%%',
        cl_yoy_aggregate_pct DECIMAL(20, 6) NULL COMMENT '成分合同负债加总后的整体同比%%',
        value_unit VARCHAR(16) NULL DEFAULT '百分比' COMMENT '口径',
        stocks_sampled INT NULL,
        stocks_with_yoy INT NULL,
        calculation_method VARCHAR(128) NOT NULL,
        raw_json JSON NOT NULL,
        created_at DATETIME NOT NULL,
        updated_at DATETIME NOT NULL,
        UNIQUE KEY uniq_cl_yoy (source, trade_date, industry_code)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='行业合同负债同比增速,见schema计算说明';
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
        cl_yoy_mean_pct, cl_yoy_aggregate_pct, value_unit,
        stocks_sampled, stocks_with_yoy, calculation_method, raw_json,
        created_at, updated_at
    )
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, CAST(%s AS JSON), %s, %s)
    ON DUPLICATE KEY UPDATE
        industry_name = VALUES(industry_name),
        cl_yoy_mean_pct = VALUES(cl_yoy_mean_pct),
        cl_yoy_aggregate_pct = VALUES(cl_yoy_aggregate_pct),
        value_unit = VALUES(value_unit),
        stocks_sampled = VALUES(stocks_sampled),
        stocks_with_yoy = VALUES(stocks_with_yoy),
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
    method = "mean_yoy_and_aggregate_yoy_from_ths_debt"

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

        yoys: list[float] = []
        sum_cur = 0.0
        sum_prev = 0.0
        n_agg = 0
        for i, sym in enumerate(syms):
            if i > 0 and sleep_seconds > 0:
                time.sleep(sleep_seconds)
            yoy, vcur, vprev = _contract_liab_yoy_detail(sym)
            if yoy is not None:
                yoys.append(yoy)
            if vcur is not None and vprev is not None and abs(vprev) > 1e-12:
                sum_cur += vcur
                sum_prev += vprev
                n_agg += 1

        mean_yoy = float(sum(yoys) / len(yoys)) if yoys else None
        agg_yoy = None
        if n_agg > 0 and abs(sum_prev) > 1e-9:
            agg_yoy = float((sum_cur - sum_prev) / abs(sum_prev) * 100.0)

        raw = {
            "method": method,
            "max_stocks": max_stocks,
            "sum_cur": sum_cur,
            "sum_prev": sum_prev,
            "n_for_aggregate": n_agg,
            "n_yoy": len(yoys),
        }

        rows_out.append(
            (
                SOURCE_THS_YOY_SW3,
                run_date,
                code,
                name,
                mean_yoy,
                agg_yoy,
                "百分比",
                len(syms),
                len(yoys),
                method,
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
    LOG.info("行业合同负债同比增速入库 %s 行", n)
    return n


def _parse_args() -> argparse.Namespace:
    h, p, u, pw, db, tbl = _mysql_defaults()
    parser = argparse.ArgumentParser(description="行业合同负债同比增速 → MySQL")
    parser.add_argument("--host", default=h)
    parser.add_argument("--port", type=int, default=p)
    parser.add_argument("--user", default=u)
    parser.add_argument("--password", default=pw)
    parser.add_argument("--database", default=db)
    parser.add_argument("--table-name", default=tbl)
    parser.add_argument("--trade-date", default=None)
    parser.add_argument("--max-industries", type=int, default=None)
    parser.add_argument("--max-stocks", type=int, default=60)
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
