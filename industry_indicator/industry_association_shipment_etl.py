#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
行业协会口径「出货」同比增速入库（乘联会乘用车总量市场）。

计算方法见 industry_indicator/schema.sql 中 industry_association_shipment_di 注释块。
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pymysql
import requests

LOG = logging.getLogger(__name__)

SOURCE_CPCA_CHART1 = "cpca_total_market_chartlist_1"
METHOD_KEY = "cpca_api_yoy_total_market_four_metrics"
DEFAULT_TABLE = "industry_association_shipment_di"

# 接口返回四维数组顺序（与 AkShare car_market_total_cpca 一致）：批发、零售、出口、进口
METRICS: list[tuple[str, str, int]] = [
    ("wholesale", "批发", 0),
    ("retail", "零售", 1),
    ("export", "出口", 2),
    ("import", "进口", 3),
]

MARKET_SCOPES: list[tuple[str, str, int]] = [
    ("narrow_passenger", "狭义乘用车", 0),
    ("broad_passenger", "广义乘用车", 1),
]

CPCA_CHARTLIST_URL = "http://data.cpcadata.com/api/chartlist"


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
            getattr(cfg, "INDUSTRY_ASSOCIATION_SHIPMENT_TABLE", DEFAULT_TABLE),
        )
    except Exception:
        return (
            os.getenv("MYSQL_HOST", "localhost"),
            int(os.getenv("MYSQL_PORT", "3306")),
            os.getenv("MYSQL_USER", "root"),
            os.getenv("MYSQL_PASSWORD", ""),
            os.getenv("MYSQL_DATABASE", "stock_data"),
            os.getenv("INDUSTRY_ASSOCIATION_SHIPMENT_TABLE", DEFAULT_TABLE),
        )


def _year_keys(item: dict[str, Any]) -> list[str]:
    ys: list[str] = []
    for k in item:
        if isinstance(k, str) and len(k) == 5 and k.endswith("年"):
            p = k[:-1]
            if p.isdigit() and len(p) == 4:
                ys.append(k)
    return sorted(ys, reverse=True)


def _yoy_key(item: dict[str, Any]) -> str | None:
    if "同比" in item:
        return "同比"
    for k in item:
        if isinstance(k, str) and k.endswith("同比"):
            return k
    return None


def _month_num(month_label: object) -> int | None:
    s = str(month_label).strip()
    m = re.match(r"^(\d{1,2})月$", s)
    if m:
        return int(m.group(1))
    return None


def _stat_month(year: int, month_label: object) -> date | None:
    mn = _month_num(month_label)
    if mn is None or not (1 <= mn <= 12):
        return None
    return date(year, mn, 1)


def _float_at(seq: object, idx: int) -> float | None:
    if seq is None:
        return None
    if not isinstance(seq, (list, tuple)):
        return None
    if idx >= len(seq):
        return None
    v = seq[idx]
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _yoy_from_volumes(cur: float | None, prev: float | None) -> float | None:
    if cur is None or prev is None:
        return None
    if abs(prev) < 1e-12:
        return None
    return float((cur - prev) / abs(prev) * 100.0)


def fetch_cpca_chartlist_total_market(timeout: float = 30.0) -> list[dict[str, Any]]:
    r = requests.get(
        CPCA_CHARTLIST_URL,
        params={"charttype": "1"},
        timeout=timeout,
    )
    r.raise_for_status()
    data = r.json()
    if not isinstance(data, list):
        raise ValueError("chartlist 返回非列表")
    return data


def _rows_from_payload(
    payload: list[dict[str, Any]],
    run_date: str,
    now: str,
) -> list[tuple[Any, ...]]:
    rows: list[tuple[Any, ...]] = []
    for scope_code, scope_name, scope_idx in MARKET_SCOPES:
        if scope_idx >= len(payload):
            continue
        block = payload[scope_idx]
        data_list = block.get("dataList")
        if not isinstance(data_list, list):
            continue
        for item in data_list:
            if not isinstance(item, dict):
                continue
            yks = _year_keys(item)
            if len(yks) < 2:
                continue
            cur_yk, prev_yk = yks[0], yks[1]
            try:
                cur_year = int(str(cur_yk)[:4])
            except ValueError:
                continue
            sm = _stat_month(cur_year, item.get("month"))
            if sm is None:
                continue
            yoy_key = _yoy_key(item)
            yoy_raw = item.get(yoy_key) if yoy_key else None
            cur_list = item.get(cur_yk)
            prev_list = item.get(prev_yk)

            for mcode, mzh, mi in METRICS:
                yoy_api = _float_at(yoy_raw, mi)
                v_cur = _float_at(cur_list, mi)
                v_prev = _float_at(prev_list, mi)
                yoy_final = yoy_api
                if yoy_final is None:
                    yoy_final = _yoy_from_volumes(v_cur, v_prev)

                ind_code = f"CPCA_{scope_code.upper()}_{mcode.upper()}"
                ind_name = f"乘联会-{scope_name}-{mzh}"

                raw = {
                    "method": METHOD_KEY,
                    "market_scope": scope_code,
                    "metric": mcode,
                    "stat_month": sm.isoformat(),
                    "yoy_from_api": yoy_api,
                    "volume_current": v_cur,
                    "volume_prev_year": v_prev,
                    "year_keys": yks,
                }
                rows.append(
                    (
                        SOURCE_CPCA_CHART1,
                        run_date,
                        sm,
                        scope_code,
                        mcode,
                        ind_code,
                        ind_name,
                        yoy_final,
                        v_cur,
                        v_prev,
                        "万辆",
                        METHOD_KEY,
                        json.dumps(raw, ensure_ascii=False),
                        now,
                        now,
                    )
                )
    return rows


