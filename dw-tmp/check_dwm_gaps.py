#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
检查 DWM 层各表在交易日区间内缺失的 trade_date。

以 ods_trading_day 为基准日历，对比每张 DWM 表是否已有数据（trade_date 存在且行数>0）。

用法（建议先 source dw-utils/func.sh）：
  python dw-tmp/check_dwm_gaps.py
  python dw-tmp/check_dwm_gaps.py --start 20250101 --end 20260609
  python dw-tmp/check_dwm_gaps.py --group dc
  python dw-tmp/check_dwm_gaps.py --jobs dc_fund_flow,dc_trend
  python dw-tmp/check_dwm_gaps.py --table dwm_dc_industry_fund_flow_di
  python dw-tmp/check_dwm_gaps.py --format dates
  python dw-tmp/check_dwm_gaps.py --export dw-tmp/out/dwm_gaps.csv

说明：
  - 「缺失」= 交易日历有该日，但 DWM 表无记录（或行数为 0）
  - 若 ODS 当日也无数据，DWM 脚本会 skip，也会表现为缺失
"""
from __future__ import annotations

import argparse
import csv
import sys
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

from sqlalchemy import text

_DW_ROOT = Path(__file__).resolve().parent.parent
for _p in (_DW_ROOT / "dw-utils", _DW_ROOT / "dw-tmp"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from mysql_config import get_engine  # noqa: E402

DEFAULT_START = "20250101"
DEFAULT_MAX_SHOW = 30


@dataclass(frozen=True)
class DwmTableSpec:
    job_id: str
    table: str
    desc: str
    groups: frozenset[str]


DWM_TABLES: tuple[DwmTableSpec, ...] = (
    DwmTableSpec("market_breadth", "dwm_market_breadth_di", "全市场广度", frozenset({"base", "dc", "ths", "sw", "all"})),
    DwmTableSpec("dc_fund_flow", "dwm_dc_industry_fund_flow_di", "东财资金", frozenset({"dc", "all"})),
    DwmTableSpec("ths_fund_flow", "dwm_ths_industry_fund_flow_di", "同花顺资金", frozenset({"ths", "all"})),
    DwmTableSpec("dc_trend", "dwm_dc_industry_trend_strength_di", "东财趋势", frozenset({"dc", "all"})),
    DwmTableSpec("ths_trend", "dwm_ths_industry_trend_strength_di", "同花顺趋势", frozenset({"ths", "all"})),
    DwmTableSpec("dc_prosperity", "dwm_dc_industry_prosperity_di", "东财景气", frozenset({"dc", "all"})),
    DwmTableSpec("ths_prosperity", "dwm_ths_industry_prosperity_di", "同花顺景气", frozenset({"ths", "all"})),
    DwmTableSpec("sw_prosperity", "dwm_sw_industry_prosperity_di", "申万景气", frozenset({"sw", "all"})),
    DwmTableSpec("dc_market_heat", "dwm_dc_industry_market_heat_di", "东财热度", frozenset({"dc", "all"})),
    DwmTableSpec("ths_market_heat", "dwm_ths_industry_market_heat_di", "同花顺热度", frozenset({"ths", "all"})),
    DwmTableSpec("dc_diffusion", "dwm_dc_industry_diffusion_di", "东财扩散", frozenset({"dc", "all"})),
    DwmTableSpec("ths_diffusion", "dwm_ths_industry_diffusion_di", "同花顺扩散", frozenset({"ths", "all"})),
    DwmTableSpec("sw_diffusion", "dwm_sw_industry_diffusion_di", "申万扩散", frozenset({"sw", "all"})),
)

TABLE_MAP = {t.table: t for t in DWM_TABLES}
JOB_MAP = {t.job_id: t for t in DWM_TABLES}


def parse_yyyymmdd(s: str) -> date:
    s = s.strip()
    if len(s) == 8 and s.isdigit():
        return datetime.strptime(s, "%Y%m%d").date()
    return datetime.strptime(s, "%Y-%m-%d").date()


def default_end_yesterday() -> date:
    return date.today() - timedelta(days=1)


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


def load_present_days(table: str, start: date, end: date) -> set[date]:
    engine = get_engine()
    with engine.connect() as conn:
        exists = conn.execute(
            text(
                """
                SELECT COUNT(*)
                FROM information_schema.tables
                WHERE table_schema = DATABASE()
                  AND table_name = :t
                """
            ),
            {"t": table},
        ).scalar()
        if not exists:
            return set()

        rows = conn.execute(
            text(
                f"""
                SELECT trade_date
                FROM `{table}`
                WHERE trade_date >= :s AND trade_date <= :e
                GROUP BY trade_date
                HAVING COUNT(*) > 0
                """
            ),
            {"s": start, "e": end},
        ).fetchall()
    return {r[0] for r in rows}


def resolve_specs(
    *,
    group: str | None,
    jobs_arg: str | None,
    table_arg: str | None,
) -> list[DwmTableSpec]:
    if table_arg:
        names = [x.strip() for x in table_arg.split(",") if x.strip()]
        out: list[DwmTableSpec] = []
        for name in names:
            if name in TABLE_MAP:
                out.append(TABLE_MAP[name])
            elif name in JOB_MAP:
                out.append(JOB_MAP[name])
            else:
                raise SystemExit(f"未知表/job: {name}")
        return out

    if jobs_arg:
        ids = [x.strip() for x in jobs_arg.split(",") if x.strip()]
        unknown = [i for i in ids if i not in JOB_MAP]
        if unknown:
            raise SystemExit(f"未知 job: {', '.join(unknown)}")
        return [JOB_MAP[i] for i in ids]

    grp = (group or "all").lower()
    if grp == "all":
        return list(DWM_TABLES)
    selected = [t for t in DWM_TABLES if grp in t.groups]
    if not selected:
        raise SystemExit(f"未知 group: {grp}")
    return selected


def fmt_dates(dates: list[date], max_show: int) -> str:
    if not dates:
        return "(无)"
    shown = dates[:max_show]
    parts = [d.strftime("%Y%m%d") for d in shown]
    if len(dates) > max_show:
        parts.append(f"... 共 {len(dates)} 天")
    return ", ".join(parts)


@dataclass
class GapReport:
    spec: DwmTableSpec
    expected: int
    present: int
    missing: list[date]


def build_reports(
    specs: list[DwmTableSpec],
    trading_days: list[date],
    start: date,
    end: date,
) -> list[GapReport]:
    expected_set = set(trading_days)
    reports: list[GapReport] = []
    for spec in specs:
        present = load_present_days(spec.table, start, end)
        missing = sorted(expected_set - present)
        reports.append(
            GapReport(
                spec=spec,
                expected=len(trading_days),
                present=len(present & expected_set),
                missing=missing,
            )
        )
    return reports


def print_table_report(reports: list[GapReport], max_show: int) -> None:
    print(f"{'表名':<42} {'应有':>6} {'已有':>6} {'缺失':>6}  缺失日期(节选)")
    print("-" * 110)
    for r in reports:
        print(
            f"{r.spec.table:<42} {r.expected:>6} {r.present:>6} {len(r.missing):>6}  "
            f"{fmt_dates(r.missing, max_show)}"
        )
    print("-" * 110)
    bad = [r for r in reports if r.missing]
    if bad:
        print(f"共 {len(bad)}/{len(reports)} 张表存在缺失交易日")
    else:
        print("全部表在区间内无缺失交易日")


def print_dates_report(reports: list[GapReport], max_show: int) -> None:
    for r in reports:
        print(f"# {r.spec.table} ({r.spec.desc}) 缺失 {len(r.missing)} 天")
        if r.missing:
            for d in r.missing[:max_show]:
                print(d.strftime("%Y%m%d"))
            if len(r.missing) > max_show:
                print(f"... 共 {len(r.missing)} 天")
        print()


def export_csv(path: Path, reports: list[GapReport]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["table", "job_id", "desc", "trade_date", "status"])
        for r in reports:
            missing_set = set(r.missing)
            # only export missing rows to keep file small
            for d in r.missing:
                w.writerow([r.spec.table, r.spec.job_id, r.spec.desc, d.isoformat(), "missing"])


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="检查 DWM 层缺失交易日")
    p.add_argument("--start", default=DEFAULT_START, help="YYYYMMDD，默认 20250101")
    p.add_argument("--end", default=None, help="YYYYMMDD，默认昨日")
    p.add_argument("--group", default="all", choices=["all", "base", "dc", "ths", "sw"])
    p.add_argument("--jobs", default=None, help="逗号分隔 job id")
    p.add_argument("--table", default=None, help="逗号分隔表名或 job id")
    p.add_argument(
        "--format",
        default="table",
        choices=["table", "dates"],
        help="table=汇总表；dates=按表列出缺失 YYYYMMDD",
    )
    p.add_argument("--max-show", type=int, default=DEFAULT_MAX_SHOW, help="终端最多展示缺失天数")
    p.add_argument("--export", default=None, help="导出缺失明细 CSV 路径")
    p.add_argument("--list-tables", action="store_true", help="列出可检查的表")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.list_tables:
        for t in DWM_TABLES:
            print(f"{t.job_id:20} {t.table:42} {t.desc}")
        return 0

    start = parse_yyyymmdd(args.start)
    end = parse_yyyymmdd(args.end) if args.end else default_end_yesterday()
    if start > end:
        print(f"ERROR: start={args.start} 不能晚于 end={args.end or end}", file=sys.stderr)
        return 1

    specs = resolve_specs(group=args.group, jobs_arg=args.jobs, table_arg=args.table)
    trading_days = load_trading_days(start, end)
    if not trading_days:
        print(
            f"ERROR: ods_trading_day 在 {start}~{end} 无交易日，请先同步交易日历",
            file=sys.stderr,
        )
        return 1

    print(
        f"区间: {start} ~ {end} | 交易日: {len(trading_days)} 天 "
        f"({trading_days[0]} ~ {trading_days[-1]}) | 检查表: {len(specs)} 张"
    )
    reports = build_reports(specs, trading_days, start, end)

    if args.format == "dates":
        print_dates_report(reports, args.max_show)
    else:
        print_table_report(reports, args.max_show)

    if args.export:
        export_csv(Path(args.export), reports)
        print(f"已导出: {Path(args.export).resolve()}")

    return 1 if any(r.missing for r in reports) else 0


if __name__ == "__main__":
    raise SystemExit(main())
