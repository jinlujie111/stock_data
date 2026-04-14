#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
全 A 股财务数据入库（2020 年以来报告期维度）。

数据源（按 --source）：
  - tushare：stock_basic + fina_indicator（需 Tushare 积分/权限，见 pro 文档）
  - akshare_em：东方财富 datacenter 主要指标 + 可选三大表（按股票逐只请求，较慢）
  - auto：先尝试 tushare 单股探测，无权限则走 akshare_em

表结构与说明见同目录 schema.sql。
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable

import pandas as pd
import pymysql

LOG = logging.getLogger(__name__)

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent
if str(_ROOT / "industry_indicator") not in sys.path:
    sys.path.insert(0, str(_ROOT / "industry_indicator"))

import config as cfg  # noqa: E402

DEFAULT_TABLE = "stock_financial_report_di"


def _mysql_defaults() -> tuple[str, int, str, str, str, str]:
    return (
        cfg.MYSQL_HOST,
        cfg.MYSQL_PORT,
        cfg.MYSQL_USER,
        cfg.MYSQL_PASSWORD,
        cfg.MYSQL_DATABASE,
        getattr(cfg, "STOCK_FINANCIAL_REPORT_TABLE", DEFAULT_TABLE),
    )


def ts_code_to_em_h10(ts_code: str) -> str:
    """600519.SH -> SH600519（东方财富 H10 部分接口）。"""
    parts = ts_code.strip().upper().split(".")
    if len(parts) != 2:
        return ""
    code, mkt = parts[0].zfill(6), parts[1]
    return f"{mkt}{code}"


