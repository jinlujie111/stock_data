"""涨停天梯分析（ods_limit_list_di · limit=U）。"""
from __future__ import annotations

import re
from typing import Any

from app.db import fetch_all_stock
from app.dc_query_util import (
    latest_trade_date_from_table,
    list_trade_dates_from_table,
    resolve_trade_date,
    serialize_row,
)

TABLE = "ods_limit_list_di"

# 展示顺序：高连板在前
LADDER_LEVELS: tuple[tuple[int, str], ...] = (
    (6, "五板以上"),
    (5, "五板"),
    (4, "四板"),
    (3, "三板"),
    (2, "二板"),
    (1, "一板"),
)


def latest_trade_date() -> str | None:
    return latest_trade_date_from_table(TABLE, fallback_table="ods_stock_detail_di")


def list_trade_dates(limit: int = 90) -> list[str]:
    dates = list_trade_dates_from_table(TABLE, limit)
    if dates:
        return dates
    return list_trade_dates_from_table("ods_stock_detail_di", limit)


def _resolve_trade_date(trade_date: str | None) -> str:
    return resolve_trade_date(
        trade_date,
        table=TABLE,
        fallback_table="ods_stock_detail_di",
        empty_msg="暂无涨停数据，请先运行 run_data_sync 同步 limit_list_d",
    )


def _bucket_level(limit_times: int | None) -> int:
    if limit_times is None or limit_times < 1:
        return 1
    if limit_times >= 6:
        return 6
    return int(limit_times)


def _parse_up_stat(up_stat: str | None) -> tuple[int | None, int | None]:
    """Tushare up_stat 为 N/T（N 板 / T 天）→ 展示 T天N板。"""
    if not up_stat:
        return None, None
    m = re.match(r"^\s*(\d+)\s*/\s*(\d+)\s*$", str(up_stat).strip())
    if not m:
        return None, None
    boards, days = int(m.group(1)), int(m.group(2))
    return days, boards


def _format_stat(item: dict) -> str:
    days, boards = _parse_up_stat(item.get("up_stat"))
    lt = item.get("limit_times")
    if days is not None and boards is not None:
        stat = f"{days}天{boards}板"
    elif lt is not None:
        stat = f"{int(lt)}板"
    else:
        stat = "1板"
    pct = item.get("pct_chg")
    if pct is not None:
        n = float(pct)
        stat += f"({n:.2f}%)"
    return stat


def get_limit_up_ladder(trade_date: str | None = None) -> dict[str, Any]:
    td = _resolve_trade_date(trade_date)
    rows = fetch_all_stock(
        f"""
        SELECT
            l.trade_date, l.ts_code, l.name, l.industry,
            l.close, l.pct_chg, l.amount, l.turnover_ratio,
            l.first_time, l.last_time, l.open_times,
            l.up_stat, l.limit_times, l.fd_amount,
            d.pct_chg AS daily_pct_chg
        FROM {TABLE} l
        LEFT JOIN ods_stock_detail_di d
            ON d.trade_date = l.trade_date AND d.ts_code = l.ts_code
        WHERE l.trade_date = :td AND l.`limit` = 'U'
        ORDER BY l.limit_times IS NULL, l.limit_times DESC, l.pct_chg DESC, l.ts_code
        """,
        {"td": td},
    )

    buckets: dict[int, list[dict]] = {lv: [] for lv, _ in LADDER_LEVELS}
    for r in rows:
        item = serialize_row(r)
        if item.get("pct_chg") is None and item.get("daily_pct_chg") is not None:
            item["pct_chg"] = item["daily_pct_chg"]
        item["stat_text"] = _format_stat(item)
        item["board_level"] = _bucket_level(item.get("limit_times"))
        buckets[item["board_level"]].append(item)

    groups = []
    total = 0
    for level, label in LADDER_LEVELS:
        items = buckets.get(level, [])
        total += len(items)
        groups.append({"level": level, "label": label, "count": len(items), "items": items})

    return {
        "trade_date": td,
        "total": total,
        "groups": groups,
    }
