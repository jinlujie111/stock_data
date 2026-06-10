#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
回溯同步 Tushare fina_indicator_vip → ods_fina_indicator（按报告期 period 季末全市场拉取）。

默认区间：20250101 起至今日（覆盖 2025 年以来各季报财务指标，供产业景气 DWM 等使用）。

用法（建议先 source dw-utils/func.sh）：
  python dw-tmp/sync_ods_fina_indicator.py
  python dw-tmp/sync_ods_fina_indicator.py --dry-run
  python dw-tmp/sync_ods_fina_indicator.py --start 20250101 --end 20260630
  python dw-tmp/sync_ods_fina_indicator.py --sleep 0.6 --save-csv dw-tmp/out/fina_2025.csv

说明：
  - 默认 UPSERT（ON DUPLICATE KEY UPDATE），不清空历史；仅补 2025 以来缺口时用默认参数即可。
  - 需 Tushare fina_indicator_vip 权限（约 5000 积分）；走 db_token / TUSHARE_HTTP_URL 代理。
"""
from __future__ import annotations

import argparse
import logging
import math
import os
import sys
import time
from datetime import date, datetime
from pathlib import Path

import pandas as pd
from sqlalchemy import text

_DW_ROOT = Path(__file__).resolve().parent.parent
for _p in (_DW_ROOT / "dw-utils", _DW_ROOT / "dw-sync"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from mysql_config import get_engine, load_sync_tasks  # noqa: E402
from task_config import apply_transform  # noqa: E402
from task_registry import _quarter_period_ends, fetch_tushare  # noqa: E402
from tushare_client import prime_proxy_host  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

DEFAULT_START = "20250101"
TARGET_TABLE = "ods_fina_indicator"
TARGET_DATABASE = "stock_data"
SOURCE_TABLE = "fina_indicator_vip"
SLEEP_SECONDS = 0.5

_FALLBACK_TASK = {
    "source_table": SOURCE_TABLE,
    "fetch_config": {
        "token_type": "tushare",
        "sleep_seconds": SLEEP_SECONDS,
    },
    "transform_config": {
        "date_columns": {"ann_date": "%Y%m%d", "end_date": "%Y%m%d"},
        "dedupe": ["ts_code", "end_date", "ann_date"],
        "dropna": ["ts_code", "end_date", "ann_date"],
        "keep_columns": [
            "ts_code", "ann_date", "end_date",
            "eps", "dt_eps", "bps", "roe", "roe_waa", "roe_dt", "roa",
            "grossprofit_margin", "netprofit_margin", "debt_to_assets", "profit_dedt",
            "tr_yoy", "or_yoy", "netprofit_yoy", "dt_netprofit_yoy",
            "op_yoy", "ebt_yoy", "equity_yoy", "q_profit_yoy", "q_sales_yoy", "ocf_yoy",
        ],
    },
}


def _default_end_yyyymmdd() -> str:
    return date.today().strftime("%Y%m%d")


def ensure_dw_loaded() -> None:
    if os.getenv("DW_FUNC_LOADED") != "1":
        logger.warning(
            "未检测到 DW_FUNC_LOADED=1，将使用环境变量默认值；"
            "建议先: source dw-utils/func.sh"
        )


def parse_yyyymmdd(s: str) -> date:
    s = s.strip()
    if len(s) == 8 and s.isdigit():
        return datetime.strptime(s, "%Y%m%d").date()
    return datetime.strptime(s, "%Y-%m-%d").date()


def load_task() -> dict:
    try:
        tasks = load_sync_tasks(source_table=SOURCE_TABLE, status=1)
        if tasks:
            logger.info("使用 db_sync_task id=%s 的 transform 配置", tasks[0]["id"])
            return tasks[0]
    except Exception as exc:  # noqa: BLE001
        logger.warning("读取 db_sync_task 失败，使用内置 transform 配置: %s", exc)
    else:
        logger.warning("未找到 db_sync_task，使用内置 transform 配置")
    return _FALLBACK_TASK


def _sql_value(v):
    """pymysql 不接受 float nan；统一转为 NULL。"""
    if v is None:
        return None
    if isinstance(v, float) and math.isnan(v):
        return None
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    return v


def _mysql_records(df: pd.DataFrame, cols: list[str]) -> list[dict]:
    # float 列上 .where(..., None) 仍会保留 nan，须逐格清洗
    sub = df[cols].astype(object)
    return [{c: _sql_value(row[c]) for c in cols} for row in sub.to_dict(orient="records")]


def upsert_dataframe(df: pd.DataFrame, *, database: str, table: str) -> int:
    if df.empty:
        return 0

    engine = get_engine(database)
    cols = [c for c in df.columns if c != "id"]
    col_sql = ", ".join(f"`{c}`" for c in cols)
    val_sql = ", ".join(f":{c}" for c in cols)
    update_sql = ", ".join(
        f"`{c}`=VALUES(`{c}`)" for c in cols if c not in ("ts_code", "end_date", "ann_date")
    )
    sql = (
        f"INSERT INTO `{table}` ({col_sql}) VALUES ({val_sql}) "
        f"ON DUPLICATE KEY UPDATE {update_sql}"
    )

    records = _mysql_records(df, cols)
    with engine.begin() as conn:
        conn.execute(text(sql), records)
    return len(records)


def fetch_periods(
    task: dict,
    start: date,
    end: date,
    *,
    sleep_s: float,
) -> pd.DataFrame:
    fetch_cfg = task.get("fetch_config") or {}
    if isinstance(fetch_cfg, str):
        import json

        fetch_cfg = json.loads(fetch_cfg)
    token_type = fetch_cfg.get("token_type") or "tushare"
    sleep_s = float(fetch_cfg.get("sleep_seconds") or sleep_s)

    periods = _quarter_period_ends(start.strftime("%Y%m%d"), end)
    logger.info(
        "共 %s 个报告期: %s ~ %s",
        len(periods),
        periods[0] if periods else "-",
        periods[-1] if periods else "-",
    )

    frames: list[pd.DataFrame] = []
    for i, period in enumerate(periods):
        logger.info("拉取进度 %s/%s period=%s", i + 1, len(periods), period)
        try:
            part = fetch_tushare(SOURCE_TABLE, token_type=token_type, period=period)
        except Exception as exc:  # noqa: BLE001
            logger.warning("period=%s 失败: %s", period, exc)
            continue
        if not part.empty:
            logger.info("period=%s 返回 %s 行", period, len(part))
            frames.append(part)
        if sleep_s > 0 and i + 1 < len(periods):
            time.sleep(sleep_s)

    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="同步 fina_indicator_vip → ods_fina_indicator（默认自 2025-01-01 起）"
    )
    parser.add_argument(
        "--start",
        default=DEFAULT_START,
        help=f"区间起点 YYYYMMDD，默认 {DEFAULT_START}",
    )
    parser.add_argument(
        "--end",
        default=None,
        help="区间终点 YYYYMMDD，默认今日",
    )
    parser.add_argument("--dry-run", action="store_true", help="只拉取统计，不写库")
    parser.add_argument("--save-csv", default=None, help="额外保存 CSV 路径")
    parser.add_argument("--sleep", type=float, default=SLEEP_SECONDS, help="每次 API 间隔秒数")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    ensure_dw_loaded()
    args = parse_args(argv)
    end_s = args.end or _default_end_yyyymmdd()
    start = parse_yyyymmdd(args.start)
    end = parse_yyyymmdd(end_s)
    if start > end:
        logger.error("start=%s 不能晚于 end=%s", args.start, end_s)
        return 1

    logger.info("同步 %s.%s：%s ~ %s", TARGET_DATABASE, TARGET_TABLE, args.start, end_s)
    prime_proxy_host()
    task = load_task()

    raw = fetch_periods(task, start, end, sleep_s=args.sleep)
    out = apply_transform(raw, task)
    logger.info("原始 %s 行，转换后 %s 行", len(raw), len(out))

    if args.save_csv:
        csv_path = Path(args.save_csv)
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        out.to_csv(csv_path, index=False, encoding="utf-8-sig")
        logger.info("已保存 CSV: %s", csv_path.resolve())

    if args.dry_run:
        logger.info("dry-run 完成，未写库")
        return 0

    if out.empty:
        logger.warning("无数据可写")
        return 0

    rows = upsert_dataframe(out, database=TARGET_DATABASE, table=TARGET_TABLE)
    logger.info("UPSERT %s.%s 完成，%s 行", TARGET_DATABASE, TARGET_TABLE, rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
