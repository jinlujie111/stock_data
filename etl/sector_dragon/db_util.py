"""数据库连接、建表与交易日工具。"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine

from mysql_config import get_engine

EXCLUDED_BOARD_NAMES = {"B股", "B 股"}
EXCLUDED_BOARD_CODES = {"BK0636.DC", "BK0636"}


@dataclass
class DragonConfig:
    score_mode: str = "mvp"
    content_types: tuple[str, ...] = ("行业", "概念")
    fund_window_days: int = 20
    ret_window_days: int = 60
    amount_window_days: int = 20
    rs_cap: float = 3.0
    rs_cap_score: float = 90.0
    min_constituents: int = 3
    w_fund: float = 0.4
    w_rs: float = 0.3
    w_amount: float = 0.2
    w_mv: float = 0.1
    w_np_yoy: float = 0.35
    w_q_yoy: float = 0.25
    w_roe: float = 0.25
    w_upgrade: float = 0.075
    w_forecast_rev: float = 0.075


def parse_trade_date(s: str) -> date:
    s = s.strip().replace("-", "")
    if len(s) != 8:
        raise ValueError(f"invalid trade_date: {s}")
    return datetime.strptime(s, "%Y%m%d").date()


def normalize_con_code(con_code: str) -> str:
    con_code = con_code.strip()
    if not con_code:
        return con_code
    if "." in con_code:
        return con_code
    head = con_code[0]
    if head in "659":
        return f"{con_code}.SH"
    if head in "84":
        return f"{con_code}.BJ"
    return f"{con_code}.SZ"


def get_engine_stock() -> Engine:
    return get_engine()


def ensure_schema(engine: Engine) -> None:
    """表结构以 mysql_tables/stock_data.sql 为准；此处仅种子默认配置。"""
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT IGNORE INTO dwm_dc_sector_dragon_config (
                    config_key, score_mode, content_types, effective_date, is_active
                ) VALUES ('__global__', 'mvp', '行业,概念', CURDATE(), 1)
                """
            )
        )


def load_config(engine: Engine, content_types: list[str]) -> DragonConfig:
    cfg = DragonConfig(content_types=tuple(content_types))
    with engine.connect() as conn:
        row = conn.execute(
            text(
                """
                SELECT score_mode, content_types, fund_window_days, rs_cap, rs_cap_score,
                       min_constituents, mvp_weights
                FROM dwm_dc_sector_dragon_config
                WHERE config_key = '__global__' AND is_active = 1
                ORDER BY effective_date DESC
                LIMIT 1
                """
            )
        ).mappings().first()
    if not row:
        return cfg
    if row.get("fund_window_days"):
        cfg.fund_window_days = int(row["fund_window_days"])
    if row.get("rs_cap") is not None:
        cfg.rs_cap = float(row["rs_cap"])
    if row.get("rs_cap_score") is not None:
        cfg.rs_cap_score = float(row["rs_cap_score"])
    if row.get("min_constituents"):
        cfg.min_constituents = int(row["min_constituents"])
    mw = row.get("mvp_weights")
    if mw:
        import json

        if isinstance(mw, str):
            mw = json.loads(mw)
        cfg.w_fund = float(mw.get("fund", cfg.w_fund))
        cfg.w_rs = float(mw.get("rs", cfg.w_rs))
        cfg.w_amount = float(mw.get("amount_share", cfg.w_amount))
        cfg.w_mv = float(mw.get("mv", cfg.w_mv))
        iw = mw.get("industry")
        if isinstance(iw, dict):
            cfg.w_np_yoy = float(iw.get("np_yoy", cfg.w_np_yoy))
            cfg.w_q_yoy = float(iw.get("q_yoy", cfg.w_q_yoy))
            cfg.w_roe = float(iw.get("roe", cfg.w_roe))
            cfg.w_upgrade = float(iw.get("upgrade", cfg.w_upgrade))
            cfg.w_forecast_rev = float(iw.get("forecast_rev", cfg.w_forecast_rev))
    return cfg


def list_trading_days(engine: Engine, end: date, limit: int) -> list[date]:
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT trade_date FROM ods_trading_day
                WHERE trade_date <= :end
                ORDER BY trade_date DESC
                LIMIT :lim
                """
            ),
            {"end": end, "lim": limit},
        ).fetchall()
    if rows:
        return sorted(r[0] for r in rows)
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT DISTINCT trade_date FROM ods_stock_detail_di
                WHERE trade_date <= :end
                ORDER BY trade_date DESC
                LIMIT :lim
                """
            ),
            {"end": end, "lim": limit},
        ).fetchall()
    return sorted(r[0] for r in rows)


