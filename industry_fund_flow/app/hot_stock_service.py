"""东财 App 热榜（ods_dc_hot_di）查询。"""
from __future__ import annotations

from typing import Any

from app.db import fetch_all_stock
from app.dc_query_util import (
    latest_trade_date_from_table,
    list_trade_dates_from_table,
    resolve_trade_date,
    serialize_row,
)

TABLE = "ods_dc_hot_di"
DEFAULT_MARKET = "A股市场"
HOT_TYPES = ("人气榜", "飙升榜")
MARKETS = ("A股市场", "ETF基金", "港股市场", "美股市场")


def latest_trade_date() -> str | None:
    return latest_trade_date_from_table(TABLE)


def list_trade_dates(limit: int = 90) -> list[str]:
    return list_trade_dates_from_table(TABLE, limit)


def _resolve_trade_date(trade_date: str | None) -> str:
    return resolve_trade_date(
        trade_date,
        table=TABLE,
        empty_msg="暂无东财热榜数据，请先运行 run_data_sync 同步 dc_hot",
    )


def get_hot_stocks(
    trade_date: str | None = None,
    hot_type: str = "人气榜",
    market: str = DEFAULT_MARKET,
    limit: int = 100,
) -> dict[str, Any]:
    td = _resolve_trade_date(trade_date)
    if hot_type not in HOT_TYPES:
        hot_type = "人气榜"
    if market not in MARKETS:
        market = DEFAULT_MARKET
    limit = max(1, min(limit, 200))

    rows = fetch_all_stock(
        f"""
        SELECT
            h.trade_date, h.market, h.hot_type, h.dc_rank,
            h.ts_code, h.ts_name, h.pct_change, h.current_price, h.rank_time,
            d.pct_chg, d.close, d.open, d.high, d.low, d.amount, d.vol,
            db.turnover_rate, db.pe_ttm, db.total_mv
        FROM {TABLE} h
        LEFT JOIN ods_stock_detail_di d
            ON d.trade_date = h.trade_date AND d.ts_code = h.ts_code
        LEFT JOIN ods_daily_basic_di db
            ON db.trade_date = h.trade_date AND db.ts_code = h.ts_code
        WHERE h.trade_date = :td
          AND h.market = :market
          AND h.hot_type = :ht
        ORDER BY h.dc_rank IS NULL, h.dc_rank ASC, h.ts_code
        LIMIT {limit}
        """,
        {"td": td, "market": market, "ht": hot_type},
    )

    items = []
    for r in rows:
        item = serialize_row(r)
        pct = item.get("pct_change")
        if pct is None:
            item["pct_change"] = item.get("pct_chg")
        amt = item.get("amount")
        item["amount_yi"] = round(float(amt) / 100000, 2) if amt is not None else None
        price = item.get("current_price")
        if price is None:
            item["current_price"] = item.get("close")
        items.append(item)

    return {
        "trade_date": td,
        "market": market,
        "hot_type": hot_type,
        "sort": "dc_rank",
        "order": "asc",
        "items": items,
    }
