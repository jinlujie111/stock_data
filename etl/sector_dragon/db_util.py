"""数据库连接、建表与交易日工具。"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine

from mysql_config import get_engine


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
    ddl = """
    CREATE TABLE IF NOT EXISTS dwm_sector_stock_dragon_score_di (
        id BIGINT PRIMARY KEY AUTO_INCREMENT,
        trade_date DATE NOT NULL,
        industry_code VARCHAR(32) NOT NULL,
        industry_name VARCHAR(128) NULL,
        content_type VARCHAR(16) NULL,
        ts_code VARCHAR(16) NOT NULL,
        stock_name VARCHAR(64) NULL,
        score_industry DECIMAL(10,2) NULL,
        score_fund DECIMAL(10,2) NULL,
        score_trend DECIMAL(10,2) NULL,
        score_inst DECIMAL(10,2) NULL,
        score_composite DECIMAL(10,2) NULL,
        rank_industry INT NULL,
        rank_fund INT NULL,
        rank_trend INT NULL,
        rank_inst INT NULL,
        rank_composite INT NULL,
        is_industry_leader TINYINT NOT NULL DEFAULT 0,
        is_fund_leader TINYINT NOT NULL DEFAULT 0,
        is_trend_leader TINYINT NOT NULL DEFAULT 0,
        is_inst_leader TINYINT NOT NULL DEFAULT 0,
        is_composite_leader TINYINT NOT NULL DEFAULT 0,
        score_mode VARCHAR(8) NOT NULL DEFAULT 'mvp',
        industry_as_of DATE NULL,
        inst_as_of DATE NULL,
        detail_json JSON NULL,
        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        UNIQUE KEY uk_sector_dragon_score (trade_date, industry_code, ts_code, score_mode)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """
    with engine.begin() as conn:
        conn.execute(text(ddl))
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS sector_dragon_summary_di (
                    id BIGINT PRIMARY KEY AUTO_INCREMENT,
                    trade_date DATE NOT NULL,
                    industry_code VARCHAR(32) NOT NULL,
                    industry_name VARCHAR(128) NULL,
                    content_type VARCHAR(16) NULL,
                    leader_industry_ts VARCHAR(16) NULL,
                    leader_industry_name VARCHAR(64) NULL,
                    leader_fund_ts VARCHAR(16) NULL,
                    leader_fund_name VARCHAR(64) NULL,
                    leader_trend_ts VARCHAR(16) NULL,
                    leader_trend_name VARCHAR(64) NULL,
                    leader_inst_ts VARCHAR(16) NULL,
                    leader_inst_name VARCHAR(64) NULL,
                    leader_composite_ts VARCHAR(16) NULL,
                    leader_composite_name VARCHAR(64) NULL,
                    summary_text TEXT NULL,
                    score_mode VARCHAR(8) NOT NULL DEFAULT 'mvp',
                    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    UNIQUE KEY uk_sector_dragon_summary (trade_date, industry_code, score_mode)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS sector_dragon_config (
                    id BIGINT PRIMARY KEY AUTO_INCREMENT,
                    config_key VARCHAR(64) NOT NULL,
                    score_mode VARCHAR(8) NOT NULL DEFAULT 'mvp',
                    content_types VARCHAR(64) NOT NULL DEFAULT '行业,概念',
                    w_industry DECIMAL(5,4) NOT NULL DEFAULT 0.2000,
                    w_fund DECIMAL(5,4) NOT NULL DEFAULT 0.3500,
                    w_trend DECIMAL(5,4) NOT NULL DEFAULT 0.2500,
                    w_inst DECIMAL(5,4) NOT NULL DEFAULT 0.2000,
                    fund_window_days INT NOT NULL DEFAULT 20,
                    trend_windows JSON NULL,
                    mvp_weights JSON NULL,
                    rs_cap DECIMAL(6,2) NOT NULL DEFAULT 3.00,
                    rs_cap_score DECIMAL(6,2) NOT NULL DEFAULT 90.00,
                    min_constituents INT NOT NULL DEFAULT 3,
                    effective_date DATE NOT NULL,
                    is_active TINYINT NOT NULL DEFAULT 1,
                    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    UNIQUE KEY uk_sector_dragon_config (config_key, effective_date)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
                """
            )
        )
        conn.execute(
            text(
                """
                INSERT IGNORE INTO sector_dragon_config (
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
                FROM sector_dragon_config
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
    """从 ods_dc_member_di 枚举板块（与扩散 DWM 一致），避免仅靠资金流 DWM 漏掉行业板块。"""
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
    board_base AS (
        SELECT
            m.ts_code AS industry_code,
            COALESCE(idx.dc_name, ff.industry_name, m.ts_code) AS industry_name,
            CASE
                WHEN idx.idx_type = '行业板块' THEN '行业'
                WHEN idx.idx_type = '概念板块' THEN '概念'
                WHEN idx.idx_type = '地域板块' THEN '地域'
                WHEN ff.content_type IN ('行业', '概念', '地域') THEN ff.content_type
                ELSE NULL
            END AS content_type,
            COUNT(DISTINCT m.con_code) AS member_cnt
        FROM ods_dc_member_di m
        LEFT JOIN ods_dc_index_di idx
          ON m.trade_date = idx.trade_date AND m.ts_code = idx.ts_code
        LEFT JOIN ff ON m.ts_code = ff.industry_code
        WHERE m.trade_date = :td
        GROUP BY m.ts_code, idx.dc_name, idx.idx_type, ff.industry_name, ff.content_type
    )
    SELECT industry_code, industry_name, content_type
    FROM board_base
    WHERE content_type IN ({placeholders})
      AND member_cnt >= :min_cnt
    ORDER BY content_type, industry_name
    """
    with engine.connect() as conn:
        rows = conn.execute(text(sql_member), params).mappings().all()
    if rows:
        return [dict(r) for r in rows]

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
        return [dict(r) for r in rows]
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
    return [dict(r) for r in rows]


def load_members(
    engine: Engine,
    trade_date: date,
    industry_code: str,
) -> list[dict[str, str]]:
    codes_to_try = [industry_code]
    if industry_code.endswith(".DC"):
        codes_to_try.append(industry_code[:-3])
    else:
        codes_to_try.append(f"{industry_code}.DC")

    for board_code in codes_to_try:
        with engine.connect() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT con_code, name
                    FROM ods_dc_member_di
                    WHERE trade_date = :td AND ts_code = :ic
                    """
                ),
                {"td": trade_date, "ic": board_code},
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