def _parse_report_date(val: object) -> date | None:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    if isinstance(val, date) and not isinstance(val, datetime):
        return val
    if isinstance(val, datetime):
        return val.date()
    if isinstance(val, (int, float)) and not pd.isna(val):
        s = str(int(val))
        if len(s) == 8 and s.isdigit():
            try:
                return datetime.strptime(s, "%Y%m%d").date()
            except ValueError:
                pass
    s = str(val).strip()
    if not s:
        return None
    if s.isdigit() and len(s) == 8:
        try:
            return datetime.strptime(s, "%Y%m%d").date()
        except ValueError:
            pass
    for fmt in ("%Y-%m-%d", "%Y%m%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(s[:10].replace("/", "-"), "%Y-%m-%d").date()
        except ValueError:
            continue
    try:
        ts = pd.to_datetime(s, errors="coerce")
        if pd.notna(ts):
            return ts.date()
    except Exception:  # noqa: BLE001
        pass
    return None


def _df_filter_since(df: pd.DataFrame, col: str, since: date) -> pd.DataFrame:
    if df is None or df.empty or col not in df.columns:
        return df
    out = []
    for _, row in df.iterrows():
        rd = _parse_report_date(row[col])
        if rd is not None and rd >= since:
            out.append(row)
    return pd.DataFrame(out) if out else pd.DataFrame()


def _serialize_row(row: pd.Series) -> dict[str, Any]:
    d: dict[str, Any] = {}
    for k, v in row.items():
        if pd.isna(v):
            d[str(k)] = None
        elif isinstance(v, (pd.Timestamp, datetime)):
            d[str(k)] = v.strftime("%Y-%m-%d %H:%M:%S") if hasattr(v, "hour") else str(v.date())
        elif isinstance(v, date):
            d[str(k)] = v.isoformat()
        elif isinstance(v, (int, float, str, bool)):
            d[str(k)] = v
        else:
            d[str(k)] = str(v)
    return d


def _retry(
    fn: Callable[[], Any],
    attempts: int = 3,
    base_sleep: float = 1.0,
) -> Any:
    last: Exception | None = None
    for i in range(attempts):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001
            last = exc
            if i < attempts - 1:
                time.sleep(base_sleep * (i + 1))
    if last:
        raise last
    return None


def load_universe_tushare() -> pd.DataFrame:
    import tushare as ts  # noqa: PLC0415

    pro = ts.pro_api(cfg.get_token())
    df = pro.stock_basic(
        exchange="",
        list_status="L",
        fields="ts_code,symbol,name",
    )
    if df is None or df.empty:
        raise RuntimeError("stock_basic 为空")
    return df


def load_universe_akshare() -> pd.DataFrame:
    import akshare as ak  # noqa: PLC0415

    df = ak.stock_info_a_code_name()
    if df is None or df.empty:
        raise RuntimeError("stock_info_a_code_name 为空")
    rows = []
    for _, r in df.iterrows():
        code = str(r["code"]).zfill(6)
        name = str(r.get("name", "") or "")
        ts = _code6_guess_ts(code)
        if ts:
            rows.append({"ts_code": ts, "symbol": code, "name": name})
    return pd.DataFrame(rows)


def _code6_guess_ts(code6: str) -> str | None:
    c = str(code6).strip().zfill(6)
    if not c.isdigit():
        return None
    p3, p2, d1 = c[:3], c[:2], c[0]
    if p3 in ("688", "689"):
        return f"{c}.SH"
    if p2 == "60" or p2 == "68":
        return f"{c}.SH"
    if d1 == "6":
        return f"{c}.SH"
    if d1 in ("0", "1", "2", "3"):
        return f"{c}.SZ"
    if p2 in ("43", "83", "87", "88", "92"):
        return f"{c}.BJ"
    if d1 in ("4", "8"):
        return f"{c}.BJ"
    if d1 == "9":
        return f"{c}.SH"
    return f"{c}.SZ"


def _probe_tushare_fina(pro: Any, ts_code: str, start: str) -> bool:
    try:
        pro.fina_indicator(ts_code=ts_code, start_date=start)
        return True
    except Exception as exc:  # noqa: BLE001
        s = str(exc)
        if "权限" in s or "积分" in s or "permission" in s.lower():
            return False
        LOG.warning("fina_indicator 探测非权限错误，仍走 Tushare: %s", exc)
        return True


def fetch_tushare_fina(
    pro: Any,
    ts_code: str,
    start: str,
) -> pd.DataFrame | None:
    try:
        df = pro.fina_indicator(ts_code=ts_code, start_date=start)
        return df
    except Exception as exc:  # noqa: BLE001
        LOG.debug("fina_indicator %s: %s", ts_code, exc)
        return None


def fetch_akshare_main(ts_code: str, timeout: float) -> pd.DataFrame | None:
    import akshare as ak  # noqa: PLC0415

    def _call() -> pd.DataFrame:
        return ak.stock_financial_analysis_indicator_em(
            symbol=ts_code,
            indicator="按报告期",
        )

    try:
        return _retry(lambda: _call(), attempts=3, base_sleep=2.0)
    except Exception as exc:  # noqa: BLE001
        LOG.debug("em main %s: %s", ts_code, exc)
        return None


def fetch_akshare_statement(
    fn: Callable[..., pd.DataFrame],
    em_symbol: str,
    timeout: float,
) -> pd.DataFrame | None:
    try:
        return _retry(lambda: fn(symbol=em_symbol), attempts=2, base_sleep=3.0)
    except Exception as exc:  # noqa: BLE001
        LOG.debug("em statement %s: %s", em_symbol, exc)
        return None


def _report_col(df: pd.DataFrame) -> str | None:
    for c in df.columns:
        cs = str(c).upper()
        if cs in ("REPORT_DATE", "END_DATE", "报告期"):
            return str(c)
    return None


def _create_table_if_not_exists(conn: pymysql.connections.Connection, table_name: str) -> None:
    """使用 mysql_tables/schema.sql 中定义的表结构"""
    ddl = f"""
    CREATE TABLE IF NOT EXISTS `{table_name}` (
        id BIGINT PRIMARY KEY AUTO_INCREMENT,
        source VARCHAR(64) NOT NULL COMMENT '数据源标识,见本文件说明块',
        ts_code VARCHAR(16) NOT NULL COMMENT 'Tushare 风格代码如 600519.SH',
        stock_name VARCHAR(128) NULL,
        report_date DATE NOT NULL COMMENT '报告期截止日',
        data_kind VARCHAR(48) NOT NULL COMMENT 'fina_indicator/main_indicator/三大表等',
        raw_json JSON NOT NULL COMMENT '该期接口返回行序列化',
        created_at DATETIME NOT NULL,
        updated_at DATETIME NOT NULL,
        UNIQUE KEY uniq_sfr (source, ts_code, report_date, data_kind)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='A股财务多源明细';
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
        source, ts_code, stock_name, report_date, data_kind, raw_json, created_at, updated_at
    ) VALUES (%s, %s, %s, %s, %s, CAST(%s AS JSON), %s, %s)
    ON DUPLICATE KEY UPDATE
        stock_name = VALUES(stock_name),
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
    start_date: date,
    source_mode: str,
    max_stocks: int | None,
    sleep_seconds: float,
    include_statements: bool,
    request_timeout: float,
) -> int:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    start_str = start_date.strftime("%Y%m%d")

    try:
        universe = load_universe_tushare()
    except Exception as exc:  # noqa: BLE001
        LOG.warning("Tushare stock_basic 不可用，改用 AkShare 证券列表: %s", exc)
        universe = load_universe_akshare()
    if max_stocks is not None:
        universe = universe.head(max_stocks)

    pro = None
    if source_mode == "tushare":
        use_tushare, use_ak = True, False
    elif source_mode == "akshare_em":
        use_tushare, use_ak = False, True
    else:
        import tushare as ts  # noqa: PLC0415

        pro = ts.pro_api(cfg.get_token())
        probe_ts = str(universe.iloc[0]["ts_code"])
        use_tushare = _probe_tushare_fina(pro, probe_ts, start_str)
        use_ak = not use_tushare
        LOG.info(
            "auto 模式: %s",
            "使用 Tushare fina_indicator" if use_tushare else "无 fina_indicator 权限，使用 AkShare 东方财富",
        )

    if use_tushare:
        import tushare as ts  # noqa: PLC0415

        pro = pro or ts.pro_api(cfg.get_token())

    total_rows = 0
    batch: list[tuple[Any, ...]] = []
    batch_size = 200

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

        if include_statements and use_tushare and not use_ak:
            LOG.warning(
                "--include-statements 仅在 AkShare 路径下生效；当前为 Tushare，已忽略",
            )
            include_statements = False

        ak = None
        if use_ak:
            import akshare as ak  # noqa: PLC0415

        for ni, (_, row) in enumerate(universe.iterrows()):
            ts_code = str(row["ts_code"]).strip()
            name = str(row.get("name", "") or "")

            if use_tushare and pro is not None:
                df = fetch_tushare_fina(pro, ts_code, start_str)
                if df is not None and not df.empty and "end_date" in df.columns:
                    for _, r in df.iterrows():
                        rd = _parse_report_date(r.get("end_date"))
                        if rd is None or rd < start_date:
                            continue
                        src = "tushare_fina_indicator"
                        dk = "fina_indicator"
                        payload = _serialize_row(r)
                        batch.append(
                            (
                                src,
                                ts_code,
                                name,
                                rd,
                                dk,
                                json.dumps(payload, ensure_ascii=False),
                                now,
                                now,
                            )
                        )
                        if len(batch) >= batch_size:
                            total_rows += _upsert(conn, table_name, batch)
                            batch = []

            if use_ak and ak is not None:
                main_df = fetch_akshare_main(ts_code, request_timeout)
                rcol = _report_col(main_df) if main_df is not None else None
                if main_df is not None and rcol:
                    main_df = _df_filter_since(main_df, rcol, start_date)
                    for _, r in main_df.iterrows():
                        rd = _parse_report_date(r.get(rcol))
                        if rd is None:
                            continue
                        batch.append(
                            (
                                "akshare_em_main",
                                ts_code,
                                name,
                                rd,
                                "main_indicator",
                                json.dumps(_serialize_row(r), ensure_ascii=False),
                                now,
                                now,
                            )
                        )
                        if len(batch) >= batch_size:
                            total_rows += _upsert(conn, table_name, batch)
                            batch = []

                if include_statements:
                    em = ts_code_to_em_h10(ts_code)
                    if em:
                        pairs = [
                            (
                                "akshare_em_balance",
                                "balance_sheet",
                                ak.stock_balance_sheet_by_report_em,
                            ),
                            (
                                "akshare_em_profit",
                                "profit_sheet",
                                ak.stock_profit_sheet_by_report_em,
                            ),
                            (
                                "akshare_em_cashflow",
                                "cash_flow",
                                ak.stock_cash_flow_sheet_by_report_em,
                            ),
                        ]
                        for src, dk, fn in pairs:
                            stmt_df = fetch_akshare_statement(fn, em, request_timeout)
                            scol = _report_col(stmt_df) if stmt_df is not None else None
                            if stmt_df is None or not scol:
                                continue
                            stmt_df = _df_filter_since(stmt_df, scol, start_date)
                            for _, r in stmt_df.iterrows():
                                rd = _parse_report_date(r.get(scol))
                                if rd is None:
                                    continue
                                batch.append(
                                    (
                                        src,
                                        ts_code,
                                        name,
                                        rd,
                                        dk,
                                        json.dumps(
                                            _serialize_row(r),
                                            ensure_ascii=False,
                                        ),
                                        now,
                                        now,
                                    )
                                )
                                if len(batch) >= batch_size:
                                    total_rows += _upsert(conn, table_name, batch)
                                    batch = []

            if (ni + 1) % 200 == 0:
                LOG.info("进度 %s/%s", ni + 1, len(universe))
            if sleep_seconds > 0:
                time.sleep(sleep_seconds)

        if batch:
            total_rows += _upsert(conn, table_name, batch)
    finally:
        conn.close()

    LOG.info("完成写入约 %s 行（含更新）", total_rows)
    return total_rows


def _parse_args() -> argparse.Namespace:
    h, p, u, pw, db, tbl = _mysql_defaults()
    parser = argparse.ArgumentParser(
        description="全市场股票财务数据入库（2020 年起，MySQL）",
    )
    parser.add_argument("--host", default=h)
    parser.add_argument("--port", type=int, default=p)
    parser.add_argument("--user", default=u)
    parser.add_argument("--password", default=pw)
    parser.add_argument("--database", default=db)
    parser.add_argument("--table-name", default=tbl)
    parser.add_argument(
        "--start-date",
        default="2020-01-01",
        help="报告期起始（含），默认 2020-01-01",
    )
    parser.add_argument(
        "--source",
        choices=("auto", "tushare", "akshare_em"),
        default="auto",
        help="auto：探测 Tushare fina_indicator 权限；无则东方财富",
    )
    parser.add_argument("--max-stocks", type=int, default=None, help="仅调试用，限制股票数量")
    parser.add_argument(
        "--sleep-seconds",
        type=float,
        default=0.12,
        help="每只股票请求间隔，降频防封",
    )
    parser.add_argument(
        "--include-statements",
        action="store_true",
        help="额外拉取资产负债/利润/现金流三大表（东方财富，极慢）",
    )
    parser.add_argument("--request-timeout", type=float, default=60.0)
    return parser.parse_args()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    args = _parse_args()
    sd = datetime.strptime(args.start_date, "%Y-%m-%d").date()
    n = run(
        host=args.host,
        port=args.port,
        user=args.user,
        password=args.password,
        database=args.database,
        table_name=args.table_name,
        start_date=sd,
        source_mode=args.source,
        max_stocks=args.max_stocks,
        sleep_seconds=args.sleep_seconds,
        include_statements=args.include_statements,
        request_timeout=args.request_timeout,
    )
    raise SystemExit(0 if n >= 0 else 1)
