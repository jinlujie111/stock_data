#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
cyq_chips 区间补数（不修改项目代码，复用 dw-sync 已有同步逻辑）。

按 ods_trading_day 逐交易日执行 cyq_chips → ods_cyq_chips_di。
股票列表来自当日 ods_stock_detail_di；missing_only=true 时跳过已入库个股。

用法（Windows / Linux 均可）：
  python tmp/backfill_cyq_chips.py
  python tmp/backfill_cyq_chips.py --start 20250101 --end 20260708
  python tmp/backfill_cyq_chips.py --dry-run
  python tmp/backfill_cyq_chips.py --start 20250601 --end 20250605

运行前请确保已配置 MySQL / Tushare 环境变量（与 source dw-utils/func.sh 一致），
或在本机已设置 MYSQL_PASSWORD、CONFIG_MYSQL_PASSWORD 等。
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import date, datetime
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_DW_UTILS = _ROOT / "dw-utils"
_DW_SYNC = _ROOT / "dw-sync"
for _p in (_DW_UTILS, _DW_SYNC):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))


def _apply_default_env() -> None:
    """未 export 时写入 func.sh 默认值，便于 Windows 直接跑。"""
    defaults = {
        "CONFIG_MYSQL_HOST": "localhost",
        "CONFIG_MYSQL_PORT": "3306",
        "CONFIG_MYSQL_USER": "data_config",
        "CONFIG_MYSQL_PASSWORD": "1qaz!QAZjinlujie",
        "CONFIG_MYSQL_DATABASE": "data_config",
        "STOCK_MYSQL_HOST": "localhost",
        "STOCK_MYSQL_PORT": "3306",
        "STOCK_MYSQL_USER": "app_user",
        "STOCK_MYSQL_PASSWORD": "jinlujie",
        "STOCK_MYSQL_DATABASE": "stock_data",
        "MYSQL_HOST": "localhost",
        "MYSQL_PORT": "3306",
        "MYSQL_USER": "app_user",
        "MYSQL_PASSWORD": "jinlujie",
        "MYSQL_DATABASE": "stock_data",
        "TUSHARE_HTTP_URL": "http://a.sszhixia.cn/",
        "TUSHARE_API_FALLBACK_IP": "104.21.96.101",
        "TUSHARE_USE_FALLBACK_IP": "1",
        "TUSHARE_HTTP_TIMEOUT": "15",
        "TUSHARE_FETCH_RETRIES": "3",
        "TUSHARE_FETCH_RETRY_SLEEP": "5",
        "DW_FUNC_LOADED": "1",
    }
    for key, val in defaults.items():
        os.environ.setdefault(key, val)
    if not os.environ.get("MYSQL_HOST"):
        os.environ["MYSQL_HOST"] = os.environ.get("STOCK_MYSQL_HOST", "localhost")
    if not os.environ.get("MYSQL_PASSWORD"):
        os.environ["MYSQL_PASSWORD"] = os.environ.get("STOCK_MYSQL_PASSWORD", "")


def _parse_yyyymmdd(s: str) -> date:
    s = s.strip()
    if len(s) == 8 and s.isdigit():
        return datetime.strptime(s, "%Y%m%d").date()
    return datetime.strptime(s, "%Y-%m-%d").date()


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="cyq_chips 区间补数")
    p.add_argument("--start", default="20250101", help="起始日 YYYYMMDD（含）")
    p.add_argument("--end", default="20260708", help="结束日 YYYYMMDD（含）")
    p.add_argument("--dry-run", action="store_true", help="只拉取统计，不写库")
    return p.parse_args()


def main() -> int:
    _apply_default_env()
    args = parse_args()
    start = _parse_yyyymmdd(args.start)
    end = _parse_yyyymmdd(args.end)
    if end < start:
        start, end = end, start

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    logger = logging.getLogger("backfill_cyq_chips")

    from trade_data_flag import get_trading_dates
    from sync_data import run_sync

    dates = get_trading_dates(start, end)
    if not dates:
        logger.error("区间 %s ~ %s 在 ods_trading_day 无交易日", start, end)
        return 1

    logger.info(
        "cyq_chips 补数: %s ~ %s，共 %s 个交易日，dry_run=%s",
        dates[0],
        dates[-1],
        len(dates),
        args.dry_run,
    )
    logger.info("前置依赖：每个交易日需已有 ods_stock_detail_di 行情，否则当日无待拉股票")

    failed: list[date] = []
    for i, td in enumerate(dates, start=1):
        logger.info("—— 进度 %s/%s: %s ——", i, len(dates), td)
        try:
            results = run_sync(
                td,
                source_table="cyq_chips",
                dry_run=args.dry_run,
                force_schedule=True,
            )
            if not any(r.ok for r in results):
                failed.append(td)
        except SystemExit:
            failed.append(td)

    if failed:
        logger.error("失败 %s 天（前 10 个）: %s", len(failed), failed[:10])
        return 1

    logger.info("cyq_chips 区间补数完成: %s 个交易日", len(dates))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