def list_boards(
    engine: Engine,
    trade_date: date,
    content_types: list[str],
    min_constituents: int = 3,
) -> list[dict[str, Any]]:
    """
    从 ods_dc_member_di 枚举板块。
    成分股取 trade_date 向前 60 日内「最近且成分数最多」的一日快照，
    避免当日 dc_member 只同步了部分板块/少量股票导致行业板块被跳过。
    """
    placeholders = ", ".join(f":ct{i}" for i in range(len(content_types)))
    params: dict[str, Any] = {
        "td": trade_date,
        "min_cnt": min_constituents,
    }
    for i, ct in enumerate(content_types):
        params[f"ct{i}"] = ct

    sql_member = f"""
    WITH ff AS (
        SELECT industry_code, industry_name, content_type
        FROM dwm_dc_industry_fund_flow_di
        WHERE trade_date = :td
        UNION
        SELECT industry_code, industry_name, content_type
        FROM ods_industry_fund_flow_di
        WHERE trade_date = :td
    ),
    candidate_dates AS (
        SELECT
            m.ts_code,
            m.trade_date,
            COUNT(DISTINCT m.con_code) AS member_cnt,
            ROW_NUMBER() OVER (
                PARTITION BY m.ts_code
                ORDER BY m.trade_date DESC, COUNT(DISTINCT m.con_code) DESC
            ) AS rn
        FROM ods_dc_member_di m
        WHERE m.trade_date <= :td
          AND m.trade_date >= DATE_SUB(:td, INTERVAL 60 DAY)
        GROUP BY m.ts_code, m.trade_date
    ),
    best_member AS (
        SELECT ts_code, trade_date AS member_date, member_cnt
        FROM candidate_dates
        WHERE rn = 1 AND member_cnt >= :min_cnt
    ),
    idx_latest AS (
        SELECT ts_code, dc_name, idx_type
        FROM (
            SELECT
                ts_code, dc_name, idx_type,
                ROW_NUMBER() OVER (PARTITION BY ts_code ORDER BY trade_date DESC) AS rn
            FROM ods_dc_index_di
            WHERE trade_date <= :td
        ) t
        WHERE rn = 1
    ),
    board_base AS (
        SELECT
            b.ts_code AS industry_code,
            COALESCE(idx.dc_name, ff.industry_name, b.ts_code) AS industry_name,
            CASE
                WHEN idx.idx_type = '行业板块' THEN '行业'
                WHEN idx.idx_type = '概念板块' THEN '概念'
                WHEN idx.idx_type = '地域板块' THEN '地域'
                WHEN ff.content_type IN ('行业', '概念', '地域') THEN ff.content_type
                ELSE NULL
            END AS content_type,
            b.member_date,
            b.member_cnt
        FROM best_member b
        LEFT JOIN idx_latest idx ON b.ts_code = idx.ts_code
        LEFT JOIN ff ON b.ts_code = ff.industry_code
    )
    SELECT industry_code, industry_name, content_type, member_date, member_cnt
    FROM board_base
    WHERE content_type IN ({placeholders})
    ORDER BY content_type, industry_name
    """
    def _is_excluded_board(row: dict[str, Any]) -> bool:
        code = str(row.get("industry_code") or "").strip().upper()
        if code in EXCLUDED_BOARD_CODES:
            return True
        name = str(row.get("industry_name") or "").strip()
        return name in EXCLUDED_BOARD_NAMES

    with engine.connect() as conn:
        rows = conn.execute(text(sql_member), params).mappings().all()
    if rows:
        return [dict(r) for r in rows if not _is_excluded_board(dict(r))]

    # 兜底：资金流 DWM（历史逻辑）
    sql_ff = f"""
    SELECT DISTINCT industry_code, industry_name, content_type
    FROM dwm_dc_industry_fund_flow_di
    WHERE trade_date = :td AND content_type IN ({placeholders})
    ORDER BY content_type, industry_name
    """
    with engine.connect() as conn:
        rows = conn.execute(
            text(sql_ff),
            {k: v for k, v in params.items() if k != "min_cnt"},
        ).mappings().all()
    if rows:
        return [dict(r) for r in rows if not _is_excluded_board(dict(r))]
    sql_fb = f"""
    SELECT DISTINCT industry_code, industry_name, content_type
    FROM ods_industry_fund_flow_di
    WHERE trade_date = :td AND content_type IN ({placeholders})
    ORDER BY content_type, industry_name
    """
    with engine.connect() as conn:
        rows = conn.execute(
            text(sql_fb),
            {k: v for k, v in params.items() if k != "min_cnt"},
        ).mappings().all()
    return [dict(r) for r in rows if not _is_excluded_board(dict(r))]


def _board_code_variants(industry_code: str) -> list[str]:
    codes = [industry_code]
    if industry_code.endswith(".DC"):
        codes.append(industry_code[:-3])
    else:
        codes.append(f"{industry_code}.DC")
    return codes


def load_members(
    engine: Engine,
    trade_date: date,
    industry_code: str,
    member_date: date | None = None,
) -> list[dict[str, str]]:
    """加载成分股；member_date 为成分快照日（可与 trade_date 不同）。"""
    query_date = member_date or trade_date
    for board_code in _board_code_variants(industry_code):
        with engine.connect() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT con_code, name
                    FROM ods_dc_member_di
                    WHERE trade_date = :td AND ts_code = :ic
                    """
                ),
                {"td": query_date, "ic": board_code},
            ).mappings().all()
        if rows:
            out: list[dict[str, str]] = []
            seen: set[str] = set()
            for r in rows:
                code = normalize_con_code(str(r["con_code"]))
                if code in seen:
                    continue
                seen.add(code)
                out.append({"ts_code": code, "stock_name": r.get("name") or ""})
            return out
    return []
