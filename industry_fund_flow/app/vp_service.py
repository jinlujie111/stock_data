"""需求5：板块量价关系（VPA）查询服务。"""
from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from app.db import fetch_all_stock, fetch_one_stock
from app.dc_service import parse_trade_date

SCORE_TABLE = "dwm_industry_vp_score_di"
AGG_TABLE = "dwm_industry_vp_agg_di"
FACTOR_TABLE = "dwm_stock_vp_factor_di"


def _serialize(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()[:10]
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (bytes, bytearray)):
        return value.decode()
    return value


def _serialize_row(row: dict) -> dict:
    out = {k: _serialize(v) for k, v in row.items()}
    if isinstance(out.get("detail_json"), str):
        try:
            out["detail_json"] = json.loads(out["detail_json"])
        except json.JSONDecodeError:
            pass
    return out


def latest_trade_date() -> str | None:
    row = fetch_one_stock(f"SELECT MAX(trade_date) AS d FROM {SCORE_TABLE}")
    return _serialize(row["d"]) if row and row.get("d") else None


def list_trade_dates(limit: int = 60) -> list[str]:
    limit = max(1, min(limit, 365))
    rows = fetch_all_stock(
        f"""
        SELECT DISTINCT trade_date AS d
        FROM {SCORE_TABLE}
        ORDER BY d DESC
        LIMIT {limit}
        """
    )
    return [_serialize(r["d"]) for r in rows]


def _resolve_trade_date(trade_date: str | None) -> str:
    td = parse_trade_date(trade_date) if trade_date else None
    if td:
        return td
    latest = latest_trade_date()
    if not latest:
        raise ValueError("暂无量价评分数据，请先运行 run_vp_batch")
    return latest


def _parse_content_types(content_types: str | None) -> list[str]:
    if not content_types or not content_types.strip():
        return ["行业", "概念"]
    return [x.strip() for x in content_types.split(",") if x.strip()]


def rank_industries(
    trade_date: str | None = None,
    *,
    content_types: str | None = "行业,概念",
    window: int = 20,
    top: int = 50,
    sort: str = "vp_score",
) -> dict[str, Any]:
    td = _resolve_trade_date(trade_date)
    ctypes = _parse_content_types(content_types)
    top = max(1, min(top, 200))
    window = max(3, min(window, 120))
    sort_key = sort if sort in ("vp_score", "industry_vol_ratio_20", "breakout_ratio", "amount_streak_days") else "vp_score"

    placeholders = ", ".join(f":ct{i}" for i in range(len(ctypes)))
    params: dict[str, Any] = {"td": td, "w": window, "lim": top}
    for i, ct in enumerate(ctypes):
        params[f"ct{i}"] = ct

    rows = fetch_all_stock(
        f"""
        SELECT
            industry_code, industry_name, content_type, vp_score, vp_status,
            signal_type, industry_vol_ratio_20, rising_ratio, breakout_ratio,
            amount_streak_days, rank_vp, member_cnt,
            score_vol, score_trend, score_continuity, score_breadth, score_breakout
        FROM {SCORE_TABLE}
        WHERE trade_date = :td AND window = :w
          AND content_type IN ({placeholders})
        ORDER BY {sort_key} DESC, rank_vp ASC
        LIMIT :lim
        """,
        params,
    )
    return {
        "trade_date": td,
        "window": window,
        "items": [_serialize_row(r) for r in rows],
    }


def get_industry_detail(
    industry_code: str,
    trade_date: str | None = None,
    *,
    window: int = 20,
) -> dict[str, Any]:
    td = _resolve_trade_date(trade_date)
    window = max(3, min(window, 120))
    score = fetch_one_stock(
        f"""
        SELECT *
        FROM {SCORE_TABLE}
        WHERE trade_date = :td AND industry_code = :ic AND window = :w
        LIMIT 1
        """,
        {"td": td, "ic": industry_code, "w": window},
    )
    if not score:
        raise ValueError(f"未找到板块量价数据: {industry_code} @ {td}")
    agg = fetch_one_stock(
        f"""
        SELECT *
        FROM {AGG_TABLE}
        WHERE trade_date = :td AND industry_code = :ic AND window = :w
        LIMIT 1
        """,
        {"td": td, "ic": industry_code, "w": window},
    )
    history = fetch_all_stock(
        f"""
        SELECT trade_date, vp_score, vp_status, industry_vol_ratio_20, rising_ratio
        FROM {SCORE_TABLE}
        WHERE industry_code = :ic AND window = :w AND trade_date <= :td
        ORDER BY trade_date DESC
        LIMIT 20
        """,
        {"td": td, "ic": industry_code, "w": window},
    )
    return {
        "trade_date": td,
        "window": window,
        "score": _serialize_row(score),
        "agg": _serialize_row(agg) if agg else None,
        "history": [_serialize_row(r) for r in history],
    }


