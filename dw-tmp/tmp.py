#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
临时补数：按交易日循环执行 moneyflow_ind_dc → ods_industry_fund_flow_di（snapshot）。

用法（须先 source dw-utils/func.sh）：
  python dw-tmp/tmp.py
  python dw-tmp/tmp.py --start 20230101 --end 20260525
  python dw-tmp/tmp.py --dry-run
  python dw-tmp/tmp.py --sleep 0.3
  python dw-tmp/tmp.py --source-table moneyflow   # 个股资金流补数

等价于逐日执行：
  run_data_sync YYYYMMDD --source-table moneyflow_ind_dc
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
for _p in (_ROOT / "dw-utils", _ROOT / "dw-sync"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from sync_data import run_sync  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

SOURCE_TABLE = "moneyflow_ind_dc"
DEFAULT_START = date(2023, 1, 1)
DEFAULT_END = date.today()


def _parse_ymd(s: str) -> date:
    s = s.strip()
    if len(s) == 8 and s.isdigit():
        return datetime.strptime(s, "%Y%m%d").date()
    return datetime.strptime(s, "%Y-%m-%d").date()


def load_trading_dates(start: date, end: date) -> list[date]:
    """优先从库表 ods_trading_day / ods_trading_day_di 取交易日，否则 Tushare trade_cal。"""
    from sqlalchemy import text

    from mysql_config import get_engine

    for table in ("ods_trading_day", "ods_trading_day_di"):
        try:
            engine = get_engine()
            with engine.connect() as conn:
                rows = conn.execute(
                    text(
                        f"""
                        SELECT DISTINCT trade_date
                        FROM `{table}`
                        WHERE trade_date >= :s AND trade_date <= :e
                        ORDER BY trade_date
                        """
                    ),
                    {"s": start, "e": end},
                ).fetchall()
            if rows:
                dates = [r[0] if isinstance(r[0], date) else r[0].date() for r in rows]
                logger.info("交易日历来源: %s，共 %s 天", table, len(dates))
                return dates
        except Exception as exc:
            logger.debug("读取 %s 失败: %s", table, exc)

    try:
        from tushare_client import get_tushare_pro

        pro = get_tushare_pro("tushare")
        frames = []
        for exchange in ("SSE", "SZSE"):
            part = pro.trade_cal(
                exchange=exchange,
                start_date=start.strftime("%Y%m%d"),
                end_date=end.strftime("%Y%m%d"),
                is_open="1",
            )
            if part is not None and not part.empty:
                frames.append(part)
        if frames:
            import pandas as pd

            df = pd.concat(frames, ignore_index=True)
            col = "cal_date" if "cal_date" in df.columns else "trade_date"
            dates = sorted(
                {
                    datetime.strptime(str(x), "%Y%m%d").date()
                    for x in df[col].astype(str).unique()
                }
            )
            dates = [d for d in dates if start <= d <= end]
            logger.info("交易日历来源: trade_cal，共 %s 天", len(dates))
            return dates
    except Exception as exc:
        logger.warning("trade_cal 获取失败: %s", exc)

    # 兜底：仅工作日（不含法定假日）
    out: list[date] = []
    d = start
    while d <= end:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    logger.warning("交易日历来源: 工作日近似，共 %s 天（可能含非交易日）", len(out))
    return out


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Tushare 资金流历史补数（默认 moneyflow_ind_dc → ods_industry_fund_flow_di）"
    )
    parser.add_argument("--start", default=DEFAULT_START.strftime("%Y%m%d"), help="起始 YYYYMMDD")
    parser.add_argument("--end", default=DEFAULT_END.strftime("%Y%m%d"), help="结束 YYYYMMDD")
    parser.add_argument(
        "--source-table",
        default=SOURCE_TABLE,
        help="db_sync_task.source_table，默认 moneyflow_ind_dc",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--sleep", type=float, default=0.2, help="每日同步间隔秒数")
    parser.add_argument("--fail-fast", action="store_true", help="遇错即停")
    args = parser.parse_args()

    if os.getenv("DW_FUNC_LOADED") != "1":
        logger.warning("建议先执行: source dw-utils/func.sh")

    from tushare_client import clear_tushare_cache, prime_proxy_host

    clear_tushare_cache()
    if not prime_proxy_host("a.sszhixia.cn"):
        raise SystemExit(
            "无法解析 a.sszhixia.cn，请设置 TUSHARE_API_FALLBACK_IP 后重新 source func.sh"
        )

    start = _parse_ymd(args.start)
    end = _parse_ymd(args.end)
    if start > end:
        raise SystemExit("start 不能晚于 end")

    dates = load_trading_dates(start, end)
    if not dates:
        raise SystemExit("未得到任何交易日")

    logger.info(
        "补数 %s ~ %s，共 %s 个交易日，dry_run=%s",
        start,
        end,
        len(dates),
        args.dry_run,
    )

    ok, fail = 0, 0
    for i, td in enumerate(dates, 1):
        logger.info("===== [%s/%s] %s =====", i, len(dates), td)
        try:
            results = run_sync(
                td,
                source_table=args.source_table,
                dry_run=args.dry_run,
            )
            if results and all(r.ok for r in results):
                ok += 1
            else:
                fail += 1
                if args.fail_fast:
                    raise SystemExit(1)
        except SystemExit:
            raise
        except Exception as exc:
            fail += 1
            logger.exception("日期 %s 失败: %s", td, exc)
            if args.fail_fast:
                raise SystemExit(1) from exc
        if args.sleep > 0 and i < len(dates):
            time.sleep(args.sleep)

    logger.info("补数结束: 成功 %s / 失败 %s / 共 %s 天", ok, fail, len(dates))
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
