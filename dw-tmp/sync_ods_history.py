#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
ODS 历史数据回补：按 db_sync_task 配置，将指定目标表从 start~end 同步入库。

默认：20250101 ~ 昨日；覆盖用户指定的 22 张 ODS 表。
- full 表：执行一次全量同步（交易日历、分类、成分、ETF 基础、同花顺指数/成分）
- snapshot 表：按 ods_trading_day 交易日逐日 run_task
- ods_fina_indicator：按季 period 回补（复用 sync_ods_fina_indicator 逻辑）

用法（建议先 source dw-utils/func.sh）：
  python dw-tmp/sync_ods_history.py
  python dw-tmp/sync_ods_history.py --dry-run
  python dw-tmp/sync_ods_history.py --start 20250101 --end 20260609
  python dw-tmp/sync_ods_history.py --tables ods_stock_detail_di,ods_limit_list_di
  python dw-tmp/sync_ods_history.py --only-full
  python dw-tmp/sync_ods_history.py --only-snapshot --continue-on-error
  python dw-tmp/sync_ods_history.py --tables ods_dc_daily_di --sleep-task 2 --sleep-day 1

注意：snapshot 全表逐日回补 API 调用量大、耗时长，建议按表拆分或使用 --tables。
默认每次任务后休眠 1s、每个交易日后额外休眠 1s，可用 --sleep-task / --sleep-day 调整。
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

from sqlalchemy import text