def list_industry_stocks(
    industry_code: str,
    trade_date: str | None = None,
    *,
    window: int = 20,
    limit: int = 100,
    sort: str = "vol_ratio_20",
) -> dict[str, Any]:
    td = _resolve_trade_date(trade_date)
    window = max(3, min(window, 120))
    limit = max(1, min(limit, 500))
    sort_key = sort if sort in ("vol_ratio_20", "vp_pattern_score", "pct_chg", "vol_streak_days") else "vol_ratio_20"

    detail = get_industry_detail(industry_code, td, window=window)
    member_date = td
    rows = fetch_all_stock(
        f"""
        SELECT m.con_code, m.name
        FROM ods_dc_member_di m
        WHERE m.trade_date = :td
          AND (m.ts_code = :ic OR m.ts_code = :ic2)
        """,
        {
            "td": td,
            "ic": industry_code,
            "ic2": industry_code.replace(".DC", "") if industry_code.endswith(".DC") else f"{industry_code}.DC",
        },
    )
    if not rows:
        raise ValueError(f"未找到板块成分: {industry_code}")

    codes: list[str] = []
    names: dict[str, str] = {}
    for r in rows:
        code = r["con_code"]
        if "." not in code:
            head = code[0]
            if head in "659":
                code = f"{code}.SH"
            elif head in "84":
                code = f"{code}.BJ"
            else:
                code = f"{code}.SZ"
        codes.append(code)
        names[code] = r.get("name") or ""

    if not codes:
        return {"trade_date": td, "industry_code": industry_code, "items": []}

    placeholders = ", ".join(f":c{i}" for i in range(len(codes)))
    params: dict[str, Any] = {"td": td, "w": window, "lim": limit}
    for i, c in enumerate(codes):
        params[f"c{i}"] = c

    factors = fetch_all_stock(
        f"""
        SELECT ts_code, close, vol, amount, pct_chg, turnover_rate,
               vol_ratio_20, vol_streak_days, is_breakout_60,
               vp_pattern, vp_pattern_score
        FROM {FACTOR_TABLE}
        WHERE trade_date = :td AND window = :w
          AND ts_code IN ({placeholders})
        ORDER BY {sort_key} DESC
        LIMIT :lim
        """,
        params,
    )
    items = []
    for f in factors:
        row = _serialize_row(f)
        row["stock_name"] = names.get(f["ts_code"], "")
        items.append(row)
    return {
        "trade_date": td,
        "industry_code": industry_code,
        "industry_name": detail["score"].get("industry_name"),
        "window": window,
        "items": items,
    }


def list_signals(
    trade_date: str | None = None,
    *,
    signal_type: str | None = None,
    window: int = 20,
    top: int = 50,
) -> dict[str, Any]:
    td = _resolve_trade_date(trade_date)
    window = max(3, min(window, 120))
    top = max(1, min(top, 200))
    params: dict[str, Any] = {"td": td, "w": window, "lim": top}
    sig_sql = ""
    if signal_type and signal_type.strip():
        sig_sql = " AND signal_type = :sig"
        params["sig"] = signal_type.strip()

    rows = fetch_all_stock(
        f"""
        SELECT industry_code, industry_name, content_type, vp_score, vp_status,
               signal_type, industry_vol_ratio_20, rising_ratio, breakout_ratio,
               amount_streak_days, rank_vp
        FROM {SCORE_TABLE}
        WHERE trade_date = :td AND window = :w
          AND signal_type IS NOT NULL AND signal_type <> 'none'
          {sig_sql}
        ORDER BY vp_score DESC
        LIMIT :lim
        """,
        params,
    )
    return {
        "trade_date": td,
        "window": window,
        "signal_type": signal_type,
        "items": [_serialize_row(r) for r in rows],
    }