def _create_table_if_not_exists(conn: pymysql.connections.Connection, table_name: str) -> None:
    ddl = f"""
    CREATE TABLE IF NOT EXISTS `{table_name}` (
        id BIGINT PRIMARY KEY AUTO_INCREMENT,
        source VARCHAR(64) NOT NULL,
        trade_date DATE NOT NULL COMMENT '入库快照日',
        stat_month DATE NOT NULL COMMENT '统计月(乘联会月度口径)',
        market_scope VARCHAR(32) NOT NULL COMMENT 'narrow_passenger/broad_passenger',
        metric_type VARCHAR(32) NOT NULL COMMENT 'wholesale/retail/export/import',
        industry_code VARCHAR(64) NOT NULL COMMENT '稳定编码,见schema',
        industry_name VARCHAR(128) NOT NULL COMMENT '展示名称',
        shipment_yoy_pct DECIMAL(20, 6) NULL COMMENT '同比增速%%,见schema',
        volume_current DECIMAL(20, 6) NULL COMMENT '当期量(万辆)',
        volume_prev_year DECIMAL(20, 6) NULL COMMENT '去年同期量(万辆)',
        value_unit VARCHAR(16) NULL DEFAULT '万辆',
        calculation_method VARCHAR(128) NOT NULL,
        raw_json JSON NOT NULL,
        created_at DATETIME NOT NULL,
        updated_at DATETIME NOT NULL,
        UNIQUE KEY uniq_assoc_ship (source, stat_month, market_scope, metric_type)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='行业协会出货增速(乘联会),见schema';
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
        source, trade_date, stat_month, market_scope, metric_type,
        industry_code, industry_name, shipment_yoy_pct,
        volume_current, volume_prev_year, value_unit,
        calculation_method, raw_json, created_at, updated_at
    )
    VALUES (
        %s, %s, %s, %s, %s,
        %s, %s, %s,
        %s, %s, %s,
        %s, CAST(%s AS JSON), %s, %s
    )
    ON DUPLICATE KEY UPDATE
        trade_date = VALUES(trade_date),
        industry_code = VALUES(industry_code),
        industry_name = VALUES(industry_name),
        shipment_yoy_pct = VALUES(shipment_yoy_pct),
        volume_current = VALUES(volume_current),
        volume_prev_year = VALUES(volume_prev_year),
        value_unit = VALUES(value_unit),
        calculation_method = VALUES(calculation_method),
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
    request_timeout: float,
) -> int:
    run_date = trade_date or datetime.now().strftime("%Y-%m-%d")
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    payload = fetch_cpca_chartlist_total_market(timeout=request_timeout)
    rows_out = _rows_from_payload(payload, run_date, now)

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
    LOG.info("行业协会出货增速入库 %s 行 trade_date=%s", n, run_date)
    return n


def _parse_args() -> argparse.Namespace:
    h, p, u, pw, db, tbl = _mysql_defaults()
    parser = argparse.ArgumentParser(description="行业协会出货增速(乘联会)→ MySQL")
    parser.add_argument("--host", default=h)
    parser.add_argument("--port", type=int, default=p)
    parser.add_argument("--user", default=u)
    parser.add_argument("--password", default=pw)
    parser.add_argument("--database", default=db)
    parser.add_argument("--table-name", default=tbl)
    parser.add_argument("--trade-date", default=None)
    parser.add_argument("--request-timeout", type=float, default=45.0)
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
        request_timeout=args.request_timeout,
    )
    raise SystemExit(0 if n >= 0 else 1)