_DW_ROOT = Path(__file__).resolve().parent.parent
for _p in (_DW_ROOT / "dw-utils", _DW_ROOT / "dw-sync", _DW_ROOT / "dw-tmp"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from mysql_config import get_engine, load_sync_tasks  # noqa: E402
from task_registry import SyncResult, run_task  # noqa: E402
from tushare_client import prime_proxy_host  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

DEFAULT_START = "20250101"

# 用户指定回补表（默认全部）
DEFAULT_TARGET_TABLES: tuple[str, ...] = (
    "ods_dc_daily_di",
    "ods_dc_hot_di",
    "ods_dc_index_di",
    "ods_dc_member_di",
    "ods_etf_basic_di",
    "ods_etf_share_size_di",
    "ods_fina_indicator",
    "ods_index_daily_di",
    "ods_index_member_all",
    "ods_industry_classify",
    "ods_industry_daily_di",
    "ods_industry_fund_flow_di",
    "ods_limit_list_di",
    "ods_report_rc_di",
    "ods_stock_detail_di",
    "ods_stock_fund_flow_di",
    "ods_ths_daily_di",
    "ods_ths_hot_di",
    "ods_ths_index_di",
    "ods_ths_member_di",
    "ods_trading_day",
    "ods_trading_day_di",
)

# full 同步顺序（含依赖：ths_index → ths_member）
FULL_TABLE_ORDER: tuple[str, ...] = (
    "ods_trading_day",
    "ods_trading_day_di",
    "ods_industry_classify",
    "ods_index_member_all",
    "ods_etf_basic_di",
    "ods_ths_index_di",
    "ods_ths_member_di",
)

# 每日 snapshot 建议顺序（先行情/资金，后热榜）
SNAPSHOT_TABLE_ORDER: tuple[str, ...] = (
    "ods_stock_detail_di",
    "ods_stock_fund_flow_di",
    "ods_limit_list_di",
    "ods_industry_fund_flow_di",
    "ods_industry_daily_di",
    "ods_index_daily_di",
    "ods_dc_index_di",
    "ods_dc_daily_di",
    "ods_dc_member_di",
    "ods_ths_daily_di",
    "ods_etf_share_size_di",
    "ods_report_rc_di",
    "ods_dc_hot_di",
    "ods_ths_hot_di",
)

FINA_TABLE = "ods_fina_indicator"

# 历史回补默认休眠（秒），降低 Tushare 限流风险
DEFAULT_SLEEP_TASK = 1.0
DEFAULT_SLEEP_DAY = 1.0
DEFAULT_SLEEP_FULL = 2.0
DEFAULT_SLEEP_FINA = 0.8


def _sleep(seconds: float, reason: str) -> None:
    if seconds > 0:
        logger.info("休眠 %.2fs (%s)", seconds, reason)
        time.sleep(seconds)


def parse_yyyymmdd(s: str) -> date:
    s = s.strip()
    if len(s) == 8 and s.isdigit():
        return datetime.strptime(s, "%Y%m%d").date()
    return datetime.strptime(s, "%Y-%m-%d").date()


def default_end_yesterday() -> date:
    return date.today() - timedelta(days=1)


def build_task_map() -> dict[str, dict]:
    tasks = load_sync_tasks(status=1)
    return {t["target_table"]: t for t in tasks}


def ordered_tables(requested: list[str], order: tuple[str, ...]) -> list[str]:
    seen = set(requested)
    out = [t for t in order if t in seen]
    for t in requested:
        if t not in out:
            out.append(t)
    return out


def load_trading_days(start: date, end: date) -> list[date]:
    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT trade_date
                FROM ods_trading_day
                WHERE trade_date >= :s AND trade_date <= :e
                ORDER BY trade_date
                """
            ),
            {"s": start, "e": end},
        ).fetchall()
    return [r[0] for r in rows]


def run_one_task(
    task: dict,
    trade_date: date | None,
    *,
    dry_run: bool,
    continue_on_error: bool,
    sleep_task: float = 0.0,
) -> bool:
    ok = False
    try:
        result: SyncResult = run_task(task, trade_date, dry_run)
        if result.ok:
            logger.info(
                "OK %s -> %s rows=%s %s",
                result.source_table,
                result.target_table,
                result.rows_affected,
                result.message or "",
            )
            ok = True
        else:
            logger.error(
                "FAIL %s -> %s: %s",
                result.source_table,
                result.target_table,
                result.message,
            )
    except Exception as exc:  # noqa: BLE001
        logger.exception(
            "FAIL %s -> %s: %s",
            task.get("source_table"),
            task.get("target_table"),
            exc,
        )
    td_label = trade_date.isoformat() if trade_date else "full"
    _sleep(sleep_task, f"任务完成 {task.get('target_table')} {td_label}")
    if not ok and not continue_on_error:
        raise SystemExit(1)
    return ok


def run_full_phase(
    task_map: dict[str, dict],
    tables: list[str],
    end: date,
    *,
    dry_run: bool,
    continue_on_error: bool,
    sleep_task: float,
    sleep_full: float,
) -> None:
    full_tables = [t for t in tables if t in FULL_TABLE_ORDER]
    ordered = ordered_tables(full_tables, FULL_TABLE_ORDER)
    for idx, target in enumerate(ordered):
        task = task_map.get(target)
        if not task:
            logger.warning("跳过 full %s: 未找到 db_sync_task", target)
            continue
        mode = (task.get("sync_mode") or "").lower()
        if mode != "full":
            logger.warning("跳过 %s: sync_mode=%s 非 full", target, mode)
            continue
        logger.info("=== FULL %s (%s) ===", target, task["source_table"])
        run_one_task(
            task,
            end,
            dry_run=dry_run,
            continue_on_error=continue_on_error,
            sleep_task=sleep_task,
        )
        if sleep_full > 0 and idx + 1 < len(ordered):
            _sleep(sleep_full, f"full 表间隔 {target}")


def run_fina_phase(
    start: date,
    end: date,
    *,
    dry_run: bool,
    sleep: float,
) -> None:
    logger.info("=== FINA %s %s ~ %s ===", FINA_TABLE, start, end)
    import sync_ods_fina_indicator as fina_mod  # noqa: WPS433

    prime_proxy_host()
    task = fina_mod.load_task()
    raw = fina_mod.fetch_periods(task, start, end, sleep_s=sleep)
    out = fina_mod.apply_transform(raw, task)
    logger.info("fina_indicator 原始 %s 行，转换后 %s 行", len(raw), len(out))
    if dry_run:
        return
    if out.empty:
        logger.warning("fina_indicator 无数据可写")
        return
    rows = fina_mod.upsert_dataframe(
        out, database=fina_mod.TARGET_DATABASE, table=fina_mod.TARGET_TABLE
    )
    logger.info("fina_indicator UPSERT %s 行", rows)


def run_snapshot_phase(
    task_map: dict[str, dict],
    tables: list[str],
    trading_days: list[date],
    *,
    dry_run: bool,
    sleep_task: float,
    sleep_day: float,
    continue_on_error: bool,
) -> None:
    snap_tables = [t for t in tables if t not in FULL_TABLE_ORDER and t != FINA_TABLE]
    snap_tables = ordered_tables(snap_tables, SNAPSHOT_TABLE_ORDER)
    if not snap_tables:
        logger.info("无 snapshot 表需要回补")
        return

    total_days = len(trading_days)
    for di, td in enumerate(trading_days, start=1):
        logger.info("--- 交易日 %s/%s %s ---", di, total_days, td)
        for target in snap_tables:
            task = task_map.get(target)
            if not task:
                logger.warning("跳过 snapshot %s: 未找到 db_sync_task", target)
                continue
            mode = (task.get("sync_mode") or "").lower()
            if mode != "snapshot":
                logger.warning("跳过 %s: sync_mode=%s 非 snapshot", target, mode)
                continue
            logger.info("SNAPSHOT %s (%s) trade_date=%s", target, task["source_table"], td)
            run_one_task(
                task,
                td,
                dry_run=dry_run,
                continue_on_error=continue_on_error,
                sleep_task=sleep_task,
            )
        if sleep_day > 0 and di < total_days:
            _sleep(sleep_day, f"交易日 {td} 全部 snapshot 完成")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="ODS 历史数据回补（20250101 起）")
    parser.add_argument("--start", default=DEFAULT_START, help="YYYYMMDD，默认 20250101")
    parser.add_argument("--end", default=None, help="YYYYMMDD，默认昨日")
    parser.add_argument(
        "--tables",
        default=None,
        help="逗号分隔目标表名，默认回补全部 22 张表",
    )
    parser.add_argument("--dry-run", action="store_true", help="只拉数统计，不写库")
    parser.add_argument("--only-full", action="store_true", help="仅跑 full 表")
    parser.add_argument("--only-snapshot", action="store_true", help="仅跑 snapshot 逐日")
    parser.add_argument("--only-fina", action="store_true", help="仅跑 ods_fina_indicator")
    parser.add_argument(
        "--continue-on-error",
        action="store_true",
        help="单日/单表失败不中断（默认遇错退出）",
    )
    parser.add_argument(
        "--sleep-task",
        type=float,
        default=DEFAULT_SLEEP_TASK,
        help=f"每次任务（表×交易日）完成后的休眠秒数，默认 {DEFAULT_SLEEP_TASK}",
    )
    parser.add_argument(
        "--sleep-day",
        type=float,
        default=DEFAULT_SLEEP_DAY,
        help=f"每个交易日全部 snapshot 任务完成后的额外休眠秒数，默认 {DEFAULT_SLEEP_DAY}",
    )
    parser.add_argument(
        "--sleep-full",
        type=float,
        default=DEFAULT_SLEEP_FULL,
        help=f"每张 full 表同步完成后的额外休眠秒数，默认 {DEFAULT_SLEEP_FULL}",
    )
    parser.add_argument(
        "--sleep-fina",
        type=float,
        default=DEFAULT_SLEEP_FINA,
        help=f"fina_indicator 每季 API 间隔，默认 {DEFAULT_SLEEP_FINA}",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    start = parse_yyyymmdd(args.start)
    end = parse_yyyymmdd(args.end) if args.end else default_end_yesterday()
    if start > end:
        logger.error("start=%s 不能晚于 end=%s", args.start, args.end or end)
        return 1

    if args.tables:
        tables = [t.strip() for t in args.tables.split(",") if t.strip()]
    else:
        tables = list(DEFAULT_TARGET_TABLES)

    logger.info(
        "ODS 历史回补: %s ~ %s, 表数=%s, sleep_task=%s sleep_day=%s sleep_full=%s sleep_fina=%s",
        start,
        end,
        len(tables),
        args.sleep_task,
        args.sleep_day,
        args.sleep_full,
        args.sleep_fina,
    )
    prime_proxy_host()
    task_map = build_task_map()

    missing = [t for t in tables if t not in task_map and t != FINA_TABLE]
    if missing:
        logger.warning("以下表未在 db_sync_task 中配置: %s", ", ".join(missing))

    run_full = not args.only_snapshot and not args.only_fina
    run_snap = not args.only_full and not args.only_fina
    run_fina = not args.only_full and not args.only_snapshot

    if run_full and any(t in FULL_TABLE_ORDER for t in tables):
        run_full_phase(
            task_map,
            tables,
            end,
            dry_run=args.dry_run,
            continue_on_error=args.continue_on_error,
            sleep_task=args.sleep_task,
            sleep_full=args.sleep_full,
        )

    trading_days: list[date] = []
    if run_snap and any(
        t for t in tables if t not in FULL_TABLE_ORDER and t != FINA_TABLE
    ):
        trading_days = load_trading_days(start, end)
        if not trading_days:
            logger.warning("ods_trading_day 在区间内无数据，尝试先同步交易日历")
            for cal in ("ods_trading_day", "ods_trading_day_di"):
                if cal in tables and cal in task_map:
                    run_one_task(
                        task_map[cal],
                        end,
                        dry_run=args.dry_run,
                        continue_on_error=args.continue_on_error,
                        sleep_task=args.sleep_task,
                    )
            trading_days = load_trading_days(start, end)
        if not trading_days:
            logger.error("无法获取 %s~%s 交易日列表，请先确保 ods_trading_day 有数据", start, end)
            return 1
        logger.info("交易日数量: %s (%s ~ %s)", len(trading_days), trading_days[0], trading_days[-1])

    if run_fina and FINA_TABLE in tables:
        run_fina_phase(start, end, dry_run=args.dry_run, sleep=args.sleep_fina)

    if run_snap and trading_days:
        run_snapshot_phase(
            task_map,
            tables,
            trading_days,
            dry_run=args.dry_run,
            sleep_task=args.sleep_task,
            sleep_day=args.sleep_day,
            continue_on_error=args.continue_on_error,
        )

    logger.info("ODS 历史回补完成")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
