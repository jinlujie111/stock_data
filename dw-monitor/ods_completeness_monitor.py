#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
ODS 层数据完整度监控：全量维表 + 日快照/报告期覆盖 + 交易日连续性。

须 source dw-utils/func.sh 后运行（注入 MySQL 环境变量）。

用法:
  python dw-monitor/ods_completeness_monitor.py
  python dw-monitor/ods_completeness_monitor.py 20260627
  python dw-monitor/ods_completeness_monitor.py 20260627 --force
  python dw-monitor/ods_completeness_monitor.py --json
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any

_DW_ROOT = Path(__file__).resolve().parent.parent
for _p in (_DW_ROOT / "dw-utils", _DW_ROOT / "dw-sync", _DW_ROOT / "dw-monitor"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from sqlalchemy import text  # noqa: E402

from mysql_config import get_engine  # noqa: E402
from trade_data_flag import get_trading_dates, is_trading_day  # noqa: E402


class Level(str, Enum):
    OK = "OK"
    WARN = "WARN"
    ALERT = "ALERT"
    SKIP = "SKIP"


@dataclass
class CheckResult:
    table: str
    check_type: str
    level: Level
    message: str
    label: str = ""
    metrics: dict[str, Any] = field(default_factory=dict)


def parse_check_date(s: str | None) -> date:
    if not s:
        return date.today() - timedelta(days=1)
    s = s.strip()
    if len(s) == 8 and s.isdigit():
        return datetime.strptime(s, "%Y%m%d").date()
    return datetime.strptime(s, "%Y-%m-%d").date()


def load_checks_config(path: Path | None = None) -> dict[str, Any]:
    cfg_path = path or Path(__file__).with_name("ods_checks.json")
    with cfg_path.open(encoding="utf-8") as f:
        return json.load(f)


def table_exists(conn, table: str) -> bool:
    row = conn.execute(
        text(
            """
            SELECT COUNT(*)
            FROM information_schema.tables
            WHERE table_schema = DATABASE() AND table_name = :t
            """
        ),
        {"t": table},
    ).scalar()
    return int(row or 0) >= 1


def _where_clause(spec: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    w = spec.get("where")
    if not w:
        return "", {}
    return f" AND ({w})", {}


def check_full(conn, spec: dict[str, Any]) -> CheckResult:
    table = spec["table"]
    label = spec.get("label") or table
    min_rows = int(spec.get("min_rows") or 0)
    min_distinct = spec.get("min_distinct")
    distinct_col = spec.get("distinct_column")

    extra_where, _ = _where_clause(spec)
    total = conn.execute(text(f"SELECT COUNT(*) FROM `{table}` WHERE 1=1{extra_where}")).scalar()
    total = int(total or 0)
    metrics: dict[str, Any] = {"total_rows": total}

    if min_distinct and distinct_col:
        dcnt = conn.execute(
            text(f"SELECT COUNT(DISTINCT `{distinct_col}`) FROM `{table}` WHERE 1=1{extra_where}")
        ).scalar()
        metrics["distinct"] = int(dcnt or 0)

    if total < min_rows:
        return CheckResult(
            table, "full", Level.ALERT,
            f"全表行数不足 rows={total} require>={min_rows}",
            label, metrics,
        )
    if min_distinct and distinct_col and metrics.get("distinct", 0) < int(min_distinct):
        return CheckResult(
            table, "full", Level.ALERT,
            f"全表 distinct({distinct_col})={metrics['distinct']} require>={min_distinct}",
            label, metrics,
        )
    return CheckResult(
        table, "full", Level.OK,
        f"total_rows={total}" + (f" distinct={metrics.get('distinct')}" if "distinct" in metrics else ""),
        label, metrics,
    )


def _snapshot_metrics(
    conn, table: str, date_col: str, d: date, spec: dict[str, Any]
) -> dict[str, Any]:
    extra_where, _ = _where_clause(spec)
    params: dict[str, Any] = {"d": d}
    rows = conn.execute(
        text(f"SELECT COUNT(*) FROM `{table}` WHERE `{date_col}` = :d{extra_where}"),
        params,
    ).scalar()
    metrics: dict[str, Any] = {"date": d.isoformat(), "rows": int(rows or 0)}
    distinct_col = spec.get("distinct_column")
    if distinct_col:
        dcnt = conn.execute(
            text(
                f"SELECT COUNT(DISTINCT `{distinct_col}`) FROM `{table}`"
                f" WHERE `{date_col}` = :d{extra_where}"
            ),
            params,
        ).scalar()
        metrics["distinct"] = int(dcnt or 0)
    return metrics


def check_snapshot_one(
    conn, spec: dict[str, Any], d: date, *, prefix: str = ""
) -> CheckResult | None:
    table = spec["table"]
    label = spec.get("label") or table
    date_col = spec["date_column"]
    min_rows = int(spec.get("min_rows") or 0)
    min_distinct = spec.get("min_distinct")

    metrics = _snapshot_metrics(conn, table, date_col, d, spec)
    tag = f"{prefix}{date_col}={d}"

    if metrics["rows"] < min_rows:
        return CheckResult(
            table, "snapshot", Level.ALERT,
            f"{tag} rows={metrics['rows']} require>={min_rows}",
            label, metrics,
        )
    if min_distinct and metrics.get("distinct", 0) < int(min_distinct):
        return CheckResult(
            table, "snapshot", Level.ALERT,
            f"{tag} distinct={metrics.get('distinct')} require>={min_distinct}",
            label, metrics,
        )
    return CheckResult(
        table, "snapshot", Level.OK,
        f"{tag} rows={metrics['rows']}"
        + (f" distinct={metrics.get('distinct')}" if "distinct" in metrics else ""),
        label, metrics,
    )


def check_snapshot(conn, spec: dict[str, Any], check_date: date, defaults: dict[str, Any]) -> list[CheckResult]:
    table = spec["table"]
    label = spec.get("label") or table
    results: list[CheckResult] = []

    primary = check_snapshot_one(conn, spec, check_date)
    if primary:
        results.append(primary)

    if not spec.get("continuity"):
        return results

    n_days = int(spec.get("continuity_trade_days") or defaults.get("continuity_trade_days") or 5)
    start = check_date - timedelta(days=max(n_days * 3, 30))
    trade_days = get_trading_dates(start, check_date)
    if check_date not in trade_days and trade_days:
        trade_days = [d for d in trade_days if d <= check_date]
    window = trade_days[-n_days:] if len(trade_days) >= n_days else trade_days

    missing: list[str] = []
    min_rows = int(spec.get("min_rows") or 0)
    for d in window:
        if d == check_date:
            continue
        m = _snapshot_metrics(conn, table, spec["date_column"], d, spec)
        if m["rows"] < min_rows:
            missing.append(f"{d}(rows={m['rows']})")

    if missing:
        results.append(
            CheckResult(
                table, "continuity", Level.WARN,
                f"近{n_days}个交易日缺数据或不足: {', '.join(missing)}",
                label,
                {"missing_dates": missing, "window": [d.isoformat() for d in window]},
            )
        )
    elif window:
        results.append(
            CheckResult(
                table, "continuity", Level.OK,
                f"近{len(window)}个交易日连续性通过",
                label,
                {"window": [d.isoformat() for d in window]},
            )
        )
    return results


def check_period(conn, spec: dict[str, Any], defaults: dict[str, Any]) -> list[CheckResult]:
    table = spec["table"]
    label = spec.get("label") or table
    date_col = spec["date_column"]
    period_count = int(spec.get("period_count") or defaults.get("period_lookback") or 2)
    min_distinct = int(spec.get("min_distinct") or 0)
    min_rows = spec.get("min_rows_per_period")
    distinct_col = spec.get("distinct_column") or "ts_code"
    extra_where, _ = _where_clause(spec)

    rows = conn.execute(
        text(
            f"""
            SELECT `{date_col}` AS pd,
                   COUNT(*) AS row_cnt,
                   COUNT(DISTINCT `{distinct_col}`) AS stock_cnt
            FROM `{table}`
            WHERE 1=1{extra_where}
            GROUP BY `{date_col}`
            ORDER BY `{date_col}` DESC
            LIMIT :lim
            """
        ),
        {"lim": period_count},
    ).mappings().all()

    results: list[CheckResult] = []
    if len(rows) < period_count:
        results.append(
            CheckResult(
                table, "period", Level.ALERT,
                f"报告期数量不足 periods={len(rows)} require>={period_count}",
                label,
                {"periods_found": len(rows)},
            )
        )

    for r in rows:
        pd_val = r["pd"]
        pd_str = pd_val.isoformat() if hasattr(pd_val, "isoformat") else str(pd_val)
        stock_cnt = int(r["stock_cnt"] or 0)
        row_cnt = int(r["row_cnt"] or 0)
        metrics = {"end_date": pd_str, "rows": row_cnt, "distinct": stock_cnt}
        if stock_cnt < min_distinct:
            results.append(
                CheckResult(
                    table, "period", Level.ALERT,
                    f"{date_col}={pd_str} distinct={stock_cnt} require>={min_distinct}",
                    label, metrics,
                )
            )
        elif min_rows and row_cnt < int(min_rows):
            results.append(
                CheckResult(
                    table, "period", Level.WARN,
                    f"{date_col}={pd_str} rows={row_cnt} require>={min_rows}",
                    label, metrics,
                )
            )
        else:
            results.append(
                CheckResult(
                    table, "period", Level.OK,
                    f"{date_col}={pd_str} rows={row_cnt} distinct={stock_cnt}",
                    label, metrics,
                )
            )
    return results


def run_monitor(
    check_date: date,
    *,
    force: bool = False,
    config_path: Path | None = None,
) -> tuple[list[CheckResult], dict[str, int]]:
    cfg = load_checks_config(config_path)
    defaults = cfg.get("defaults") or {}
    specs: list[dict[str, Any]] = cfg.get("checks") or []

    results: list[CheckResult] = []
    engine = get_engine()

    if not force and not is_trading_day(check_date):
        results.append(
            CheckResult(
                "ods_trading_day", "calendar", Level.SKIP,
                f"{check_date} 非交易日，跳过日快照/连续性检查（加 --force 强制执行）",
            )
        )
        run_snapshots = False
    else:
        run_snapshots = True
        with engine.connect() as conn:
            if not table_exists(conn, "ods_trading_day"):
                results.append(
                    CheckResult("ods_trading_day", "calendar", Level.ALERT, "表不存在")
                )
            else:
                cnt = conn.execute(
                    text("SELECT COUNT(*) FROM ods_trading_day WHERE trade_date = :d"),
                    {"d": check_date},
                ).scalar()
                if int(cnt or 0) < 1:
                    results.append(
                        CheckResult(
                            "ods_trading_day", "calendar", Level.ALERT,
                            f"交易日历缺少 {check_date}",
                        )
                    )
                else:
                    results.append(
                        CheckResult(
                            "ods_trading_day", "calendar", Level.OK,
                            f"含 {check_date}",
                        )
                    )

    with engine.connect() as conn:
        for spec in specs:
            table = spec["table"]
            ctype = spec.get("type", "snapshot")
            if not table_exists(conn, table):
                results.append(
                    CheckResult(table, ctype, Level.ALERT, "表不存在", spec.get("label") or table)
                )
                continue

            if ctype == "full":
                results.append(check_full(conn, spec))
            elif ctype == "period":
                results.extend(check_period(conn, spec, defaults))
            elif ctype == "snapshot":
                if run_snapshots or force:
                    results.extend(check_snapshot(conn, spec, check_date, defaults))
                else:
                    results.append(
                        CheckResult(
                            table, ctype, Level.SKIP,
                            "非交易日跳过",
                            spec.get("label") or table,
                        )
                    )
            else:
                results.append(
                    CheckResult(table, ctype, Level.ALERT, f"未知检查类型: {ctype}")
                )

    summary = {
        "ok": sum(1 for r in results if r.level == Level.OK),
        "warn": sum(1 for r in results if r.level == Level.WARN),
        "alert": sum(1 for r in results if r.level == Level.ALERT),
        "skip": sum(1 for r in results if r.level == Level.SKIP),
    }
    return results, summary


def format_line(r: CheckResult) -> str:
    label = f" ({r.label})" if r.label else ""
    return f"[{r.level.value}] {r.table}{label} [{r.check_type}] {r.message}"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="ODS 层数据完整度监控")
    parser.add_argument("check_date", nargs="?", default=None, help="业务日 YYYYMMDD，默认昨日")
    parser.add_argument("--force", "-f", action="store_true", help="非交易日也执行日快照检查")
    parser.add_argument("--json", action="store_true", help="输出 JSON 结果")
    parser.add_argument("--config", default=None, help="检查配置 JSON 路径")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    check_date = parse_check_date(args.check_date)
    config_path = Path(args.config) if args.config else None

    results, summary = run_monitor(check_date, force=args.force, config_path=config_path)

    if args.json:
        payload = {
            "check_date": check_date.isoformat(),
            "summary": summary,
            "results": [
                {**asdict(r), "level": r.level.value} for r in results
            ],
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"======== ODS 完整度监控 check_date={check_date} ========")
        for r in results:
            print(format_line(r))
        print(
            f"--- 汇总 OK={summary['ok']} WARN={summary['warn']} "
            f"ALERT={summary['alert']} SKIP={summary['skip']} ---"
        )

    return 1 if summary["alert"] > 0 else 0


if __name__ == "__main__":
    raise SystemExit(main())
