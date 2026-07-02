"""东财行业/概念板块列表与成分股（类东财板块页）。"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from functools import lru_cache
from typing import Any

from app.db import fetch_all_stock, fetch_one_stock
from app.dc_query_util import latest_trade_date_from_table, list_trade_dates_from_table, resolve_trade_date

FUND_TABLE = "dwm_dc_industry_fund_flow_di"
HEAT_TABLE = "dwm_dc_industry_market_heat_di"
DRAGON_SUMMARY = "dwm_sector_dragon_summary_di"
DEFAULT_CONTENT_TYPES = ("行业", "概念")


def _serialize(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()[:10]
    if isinstance(value, Decimal):
        return float(value)
    return value


def _serialize_row(row: dict) -> dict:
    return {k: _serialize(v) for k, v in row.items()}


def _board_code_variants(industry_code: str) -> list[str]:
    code = industry_code.strip()
    if code.endswith(".DC"):
        return [code, code[:-3]]
    return [code, f"{code}.DC"]


def latest_trade_date() -> str | None:
    return latest_trade_date_from_table(FUND_TABLE, fallback_table="ods_trading_day")


def list_trade_dates(limit: int = 90) -> list[str]:
    dates = list_trade_dates_from_table(FUND_TABLE, limit)
    if dates:
        return dates
    return list_trade_dates_from_table("ods_trading_day", limit)


def _resolve_trade_date(trade_date: str | None) -> str:
    return resolve_trade_date(
        trade_date,
        table=FUND_TABLE,
        empty_msg="暂无板块数据，请先运行 run_dwm_dc_industry_fund_flow",
    )


def _format_sector_row(r: dict) -> dict:
    item = _serialize_row(r)
    net = item.get("net_amount")
    item["net_amount_yi"] = round(float(net) / 1e8, 2) if net is not None else None
    amt = item.get("board_amount")
    item["board_amount_yi"] = round(float(amt) / 1e8, 2) if amt is not None else None
    mv = item.get("total_mv")
    item["total_mv_yi"] = round(float(mv) / 10000, 2) if mv is not None else None
    up = item.get("up_num")
    down = item.get("down_num")
    item["up_down"] = float(up) if up is not None and down is not None else None
    return item


def get_sector_list(
    trade_date: str | None = None,
    content_type: str = "行业",
    keyword: str | None = None,
    limit: int = 500,
    industry_codes: list[str] | None = None,
) -> dict[str, Any]:
    td = _resolve_trade_date(trade_date)
    limit = max(1, min(limit, 1000))
    params: dict[str, Any] = {"td": td}
    if content_type in (None, "", "全部"):
        ct_sql = " AND ff.content_type IN ('行业', '概念')"
        ct_label = "全部"
    else:
        if content_type not in DEFAULT_CONTENT_TYPES:
            content_type = "行业"
        ct_sql = " AND ff.content_type = :ct"
        params["ct"] = content_type
        ct_label = content_type
    kw_sql = ""
    if keyword and keyword.strip():
        kw_sql = " AND (ff.industry_name LIKE :kw OR ff.industry_code LIKE :kw)"
        params["kw"] = f"%{keyword.strip()}%"

    codes_sql = ""
    if industry_codes:
        codes = [c.strip() for c in industry_codes if c and c.strip()]
        if codes:
            codes_sql = " AND ff.industry_code IN (" + ", ".join(f":ic{i}" for i in range(len(codes))) + ")"
            params.update({f"ic{i}": c for i, c in enumerate(codes)})

    rows = fetch_all_stock(
        f"""
        SELECT
            ff.trade_date, ff.content_type, ff.industry_code, ff.industry_name,
            ff.pct_change, ff.net_amount, ff.net_amount_rate, ff.board_amount,
            ff.dc_rank, ff.elg_net_ratio,
            COALESCE(daily.turnover_rate, idx.turnover_rate, mh.turnover_rate) AS turnover_rate,
            idx.up_num, idx.down_num,
            idx.dc_leading, idx.leading_code, idx.leading_pct,
            idx.total_mv,
            mh.constituent_cnt, mh.up_ratio, mh.limit_up_cnt,
            ds.leader_composite_name, ds.leader_composite_ts,
            ds.leader_fund_name, ds.leader_trend_name
        FROM {FUND_TABLE} ff
        LEFT JOIN ods_dc_index_di idx
            ON idx.trade_date = ff.trade_date AND idx.ts_code = ff.industry_code
        LEFT JOIN ods_dc_daily_di daily
            ON daily.trade_date = ff.trade_date AND daily.ts_code = ff.industry_code
        LEFT JOIN {HEAT_TABLE} mh
            ON mh.trade_date = ff.trade_date AND mh.industry_code = ff.industry_code
        LEFT JOIN {DRAGON_SUMMARY} ds
            ON ds.trade_date = ff.trade_date
           AND ds.industry_code = ff.industry_code
           AND ds.score_mode = 'mvp'
        WHERE ff.trade_date = :td
          {ct_sql}
          {kw_sql}
          {codes_sql}
        ORDER BY ff.pct_change IS NULL, ff.pct_change DESC, ff.industry_name
        LIMIT {limit}
        """,
        params,
    )

    items = [_format_sector_row(r) for r in rows]

    return {
        "trade_date": td,
        "content_type": ct_label,
        "sort": "pct_change",
        "order": "desc",
        "items": items,
    }


def _resolve_member_snapshot(trade_date: str, industry_code: str) -> tuple[str, str] | None:
    codes = _board_code_variants(industry_code)
    placeholders = ", ".join(f":c{i}" for i in range(len(codes)))
    params = {"td": trade_date, **{f"c{i}": c for i, c in enumerate(codes)}}
    row = fetch_one_stock(
        f"""
        SELECT ts_code, trade_date AS member_date
        FROM ods_dc_member_di
        WHERE trade_date <= :td AND ts_code IN ({placeholders})
        ORDER BY trade_date DESC
        LIMIT 1
        """,
        params,
    )
    if not row:
        return None
    return str(row["ts_code"]), str(_serialize(row["member_date"]))


def get_sector_members(
    industry_code: str,
    trade_date: str | None = None,
    limit: int = 500,
) -> dict[str, Any]:
    if not industry_code or not industry_code.strip():
        raise ValueError("industry_code 必填")
    code = industry_code.strip()
    td = _resolve_trade_date(trade_date)
    limit = max(1, min(limit, 2000))

    header = fetch_one_stock(
        f"""
        SELECT industry_name, content_type
        FROM {FUND_TABLE}
        WHERE trade_date = :td AND industry_code = :ic
        LIMIT 1
        """,
        {"td": td, "ic": code},
    )
    snap = _resolve_member_snapshot(td, code)
    if not snap:
        raise ValueError(f"板块 {code} 暂无成分股数据")
    board_code, member_date = snap
    codes = _board_code_variants(board_code)
    placeholders = ", ".join(f":c{i}" for i in range(len(codes)))

    rows = fetch_all_stock(
        f"""
        SELECT
            m.con_code AS ts_code,
            m.name AS stock_name,
            d.pct_chg,
            d.close,
            d.amount,
            d.vol,
            db.turnover_rate,
            db.pe_ttm,
            db.total_mv,
            mf.net_mf_amount
        FROM ods_dc_member_di m
        LEFT JOIN ods_stock_detail_di d
            ON d.trade_date = :td AND d.ts_code = m.con_code
        LEFT JOIN ods_daily_basic_di db
            ON db.trade_date = :td AND db.ts_code = m.con_code
        LEFT JOIN ods_stock_fund_flow_di mf
            ON mf.trade_date = :td AND mf.ts_code = m.con_code
        WHERE m.trade_date = :member_date
          AND m.ts_code IN ({placeholders})
        ORDER BY d.pct_chg IS NULL, d.pct_chg DESC, m.name
        LIMIT {limit}
        """,
        {"td": td, "member_date": member_date, **{f"c{i}": c for i, c in enumerate(codes)}},
    )

    items = []
    for r in rows:
        item = _serialize_row(r)
        amt = item.get("amount")
        item["amount_yi"] = round(float(amt) / 100000, 2) if amt is not None else None
        net = item.get("net_mf_amount")
        item["net_mf_yi"] = round(float(net) / 10000, 2) if net is not None else None
        mv = item.get("total_mv")
        item["total_mv_yi"] = round(float(mv) / 10000, 2) if mv is not None else None
        items.append(item)

    return {
        "trade_date": td,
        "member_date": member_date,
        "industry_code": code,
        "industry_name": header["industry_name"] if header else None,
        "content_type": header.get("content_type") if header else None,
        "sort": "pct_chg",
        "order": "desc",
        "items": items,
    }


def lookup_board(trade_date: str | None, keyword: str) -> list[dict]:
    """自选/搜索：按名称或代码查板块。"""
    if not keyword or not keyword.strip():
        return []
    td = _resolve_trade_date(trade_date)
    kw = f"%{keyword.strip()}%"
    rows = fetch_all_stock(
        f"""
        SELECT industry_code, industry_name, content_type, pct_change, net_amount
        FROM {FUND_TABLE}
        WHERE trade_date = :td
          AND content_type IN ('行业', '概念')
          AND (industry_name LIKE :kw OR industry_code LIKE :kw)
        ORDER BY pct_change DESC
        LIMIT 20
        """,
        {"td": td, "kw": kw},
    )
    return [_serialize_row(r) for r in rows]


@lru_cache(maxsize=64)
def _latest_dc_member_date(trade_date: str) -> str | None:
    row = fetch_one_stock(
        """
        SELECT MAX(trade_date) AS d
        FROM ods_dc_member_di
        WHERE trade_date <= :td
        """,
        {"td": trade_date},
    )
    return _serialize(row["d"]) if row and row.get("d") else None


def lookup_stock(trade_date: str | None, keyword: str) -> list[dict]:
    """自选/搜索：按名称或代码查个股（仅最新成分股快照 + 当日涨跌停，不做行情 JOIN）。"""
    if not keyword or not keyword.strip():
        return []
    td = _resolve_trade_date(trade_date)
    raw = keyword.strip()
    kw = f"%{raw}%"
    member_date = _latest_dc_member_date(td)
    params: dict[str, Any] = {"td": td, "kw": kw}
    unions: list[str] = []

    if member_date:
        params["member_date"] = member_date
        unions.append(
            """
            SELECT con_code AS ts_code, name AS stock_name
            FROM ods_dc_member_di
            WHERE trade_date = :member_date
              AND (con_code LIKE :kw OR name LIKE :kw)
            LIMIT 40
            """
        )

    unions.append(
        """
        SELECT ts_code, name AS stock_name
        FROM ods_limit_list_di
        WHERE trade_date = :td
          AND (ts_code LIKE :kw OR name LIKE :kw)
        LIMIT 40
        """
    )

    rows = fetch_all_stock(
        f"""
        SELECT ts_code, MAX(stock_name) AS stock_name
        FROM (
            {" UNION ALL ".join(unions)}
        ) u
        WHERE ts_code IS NOT NULL AND ts_code != ''
        GROUP BY ts_code
        ORDER BY stock_name
        LIMIT 20
        """,
        params,
    )
    return [_serialize_row(r) for r in rows]
