"""全市场广度 DWM 查询（dwm_market_breadth_di）。

口径说明：本模块仅透传 DWM 结果，不改写 DWM 侧统计口径。
- BJ（北交所）/ ST 等家数是否纳入统计，由 DWM 层 SQL 决定（那是独立负责的文件）；
  本层不做家数口径的增删，只在此注明当前依赖上游口径。
- 新增“家数一致性”轻校验（advance+decline+flat 是否等于 total_cnt），
  不一致只记 warning 并标记，不修改任何 DWM SQL。
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from app.db import fetch_all_stock, fetch_one_stock

logger = logging.getLogger(__name__)

TABLE = "dwm_market_breadth_di"

METRICS: list[dict[str, str]] = [
    {"key": "trade_date", "label": "交易日期", "fmt": "text"},
    {"key": "total_cnt", "label": "参与统计家数", "fmt": "int"},
    {"key": "advance_cnt", "label": "上涨家数", "fmt": "int"},
    {"key": "decline_cnt", "label": "下跌家数", "fmt": "int"},
    {"key": "flat_cnt", "label": "平盘家数", "fmt": "int"},
    {"key": "advance_ratio", "label": "上涨占比", "fmt": "pct"},
    {"key": "limit_up_cnt", "label": "涨停家数", "fmt": "int"},
    {"key": "limit_down_cnt", "label": "跌停家数", "fmt": "int"},
]


def _serialize(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()[:10]
    if isinstance(value, Decimal):
        return float(value)
    return value


def _serialize_row(row: dict) -> dict:
    return {k: _serialize(v) for k, v in row.items()}


def _check_breadth_consistency(data: dict) -> bool | None:
    """校验 上涨+下跌+平盘 是否等于参与统计家数。

    返回 True/False（可校验时），或 None（缺字段无法校验）。
    不一致时记 warning，供排查上游口径（如 BJ/ST 是否纳入 total_cnt）。
    """
    parts = [data.get("advance_cnt"), data.get("decline_cnt"), data.get("flat_cnt")]
    total = data.get("total_cnt")
    if total is None or any(p is None for p in parts):
        return None
    summed = sum(int(p) for p in parts)
    ok = summed == int(total)
    if not ok:
        logger.warning(
            "market_breadth 家数不一致 trade_date=%s: advance+decline+flat=%s total_cnt=%s",
            data.get("trade_date"),
            summed,
            int(total),
        )
    return ok


def parse_trade_date(raw: str | None) -> str | None:
    if not raw:
        return None
    s = raw.strip().replace("-", "")
    if len(s) != 8 or not s.isdigit():
        raise ValueError("trade_date 格式应为 YYYY-MM-DD 或 YYYYMMDD")
    return f"{s[0:4]}-{s[4:6]}-{s[6:8]}"


def latest_trade_date() -> str | None:
    row = fetch_one_stock(f"SELECT MAX(trade_date) AS d FROM {TABLE}")
    if not row or not row.get("d"):
        return None
    return _serialize(row["d"])


def list_trade_dates(limit: int = 60) -> list[str]:
    limit = max(1, min(limit, 365))
    rows = fetch_all_stock(
        f"""
        SELECT DISTINCT trade_date AS d
        FROM {TABLE}
        ORDER BY trade_date DESC
        LIMIT {limit}
        """
    )
    return [_serialize(r["d"]) for r in rows]


def get_market_breadth(trade_date: str | None = None) -> dict:
    td = parse_trade_date(trade_date) if trade_date else latest_trade_date()
    if not td:
        return {
            "trade_date": None,
            "metrics": METRICS,
            "data": None,
        }
    row = fetch_one_stock(
        f"""
        SELECT trade_date, total_cnt, advance_cnt, decline_cnt, flat_cnt,
               advance_ratio, limit_up_cnt, limit_down_cnt
        FROM {TABLE}
        WHERE trade_date = :trade_date
        LIMIT 1
        """,
        {"trade_date": td},
    )
    if not row:
        return {
            "trade_date": td,
            "metrics": METRICS,
            "data": None,
        }
    data = _serialize_row(row)
    # 轻校验家数一致性（不改 DWM，仅标记 + warning）
    data["consistency_ok"] = _check_breadth_consistency(data)
    return {
        "trade_date": data.get("trade_date"),
        "metrics": METRICS,
        "data": data,
    }


def get_market_breadth_history(days: int = 30) -> dict:
    """近 N 个交易日涨跌家数序列（按日期升序）。"""
    days = max(1, min(days, 365))
    rows = fetch_all_stock(
        f"""
        SELECT trade_date, advance_cnt, decline_cnt
        FROM {TABLE}
        ORDER BY trade_date DESC
        LIMIT {days}
        """
    )
    items = [_serialize_row(r) for r in reversed(rows)]
    return {"days": days, "items": items}
