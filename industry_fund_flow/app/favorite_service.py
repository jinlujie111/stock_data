"""用户板块/股票自选（data_industry 库）。"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from app.db import execute, fetch_all, fetch_all_stock, fetch_one, fetch_one_stock
from app import sector_service as sec_svc

BOARD_TABLE = "app_user_board_favorite"
STOCK_TABLE = "app_user_stock_favorite"


def _serialize(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()[:10]
    if isinstance(value, Decimal):
        return float(value)
    return value


def _serialize_row(row: dict) -> dict:
    return {k: _serialize(v) for k, v in row.items()}


def list_board_favorites(user_id: int, trade_date: str | None = None) -> list[dict]:
    rows = fetch_all(
        f"""
        SELECT id, industry_code, industry_name, content_type, created_at
        FROM {BOARD_TABLE}
        WHERE user_id = :uid
        ORDER BY created_at DESC
        """,
        {"uid": user_id},
    )
    if not rows or not trade_date:
        return [_serialize_row(r) for r in rows]

    codes = [r["industry_code"] for r in rows]
    placeholders = ", ".join(f":c{i}" for i in range(len(codes)))
    params = {"td": trade_date, **{f"c{i}": c for i, c in enumerate(codes)}}
    quotes = fetch_all_stock(
        f"""
        SELECT industry_code, industry_name, content_type, pct_change, net_amount
        FROM dwm_dc_industry_fund_flow_di
        WHERE trade_date = :td AND industry_code IN ({placeholders})
        """,
        params,
    )
    qmap = {r["industry_code"]: _serialize_row(r) for r in quotes}
    out = []
    for r in rows:
        item = _serialize_row(r)
        q = qmap.get(r["industry_code"], {})
        item["pct_change"] = q.get("pct_change")
        net = q.get("net_amount")
        item["net_amount_yi"] = round(float(net) / 1e8, 2) if net is not None else None
        if q.get("industry_name"):
            item["industry_name"] = q["industry_name"]
        if q.get("content_type"):
            item["content_type"] = q["content_type"]
        out.append(item)
    return out


def add_board_favorite(
    user_id: int,
    industry_code: str,
    industry_name: str | None = None,
    content_type: str | None = None,
) -> dict:
    if not industry_code or not industry_code.strip():
        raise ValueError("industry_code 必填")
    code = industry_code.strip()
    execute(
        f"""
        INSERT INTO {BOARD_TABLE} (user_id, industry_code, industry_name, content_type)
        VALUES (:uid, :ic, :name, :ct)
        ON DUPLICATE KEY UPDATE
            industry_name = COALESCE(VALUES(industry_name), industry_name),
            content_type = COALESCE(VALUES(content_type), content_type)
        """,
        {
            "uid": user_id,
            "ic": code,
            "name": industry_name,
            "ct": content_type,
        },
    )
    row = fetch_one(
        f"SELECT * FROM {BOARD_TABLE} WHERE user_id = :uid AND industry_code = :ic",
        {"uid": user_id, "ic": code},
    )
    return _serialize_row(row) if row else {"industry_code": code}


def remove_board_favorite(user_id: int, industry_code: str) -> bool:
    n = execute(
        f"DELETE FROM {BOARD_TABLE} WHERE user_id = :uid AND industry_code = :ic",
        {"uid": user_id, "ic": industry_code.strip()},
    )
    return n > 0


def _favorite_board_codes(user_id: int) -> list[str]:
    rows = fetch_all(
        f"SELECT industry_code FROM {BOARD_TABLE} WHERE user_id = :uid ORDER BY created_at DESC",
        {"uid": user_id},
    )
    return [r["industry_code"] for r in rows]


def get_board_favorites_table(
    user_id: int,
    trade_date: str | None,
    content_type: str | None = "全部",
    industry_codes: list[str] | None = None,
) -> dict[str, Any]:
    fav_codes = _favorite_board_codes(user_id)
    if industry_codes:
        allow = {c.strip() for c in industry_codes if c and c.strip()}
        fav_codes = [c for c in fav_codes if c in allow]
    if not fav_codes:
        td = trade_date or sec_svc.latest_trade_date()
        return {
            "trade_date": td,
            "content_type": content_type,
            "sort": "pct_change",
            "order": "desc",
            "items": [],
        }
    return sec_svc.get_sector_list(
        trade_date,
        content_type,
        keyword=None,
        limit=1000,
        industry_codes=fav_codes,
    )


def _trading_dates_up_to(end_date: str, limit: int) -> list[str]:
    rows = fetch_all_stock(
        f"""
        SELECT trade_date AS d
        FROM ods_trading_day
        WHERE trade_date <= :end_date
        ORDER BY trade_date DESC
        LIMIT {int(limit)}
        """,
        {"end_date": end_date},
    )
    return [_serialize(r["d"]) for r in rows]


def _ytd_start_trade_date(trade_date: str) -> str | None:
    year = trade_date[:4]
    row = fetch_one_stock(
        """
        SELECT MIN(trade_date) AS d
        FROM ods_trading_day
        WHERE trade_date >= :ys AND trade_date <= :td
        """,
        {"ys": f"{year}-01-01", "td": trade_date},
    )
    return _serialize(row["d"]) if row and row.get("d") else None


def list_stock_favorites(user_id: int, trade_date: str | None = None) -> list[dict]:
    rows = fetch_all(
        f"""
        SELECT id, ts_code, stock_name, created_at
        FROM {STOCK_TABLE}
        WHERE user_id = :uid
        ORDER BY created_at DESC
        """,
        {"uid": user_id},
    )
    if not rows:
        return []

    td = trade_date if trade_date else sec_svc.latest_trade_date()
    if not td:
        return [_serialize_row(r) for r in rows]
    td = td if isinstance(td, str) else _serialize(td)
    codes = [r["ts_code"] for r in rows]
    placeholders = ", ".join(f":c{i}" for i in range(len(codes)))
    params: dict[str, Any] = {"td": td, **{f"c{i}": c for i, c in enumerate(codes)}}

    dates_5 = _trading_dates_up_to(td, 5)
    dates_20 = _trading_dates_up_to(td, 20)
    ytd_start = _ytd_start_trade_date(td)

    mf5_sql = ""
    mf20_sql = ""
    if dates_5:
        d5p = ", ".join(f":d5{i}" for i in range(len(dates_5)))
        mf5_sql = f"""
        LEFT JOIN (
            SELECT ts_code, SUM(net_mf_amount) AS net_mf_5d
            FROM ods_stock_fund_flow_di
            WHERE trade_date IN ({d5p})
            GROUP BY ts_code
        ) mf5 ON mf5.ts_code = f.ts_code
        """
        params.update({f"d5{i}": d for i, d in enumerate(dates_5)})
    if dates_20:
        d20p = ", ".join(f":d20{i}" for i in range(len(dates_20)))
        mf20_sql = f"""
        LEFT JOIN (
            SELECT ts_code, SUM(net_mf_amount) AS net_mf_20d
            FROM ods_stock_fund_flow_di
            WHERE trade_date IN ({d20p})
            GROUP BY ts_code
        ) mf20 ON mf20.ts_code = f.ts_code
        """
        params.update({f"d20{i}": d for i, d in enumerate(dates_20)})

    ytd_join = ""
    if ytd_start:
        ytd_join = "LEFT JOIN ods_stock_detail_di ytd ON ytd.trade_date = :ytd_start AND ytd.ts_code = f.ts_code"
        params["ytd_start"] = ytd_start

    quote_rows = fetch_all_stock(
        f"""
        SELECT
            f.ts_code,
            d.close,
            d.pct_chg,
            d.vol,
            d.amount,
            db.total_mv,
            mf.net_mf_amount AS net_mf_today,
            mf5.net_mf_5d,
            mf20.net_mf_20d,
            ytd.close AS ytd_base_close
        FROM (
            SELECT ts_code FROM ({' UNION '.join(f'SELECT :c{i} AS ts_code' for i in range(len(codes)))}) f
        ) f
        LEFT JOIN ods_stock_detail_di d ON d.trade_date = :td AND d.ts_code = f.ts_code
        LEFT JOIN ods_daily_basic_di db ON db.trade_date = :td AND db.ts_code = f.ts_code
        LEFT JOIN ods_stock_fund_flow_di mf ON mf.trade_date = :td AND mf.ts_code = f.ts_code
        {mf5_sql}
        {mf20_sql}
        {ytd_join}
        """,
        params,
    )
    qmap = {_serialize_row(r)["ts_code"]: _serialize_row(r) for r in quote_rows}
    out = []
    for r in rows:
        item = _serialize_row(r)
        q = qmap.get(r["ts_code"], {})
        item["close"] = q.get("close")
        item["pct_chg"] = q.get("pct_chg")
        vol = q.get("vol")
        item["vol_wan"] = round(float(vol) / 10000, 2) if vol is not None else None
        amt = q.get("amount")
        item["amount_yi"] = round(float(amt) / 100000, 2) if amt is not None else None
        mv = q.get("total_mv")
        item["total_mv_yi"] = round(float(mv) / 10000, 2) if mv is not None else None
        net_t = q.get("net_mf_today")
        item["net_mf_today_yi"] = round(float(net_t) / 10000, 2) if net_t is not None else None
        net5 = q.get("net_mf_5d")
        item["net_mf_5d_yi"] = round(float(net5) / 10000, 2) if net5 is not None else None
        net20 = q.get("net_mf_20d")
        item["net_mf_20d_yi"] = round(float(net20) / 10000, 2) if net20 is not None else None
        close_now = q.get("close")
        ytd_base = q.get("ytd_base_close")
        if close_now is not None and ytd_base not in (None, 0):
            item["ytd_pct"] = round((float(close_now) - float(ytd_base)) / float(ytd_base) * 100, 2)
        else:
            item["ytd_pct"] = None
        out.append(item)
    return out


def add_stock_favorite(user_id: int, ts_code: str, stock_name: str | None = None) -> dict:
    if not ts_code or not ts_code.strip():
        raise ValueError("ts_code 必填")
    code = ts_code.strip()
    execute(
        f"""
        INSERT INTO {STOCK_TABLE} (user_id, ts_code, stock_name)
        VALUES (:uid, :tc, :name)
        ON DUPLICATE KEY UPDATE stock_name = COALESCE(VALUES(stock_name), stock_name)
        """,
        {"uid": user_id, "tc": code, "name": stock_name},
    )
    row = fetch_one(
        f"SELECT * FROM {STOCK_TABLE} WHERE user_id = :uid AND ts_code = :tc",
        {"uid": user_id, "tc": code},
    )
    return _serialize_row(row) if row else {"ts_code": code}


def remove_stock_favorite(user_id: int, ts_code: str) -> bool:
    n = execute(
        f"DELETE FROM {STOCK_TABLE} WHERE user_id = :uid AND ts_code = :tc",
        {"uid": user_id, "tc": ts_code.strip()},
    )
    return n > 0
