"""板块/个股 K 线历史（读 ods_dc_daily_di / ods_stock_detail_di）。"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from app.db import fetch_all_stock, fetch_one_stock
from app.dc_query_util import resolve_trade_date
from app.indicator_service import compute_all_levels
from app.sector_service import FUND_TABLE, _board_code_variants, _serialize_row

BOARD_DAILY = "ods_dc_daily_di"
BOARD_INDEX = "ods_dc_index_di"
STOCK_DAILY = "ods_stock_detail_di"
STOCK_BASIC = "ods_daily_basic_di"
CYQ_CHIPS = "ods_cyq_chips_di"


def _serialize(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()[:10]
    if isinstance(value, Decimal):
        return float(value)
    return value


def _resolve_end_date(trade_date: str | None) -> str:
    return resolve_trade_date(
        trade_date,
        table=FUND_TABLE,
        empty_msg="暂无板块数据，请先运行 run_dwm_dc_industry_fund_flow",
    )


def _fetch_board_bars(codes: list[str], end_date: str, days: int) -> list[dict]:
    placeholders = ", ".join(f":c{i}" for i in range(len(codes)))
    params: dict[str, Any] = {"end": end_date, **{f"c{i}": c for i, c in enumerate(codes)}}
    rows = fetch_all_stock(
        f"""
        SELECT trade_date, open, high, low, close, pct_change, vol, amount, turnover_rate
        FROM {BOARD_DAILY}
        WHERE ts_code IN ({placeholders}) AND trade_date <= :end
        ORDER BY trade_date DESC
        LIMIT {days}
        """,
        params,
    )
    if not rows:
        return []
    by_date: dict[str, dict] = {}
    for r in rows:
        td = _serialize(r["trade_date"])
        if td not in by_date:
            by_date[td] = _serialize_row(r)
    return [by_date[d] for d in sorted(by_date.keys())]


def _fetch_stock_bars(ts_code: str, end_date: str, days: int) -> list[dict]:
    rows = fetch_all_stock(
        f"""
        SELECT trade_date, open, high, low, close, pre_close, pct_chg, vol, amount
        FROM {STOCK_DAILY}
        WHERE ts_code = :tc AND trade_date <= :end
        ORDER BY trade_date DESC
        LIMIT {days}
        """,
        {"tc": ts_code.strip(), "end": end_date},
    )
    bars = [_serialize_row(r) for r in reversed(rows)]
    return bars


def _board_snapshot(codes: list[str], end_date: str) -> dict | None:
    placeholders = ", ".join(f":c{i}" for i in range(len(codes)))
    params: dict[str, Any] = {"end": end_date, **{f"c{i}": c for i, c in enumerate(codes)}}
    row = fetch_one_stock(
        f"""
        SELECT
            d.trade_date, d.ts_code, d.open, d.high, d.low, d.close, d.pct_change,
            d.vol, d.amount, d.turnover_rate,
            idx.dc_name AS industry_name, idx.total_mv,
            ff.industry_name AS fund_name, ff.pct_change AS fund_pct
        FROM {BOARD_DAILY} d
        LEFT JOIN {BOARD_INDEX} idx
            ON idx.trade_date = d.trade_date AND idx.ts_code = d.ts_code
        LEFT JOIN {FUND_TABLE} ff
            ON ff.trade_date = d.trade_date AND ff.industry_code = d.ts_code
        WHERE d.trade_date = :end AND d.ts_code IN ({placeholders})
        LIMIT 1
        """,
        params,
    )
    if not row:
        return None
    item = _serialize_row(row)
    amt = item.get("amount")
    item["amount_yi"] = round(float(amt) / 1e8, 2) if amt is not None else None
    vol = item.get("vol")
    item["vol_wan_shou"] = round(float(vol) / 1e6, 2) if vol is not None else None
    mv = item.get("total_mv")
    item["total_mv_yi"] = round(float(mv) / 10000, 2) if mv is not None else None
    return item


def _stock_snapshot(ts_code: str, end_date: str) -> dict | None:
    row = fetch_one_stock(
        f"""
        SELECT
            d.trade_date, d.ts_code, d.open, d.high, d.low, d.close, d.pre_close,
            d.pct_chg, d.vol, d.amount,
            db.turnover_rate, db.pe_ttm, db.total_mv, db.circ_mv
        FROM {STOCK_DAILY} d
        LEFT JOIN {STOCK_BASIC} db
            ON db.trade_date = d.trade_date AND db.ts_code = d.ts_code
        WHERE d.trade_date = :end AND d.ts_code = :tc
        LIMIT 1
        """,
        {"end": end_date, "tc": ts_code.strip()},
    )
    if not row:
        return None
    item = _serialize_row(row)
    amt = item.get("amount")
    item["amount_yi"] = round(float(amt) / 100000, 2) if amt is not None else None
    vol = item.get("vol")
    item["vol_wan_shou"] = round(float(vol) / 10000, 2) if vol is not None else None
    mv = item.get("total_mv")
    item["total_mv_yi"] = round(float(mv) / 10000, 2) if mv is not None else None
    circ = item.get("circ_mv")
    item["circ_mv_yi"] = round(float(circ) / 10000, 2) if circ is not None else None
    return item


def _fetch_cyq_chips(ts_code: str, trade_date: str) -> list[dict]:
    rows = fetch_all_stock(
        f"""
        SELECT price, percent
        FROM {CYQ_CHIPS}
        WHERE ts_code = :tc AND trade_date = :td
        ORDER BY price
        """,
        {"tc": ts_code.strip(), "td": trade_date},
    )
    return [_serialize_row(r) for r in rows]


def _attach_pre_close(bars: list[dict], pct_key: str) -> None:
    for i, bar in enumerate(bars):
        if i == 0:
            close = bar.get("close")
            pct = bar.get(pct_key)
            if close is not None and pct is not None:
                denom = 1 + float(pct) / 100
                bar["pre_close"] = round(float(close) / denom, 4) if denom else None
            else:
                bar["pre_close"] = None
        else:
            bar["pre_close"] = bars[i - 1].get("close")


def get_board_kline(
    industry_code: str,
    trade_date: str | None = None,
    days: int = 120,
) -> dict[str, Any]:
    if not industry_code or not industry_code.strip():
        raise ValueError("industry_code 必填")
    code = industry_code.strip()
    end = _resolve_end_date(trade_date)
    days = max(20, min(days, 365))
    codes = _board_code_variants(code)
    bars = _fetch_board_bars(codes, end, days)
    if not bars:
        raise ValueError(f"板块 {code} 暂无 K 线数据")
    _attach_pre_close(bars, "pct_change")
    snap = _board_snapshot(codes, end) or {}
    if bars:
        last = bars[-1]
        if snap.get("close") is None:
            snap["close"] = last.get("close")
        if snap.get("pre_close") is None:
            snap["pre_close"] = last.get("pre_close")
    name = snap.get("industry_name") or snap.get("fund_name")
    header = fetch_one_stock(
        f"""
        SELECT industry_name, content_type
        FROM {FUND_TABLE}
        WHERE trade_date = :end AND industry_code = :ic
        LIMIT 1
        """,
        {"end": end, "ic": code},
    )
    if header:
        name = name or header.get("industry_name")
    display_code = code.replace(".DC", "") if code.endswith(".DC") else code
    payload = {
        "kind": "board",
        "code": code,
        "display_code": display_code,
        "name": name or display_code,
        "content_type": header.get("content_type") if header else None,
        "trade_date": end,
        "snapshot": snap,
        "bars": bars,
    }
    payload["levels"] = compute_all_levels(bars)
    return payload


def get_stock_kline(
    ts_code: str,
    trade_date: str | None = None,
    days: int = 120,
) -> dict[str, Any]:
    if not ts_code or not ts_code.strip():
        raise ValueError("ts_code 必填")
    code = ts_code.strip()
    end = _resolve_end_date(trade_date)
    days = max(20, min(days, 365))
    bars = _fetch_stock_bars(code, end, days)
    if not bars:
        raise ValueError(f"股票 {code} 暂无 K 线数据")
    snap = _stock_snapshot(code, end) or (bars[-1] if bars else {})
    name_row = fetch_one_stock(
        f"""
        SELECT MAX(name) AS stock_name
        FROM ods_dc_member_di
        WHERE con_code = :tc AND trade_date <= :end
        """,
        {"tc": code, "end": end},
    )
    stock_name = name_row.get("stock_name") if name_row else None
    cyq_rows = _fetch_cyq_chips(code, end)
    payload = {
        "kind": "stock",
        "code": code,
        "display_code": code,
        "name": stock_name or code,
        "trade_date": end,
        "snapshot": snap,
        "bars": bars,
        "cyq_chips": cyq_rows,
    }
    payload["levels"] = compute_all_levels(bars, cyq_rows=cyq_rows or None)
    return payload
