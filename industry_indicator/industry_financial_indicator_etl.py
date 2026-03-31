#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
行业财务衍生指标：营业收入同比增速、毛利率、合同负债同比增速（作 backlog 代理）→ MySQL。

默认数据源（AkShare）：
  - 申万三级行业列表：sw_index_third_info
  - 行业成分与营收同比：sw_index_third_cons（含列「营业收入同比增长(09-30)」等）
  - 毛利率、合同负债：对成分股按市值取前 N 只，拉取同花顺财报摘要/负债表，再行业平均

可选模式 --mode tushare_citic：需 Tushare stock_basic、fina_indicator 等权限，按证监会行业聚合（样本有限）。
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

SOURCE_AK_LEGU = "akshare_legu_sw3"
SOURCE_TS_CITIC = "tushare_citic"
DEFAULT_TABLE = "industry_financial_indicator_di"


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
            getattr(cfg, "INDUSTRY_FINANCIAL_TABLE", DEFAULT_TABLE),
        )
    except Exception:
        return (
            os.getenv("MYSQL_HOST", "localhost"),
            int(os.getenv("MYSQL_PORT", "3306")),
            os.getenv("MYSQL_USER", "root"),
            os.getenv("MYSQL_PASSWORD", ""),
            os.getenv("MYSQL_DATABASE", "stock_data"),
            os.getenv("INDUSTRY_FINANCIAL_TABLE", DEFAULT_TABLE),
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
    if c.startswith(("5", "6", "9")):
        return c
    return c


def _parse_pct_cell(val: object) -> float | None:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    s = str(val).strip().replace("%", "").replace(",", "")
    if s in {"", "-", "--", "nan"}:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _mean_revenue_yoy_from_cons(cons: pd.DataFrame) -> float | None:
    """成分表内营业收入同比增速列（取非空较多的列）。"""
    if cons is None or cons.empty:
        return None
    candidates = [
        c
        for c in cons.columns
        if "营业收入同比" in str(c) or "营业总收入同比" in str(c)
    ]
    if not candidates:
        return None
    best_col, best_n = None, -1
    for c in candidates:
        ser = cons[c].apply(_parse_pct_cell)
        n = ser.notna().sum()
        if n > best_n:
            best_n = n
            best_col = c
    if best_col is None:
        return None
    vals = cons[best_col].apply(_parse_pct_cell).dropna()
    if vals.empty:
        return None
    return float(vals.mean())


def _find_col(df: pd.DataFrame, substr: str) -> str | None:
    for c in df.columns:
        if substr in str(c):
            return str(c)
    return None


def _latest_gross_margin_ths(symbol6: str) -> float | None:
    try:
        df = ak.stock_financial_abstract_ths(symbol=_symbol_for_ths(symbol6), indicator="按报告期")
    except Exception as exc:  # noqa: BLE001
        LOG.debug("abstract %s: %s", symbol6, exc)
        return None
    if df is None or df.empty:
        return None
    col = _find_col(df, "销售毛利率")
    if not col:
        col = _find_col(df, "毛利率")
    if not col:
        return None
    last = df.iloc[-1].get(col)
    return _parse_pct_cell(last)


def _latest_contract_liab_yoy_ths(symbol6: str) -> float | None:
    """合同负债同比增速：最近一期相对上年同期（同月）。"""
    try:
        df = ak.stock_financial_debt_ths(symbol=_symbol_for_ths(symbol6), indicator="按报告期")
    except Exception as exc:  # noqa: BLE001
        LOG.debug("debt %s: %s", symbol6, exc)
        return None
    if df is None or df.empty:
        return None
    date_col = _find_col(df, "报告期") or str(df.columns[0])
    cl_col = _find_col(df, "合同负债")
    if not cl_col:
        return None
    sub = df[[date_col, cl_col]].copy()
    sub["_d"] = pd.to_datetime(sub[date_col], errors="coerce")
    sub = sub.dropna(subset=["_d"]).sort_values("_d")
    if len(sub) < 2:
        return None
    cur = sub.iloc[-1]
    cur_t = cur["_d"]
    target = cur_t - pd.DateOffset(years=1)
    prev_candidates = sub[sub["_d"] <= target]
    if prev_candidates.empty:
        return None
    prev = prev_candidates.iloc[-1]
    v_cur = pd.to_numeric(cur[cl_col], errors="coerce")
    v_prev = pd.to_numeric(prev[cl_col], errors="coerce")
    if pd.isna(v_cur) or pd.isna(v_prev) or abs(float(v_prev)) < 1e-9:
        return None
    return float((float(v_cur) - float(v_prev)) / abs(float(v_prev)) * 100.0)


def _sample_symbols_from_cons(cons: pd.DataFrame, max_n: int) -> list[str]:
    if cons is None or cons.empty:
        return []
    code_col = "股票代码" if "股票代码" in cons.columns else None
    mv_col = "市值" if "市值" in cons.columns else None
    if not code_col:
        return []
    sub = cons.copy()
    if mv_col:
        sub["_mv"] = pd.to_numeric(sub[mv_col], errors="coerce")
        sub = sub.sort_values("_mv", ascending=False)
    syms = []
    for _, r in sub.head(max_n).iterrows():
        c = str(r[code_col]).strip().zfill(6)
        if c.isdigit():
            syms.append(c)
    return syms


def _aggregate_sample_metrics(
    cons: pd.DataFrame,
    max_stocks: int,
    sleep_s: float,
) -> tuple[float | None, float | None, int]:
    syms = _sample_symbols_from_cons(cons, max_stocks)
    gms: list[float] = []
    lys: list[float] = []
    for i, sym in enumerate(syms):
        if i > 0 and sleep_s > 0:
            time.sleep(sleep_s)
        gm = _latest_gross_margin_ths(sym)
        if gm is not None:
            gms.append(gm)
        ly = _latest_contract_liab_yoy_ths(sym)
        if ly is not None:
            lys.append(ly)
    gm_mean = float(sum(gms) / len(gms)) if gms else None
    ly_mean = float(sum(lys) / len(lys)) if lys else None
    return gm_mean, ly_mean, len(syms)


def _create_table_if_not_exists(conn: pymysql.connections.Connection, table_name: str) -> None:
    ddl = f"""
    CREATE TABLE IF NOT EXISTS `{table_name}` (
        id BIGINT PRIMARY KEY AUTO_INCREMENT,
        source VARCHAR(64) NOT NULL COMMENT '数据来源',
        report_period DATE NULL COMMENT '财报期(成分表同比口径快照;可空)',
        industry_name VARCHAR(128) NOT NULL COMMENT '行业名称',
        industry_code VARCHAR(32) NULL COMMENT '行业代码(申万三级等,无后缀)',
        revenue_yoy_pct DECIMAL(20, 6) NULL COMMENT '收入增速(百分比口径):成分表最佳同比列全成分算术平均,见schema逻辑说明块',
        gross_margin_pct DECIMAL(20, 6) NULL COMMENT '毛利率(百分比口径):市值前N股THS摘要最近期销售毛利率算术平均,见schema',
        backlog_yoy_pct DECIMAL(20, 6) NULL COMMENT 'backlog代理(百分比口径):市值前N股合同负债同比增速算术平均,见schema',
        sample_stocks INT NULL COMMENT '毛利率与backlog所用的市值前N成分股数',
        raw_json JSON NOT NULL,
        created_at DATETIME NOT NULL,
        updated_at DATETIME NOT NULL,
        UNIQUE KEY uniq_ind_fin (source, industry_name)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='行业财务衍生指标,计算逻辑见 industry_indicator/schema.sql 注释块';
    """
    with conn.cursor() as cur:
        cur.execute(ddl)
    conn.commit()


def _upsert_rows(
    conn: pymysql.connections.Connection,
    table_name: str,
    rows: list[tuple[Any, ...]],
) -> int:
    if not rows:
        return 0
    sql = f"""
    INSERT INTO `{table_name}` (
        source, report_period, industry_name, industry_code,
        revenue_yoy_pct, gross_margin_pct, backlog_yoy_pct, sample_stocks,
        raw_json, created_at, updated_at
    )
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, CAST(%s AS JSON), %s, %s)
    ON DUPLICATE KEY UPDATE
        report_period = VALUES(report_period),
        revenue_yoy_pct = VALUES(revenue_yoy_pct),
        gross_margin_pct = VALUES(gross_margin_pct),
        backlog_yoy_pct = VALUES(backlog_yoy_pct),
        sample_stocks = VALUES(sample_stocks),
        raw_json = VALUES(raw_json),
        updated_at = VALUES(updated_at);
    """
    with conn.cursor() as cur:
        cur.executemany(sql, rows)
    conn.commit()
    return len(rows)


def run_legu_sw3(
    host: str,
    port: int,
    user: str,
    password: str,
    database: str,
    table_name: str,
    max_industries: int | None,
    max_stocks_per_industry: int,
    sleep_seconds: float,
    cons_sleep: float,
) -> int:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    report_period: datetime | None = None

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
            LOG.warning("成分 %s %s: %s", code_si, name, exc)
            continue
        if cons is None or cons.empty:
            continue

        rev_yoy = _mean_revenue_yoy_from_cons(cons)
        gm, bl_yoy, sample_n = _aggregate_sample_metrics(
            cons, max_stocks_per_industry, cons_sleep
        )

        raw = {
            "industry_code_si": code_si,
            "industry_code": code,
            "cons_columns": [str(c) for c in cons.columns],
            "revenue_yoy_mean": rev_yoy,
            "gross_margin_sample_mean": gm,
            "contract_liab_yoy_sample_mean": bl_yoy,
            "max_stocks_per_industry": max_stocks_per_industry,
        }

        rows_out.append(
            (
                SOURCE_AK_LEGU,
                report_period,
                name,
                code,
                rev_yoy,
                gm,
                bl_yoy,
                sample_n,
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
        cnt = _upsert_rows(conn, table_name, rows_out)
    finally:
        conn.close()
    LOG.info("申万三级行业财务指标入库 %s 行", cnt)
    return cnt


def run_tushare_citic(
    host: str,
    port: int,
    user: str,
    password: str,
    database: str,
    table_name: str,
) -> int:
    """证监会行业聚合（需 fina_indicator、balancesheet 权限）。"""
    try:
        cfg = _load_config()
        import tushare as ts  # noqa: PLC0415

        pro = ts.pro_api(cfg.get_token())
    except Exception as exc:  # noqa: BLE001
        LOG.error("Tushare 不可用: %s", exc)
        return 0

    try:
        basic = pro.stock_basic(
            exchange="",
            list_status="L",
            fields="ts_code,name,industry",
        )
    except Exception as exc:  # noqa: BLE001
        LOG.error("stock_basic 失败: %s", exc)
        return 0

    if basic is None or basic.empty:
        return 0

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    rows_out: list[tuple[Any, ...]] = []

    for ind, g in basic.groupby("industry"):
        if ind is None or str(ind).strip() == "":
            continue
        codes = g["ts_code"].tolist()
        or_yoys: list[float] = []
        gms: list[float] = []
        for ts_code in codes[:80]:
            time.sleep(0.12)
            try:
                fi = pro.fina_indicator(ts_code=ts_code, limit=1)
            except Exception:  # noqa: BLE001
                continue
            if fi is None or fi.empty:
                continue
            r = fi.iloc[0]
            if pd.notna(r.get("or_yoy")):
                or_yoys.append(float(r["or_yoy"]))
            if pd.notna(r.get("grossprofit_margin")):
                gms.append(float(r["grossprofit_margin"]))
        rev_m = float(sum(or_yoys) / len(or_yoys)) if or_yoys else None
        gm_m = float(sum(gms) / len(gms)) if gms else None
        raw = {"ts_codes_sampled": min(len(codes), 80)}
        rows_out.append(
            (
                SOURCE_TS_CITIC,
                None,
                str(ind).strip(),
                None,
                rev_m,
                gm_m,
                None,
                min(len(codes), 80),
                json.dumps(raw, ensure_ascii=False),
                now,
                now,
            )
        )

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
        cnt = _upsert_rows(conn, table_name, rows_out)
    finally:
        conn.close()
    LOG.info("证监会行业(Tushare)入库 %s 行", cnt)
    return cnt


def run(
    host: str,
    port: int,
    user: str,
    password: str,
    database: str,
    table_name: str,
    mode: str,
    max_industries: int | None,
    max_stocks_per_industry: int,
    sleep_seconds: float,
    cons_sleep: float,
) -> int:
    if mode == "tushare_citic":
        return run_tushare_citic(host, port, user, password, database, table_name)
    return run_legu_sw3(
        host,
        port,
        user,
        password,
        database,
        table_name,
        max_industries,
        max_stocks_per_industry,
        sleep_seconds,
        cons_sleep,
    )


def _parse_args() -> argparse.Namespace:
    h, p, u, pw, db, tbl = _mysql_defaults()
    parser = argparse.ArgumentParser(description="行业营收增速/毛利率/合同负债增速 → MySQL")
    parser.add_argument("--host", default=h)
    parser.add_argument("--port", type=int, default=p)
    parser.add_argument("--user", default=u)
    parser.add_argument("--password", default=pw)
    parser.add_argument("--database", default=db)
    parser.add_argument("--table-name", default=tbl)
    parser.add_argument(
        "--mode",
        choices=["legu_sw3", "tushare_citic"],
        default="legu_sw3",
        help="legu_sw3: 申万三级+AkShare(默认); tushare_citic: 证监会行业+Tushare(需权限)",
    )
    parser.add_argument(
        "--max-industries",
        type=int,
        default=None,
        help="仅处理前 N 个申万三级行业(调试); 默认全部",
    )
    parser.add_argument(
        "--max-stocks-per-industry",
        type=int,
        default=3,
        help="毛利率/合同负债增速时每个行业按市值取前 N 只成分股做样本",
    )
    parser.add_argument("--sleep-seconds", type=float, default=0.15, help="行业之间的间隔秒")
    parser.add_argument(
        "--cons-sleep",
        type=float,
        default=0.2,
        help="同一行业内拉取 THS 财报时的间隔秒",
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
        mode=args.mode,
        max_industries=args.max_industries,
        max_stocks_per_industry=args.max_stocks_per_industry,
        sleep_seconds=args.sleep_seconds,
        cons_sleep=args.cons_sleep,
    )
    LOG.info("完成，写入/更新约 %s 行", n)
