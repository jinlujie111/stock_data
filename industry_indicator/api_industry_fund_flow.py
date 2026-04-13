#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
行业资金流 industry_fund_flow_di — HTTP JSON 接口，供微信小程序等前端调用。

运行（开发）:
  pip install -r requirements-api.txt
  python api_industry_fund_flow.py

环境变量（可选）:
  API_HOST  默认 0.0.0.0
  API_PORT  默认 8080
  API_KEY   若设置则请求头需带 X-Api-Key: <值>

生产部署请使用 HTTPS + 反向代理（nginx），并在微信公众平台配置 request 合法域名。
"""
from __future__ import annotations

import json
import logging
import os
import re
import sys
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pymysql
from flask import Flask, Response, jsonify, request

LOG = logging.getLogger(__name__)

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))


def _load_cfg():
    import config as cfg  # noqa: E402

    return cfg


def _conn():
    cfg = _load_cfg()
    return pymysql.connect(
        host=cfg.MYSQL_HOST,
        port=cfg.MYSQL_PORT,
        user=cfg.MYSQL_USER,
        password=cfg.MYSQL_PASSWORD,
        database=cfg.MYSQL_DATABASE,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=True,
    )


def _table_name() -> str:
    cfg = _load_cfg()
    name = cfg.INDUSTRY_FLOW_TABLE
    if not re.match(r"^[a-zA-Z0-9_]+$", name):
        raise ValueError("INDUSTRY_FLOW_TABLE 仅允许字母数字下划线")
    return name


def _json_default(obj: Any) -> Any:
    if isinstance(obj, (datetime, date)):
        return obj.isoformat() if hasattr(obj, "isoformat") else str(obj)
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, bytes):
        return obj.decode("utf-8", errors="replace")
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")


def _rows_to_json(rows: list[dict]) -> str:
    for row in rows:
        if "raw_json" in row and row["raw_json"] is not None:
            rj = row["raw_json"]
            if isinstance(rj, (dict, list)):
                pass
            elif isinstance(rj, str):
                try:
                    row["raw_json"] = json.loads(rj)
                except json.JSONDecodeError:
                    pass
    return json.dumps(
        {"code": 0, "message": "ok", "data": rows},
        ensure_ascii=False,
        default=_json_default,
    )


def create_app() -> Flask:
    app = Flask(__name__)
    api_key = os.getenv("API_KEY", "").strip()

    @app.before_request
    def _check_key() -> Response | None:
        if not api_key:
            return None
        if request.path in ("/", "/health"):
            return None
        if request.headers.get("X-Api-Key", "") != api_key:
            return jsonify({"code": 401, "message": "invalid or missing X-Api-Key"}), 401
        return None

    @app.get("/health")
    def health() -> Response:
        return jsonify({"status": "ok"})

    @app.get("/api/v1/industry-fund-flow/latest-date")
    def latest_date() -> Response:
        tbl = _table_name()
        sql = f"SELECT MAX(trade_date) AS d FROM `{tbl}`"
        with _conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql)
                row = cur.fetchone()
        d = row["d"] if row else None
        out = None
        if d is not None:
            out = d.isoformat() if hasattr(d, "isoformat") else str(d)[:10]
        return Response(
            json.dumps({"code": 0, "message": "ok", "data": {"trade_date": out}}, ensure_ascii=False),
            mimetype="application/json; charset=utf-8",
        )

    @app.get("/api/v1/industry-fund-flow/period-types")
    def period_types() -> Response:
        trade_date = request.args.get("trade_date", type=str)
        tbl = _table_name()
        if not trade_date:
            with _conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(f"SELECT MAX(trade_date) AS d FROM `{tbl}`")
                    r = cur.fetchone()
                    td = r["d"] if r else None
            if td is None:
                return Response(
                    json.dumps(
                        {"code": 0, "message": "ok", "data": {"trade_date": None, "period_types": []}},
                        ensure_ascii=False,
                    ),
                    mimetype="application/json; charset=utf-8",
                )
            trade_date = td.isoformat() if hasattr(td, "isoformat") else str(td)[:10]
        sql = (
            f"SELECT DISTINCT period_type FROM `{tbl}` WHERE trade_date = %s "
            "ORDER BY period_type"
        )
        with _conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (trade_date,))
                rows = cur.fetchall()
        names = [r["period_type"] for r in rows if r.get("period_type")]
        payload = json.dumps(
            {
                "code": 0,
                "message": "ok",
                "data": {"trade_date": trade_date, "period_types": names},
            },
            ensure_ascii=False,
        )
        return Response(payload, mimetype="application/json; charset=utf-8")

    @app.get("/api/v1/industry-fund-flow")
    def list_flow() -> Response:
        trade_date = request.args.get("trade_date", type=str)
        period_type = request.args.get("period_type", type=str)
        limit = request.args.get("limit", default=500, type=int)
        if limit < 1:
            limit = 1
        if limit > 2000:
            limit = 2000

        tbl = _table_name()
        if not trade_date:
            with _conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(f"SELECT MAX(trade_date) AS d FROM `{tbl}`")
                    r = cur.fetchone()
                    td = r["d"] if r else None
            if td is None:
                return Response(
                    _rows_to_json([]),
                    mimetype="application/json; charset=utf-8",
                )
            trade_date = td.isoformat() if hasattr(td, "isoformat") else str(td)[:10]

        conds = ["trade_date = %s"]
        params: list[Any] = [trade_date]
        if period_type:
            conds.append("period_type = %s")
            params.append(period_type)
        where = " AND ".join(conds)
        sql = (
            f"SELECT id, trade_date, period_type, ranking_no, industry_code, industry_name, "
            f"industry_index_value, industry_change_pct, main_net_inflow, "
            f"super_large_net_inflow, large_net_inflow, company_count, "
            f"top_stock_name, top_stock_change_pct, current_price, industry_turnover, raw_json, "
            f"created_at, updated_at FROM `{tbl}` WHERE {where} "
            f"ORDER BY period_type, ranking_no IS NULL, ranking_no ASC LIMIT %s"
        )
        params.append(limit)

        with _conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                rows = cur.fetchall()

        return Response(
            _rows_to_json(rows),
            mimetype="application/json; charset=utf-8",
        )

    return app


def main() -> None:
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
    host = os.getenv("API_HOST", "0.0.0.0")
    port = int(os.getenv("API_PORT", "8080"))
    app = create_app()
    app.run(host=host, port=port, threaded=True)


if __name__ == "__main__":
    main()
