"""AI 核心池：数据库读写与配置。"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine

from mysql_config import get_engine


@dataclass
class AiCoreConfig:
    model_name: str = "gpt-4o-mini"
    llm_provider: str | None = None
    prompt_version: str = "v1"
    temperature: float = 0.2
    max_tokens: int = 1024
    score_threshold: int = 60
    reject_score: int = 20
    mainbz_min_pct: float = 10.0
    batch_size: int = 10
    rate_limit_rpm: int = 60


@dataclass
class TrackRow:
    industry_id: str
    industry_name: str
    as_of_date: date
    content_type: str | None
    dc_board_code: str


@dataclass
class CandidateStock:
    industry_id: str
    industry_name: str
    ts_code: str
    stock_name: str | None


def parse_trade_date(s: str) -> date:
    s = s.strip().replace("-", "")
    if len(s) != 8:
        raise ValueError(f"invalid trade_date: {s}")
    return datetime.strptime(s, "%Y%m%d").date()


def get_engine_stock() -> Engine:
    return get_engine()


def ensure_schema(engine: Engine | None = None) -> None:
    """表结构以 mysql_tables/stock_data.sql 为准；此处仅确保默认配置存在。"""
    eng = engine or get_engine_stock()
    try:
        with eng.begin() as conn:
            cnt = conn.execute(text("SELECT COUNT(*) FROM ai_core_pool_config")).scalar()
            if int(cnt or 0) == 0:
                conn.execute(
                    text(
                        """
                        INSERT INTO ai_core_pool_config (
                            config_key, model_name, prompt_version, temperature, max_tokens,
                            score_threshold, reject_score, mainbz_min_pct, batch_size,
                            rate_limit_rpm, effective_date, is_active
                        ) VALUES (
                            '__global__', 'gpt-4o-mini', 'v1', 0.20, 1024,
                            60, 20, 10.00, 10, 60, CURDATE(), 1
                        )
                        """
                    )
                )
    except Exception as exc:
        raise RuntimeError(
            "ai_core_pool_config 表不存在或不可写，请先在 stock_data 执行 mysql_tables/stock_data.sql 中需求4 DDL"
        ) from exc


def load_config(trade_date: date, engine: Engine | None = None) -> AiCoreConfig:
    eng = engine or get_engine_stock()
    with eng.connect() as conn:
        has_provider = int(
            conn.execute(
                text(
                    """
                    SELECT COUNT(*) FROM information_schema.columns
                    WHERE table_schema = DATABASE()
                      AND table_name = 'ai_core_pool_config'
                      AND column_name = 'llm_provider'
                    """
                )
            ).scalar()
            or 0
        ) >= 1
        if has_provider:
            sql = """
                SELECT model_name, llm_provider, prompt_version, temperature, max_tokens,
                       score_threshold, reject_score, mainbz_min_pct,
                       batch_size, rate_limit_rpm
                FROM ai_core_pool_config
                WHERE config_key = '__global__'
                  AND is_active = 1
                  AND effective_date <= :td
                ORDER BY effective_date DESC
                LIMIT 1
            """
        else:
            sql = """
                SELECT model_name, prompt_version, temperature, max_tokens,
                       score_threshold, reject_score, mainbz_min_pct,
                       batch_size, rate_limit_rpm
                FROM ai_core_pool_config
                WHERE config_key = '__global__'
                  AND is_active = 1
                  AND effective_date <= :td
                ORDER BY effective_date DESC
                LIMIT 1
            """
        row = conn.execute(text(sql), {"td": trade_date}).mappings().first()
    if not row:
        return AiCoreConfig()
    return AiCoreConfig(
        model_name=str(row["model_name"]),
        llm_provider=str(row["llm_provider"]) if row.get("llm_provider") else None,
        prompt_version=str(row["prompt_version"]),
        temperature=float(row["temperature"]),
        max_tokens=int(row["max_tokens"]),
        score_threshold=int(row["score_threshold"]),
        reject_score=int(row["reject_score"]),
        mainbz_min_pct=float(row["mainbz_min_pct"]),
        batch_size=int(row["batch_size"]),
        rate_limit_rpm=int(row["rate_limit_rpm"]),
    )


def list_tracks(
    as_of_date: date,
    *,
    industry_id: str | None = None,
    engine: Engine | None = None,
) -> list[TrackRow]:
    eng = engine or get_engine_stock()
    sql = """
        SELECT industry_id, industry_name, as_of_date, content_type, dc_board_code
        FROM dim_industry_track
        WHERE as_of_date = :d AND status = 1
    """
    params: dict[str, Any] = {"d": as_of_date}
    if industry_id:
        sql += " AND industry_id = :iid"
        params["iid"] = industry_id
    sql += " ORDER BY heat_sort"
    with eng.connect() as conn:
        rows = conn.execute(text(sql), params).mappings().all()
    return [
        TrackRow(
            industry_id=r["industry_id"],
            industry_name=r["industry_name"],
            as_of_date=r["as_of_date"],
            content_type=r.get("content_type"),
            dc_board_code=r["dc_board_code"],
        )
        for r in rows
    ]


def list_candidates(
    as_of_date: date,
    *,
    industry_id: str | None = None,
    ts_codes: list[str] | None = None,
    engine: Engine | None = None,
) -> list[CandidateStock]:
    eng = engine or get_engine_stock()
    sql = """
        SELECT s.industry_id, t.industry_name, s.ts_code, s.stock_name
        FROM dim_industry_track_stock s
        JOIN dim_industry_track t
          ON t.industry_id = s.industry_id AND t.as_of_date = s.as_of_date
        WHERE s.as_of_date = :d AND s.is_active = 1 AND t.status = 1
    """
    params: dict[str, Any] = {"d": as_of_date}
    if industry_id:
        sql += " AND s.industry_id = :iid"
        params["iid"] = industry_id
    if ts_codes:
        placeholders = ", ".join(f":c{i}" for i in range(len(ts_codes)))
        sql += f" AND s.ts_code IN ({placeholders})"
        for i, c in enumerate(ts_codes):
            params[f"c{i}"] = c
    sql += " ORDER BY s.industry_id, s.ts_code"
    with eng.connect() as conn:
        rows = conn.execute(text(sql), params).mappings().all()
    return [
        CandidateStock(
            industry_id=r["industry_id"],
            industry_name=r["industry_name"],
            ts_code=r["ts_code"],
            stock_name=r.get("stock_name"),
        )
        for r in rows
    ]


def existing_score_keys(
    trade_date: date,
    engine: Engine | None = None,
) -> set[tuple[str, str]]:
    eng = engine or get_engine_stock()
    with eng.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT industry_id, ts_code
                FROM dwm_industry_stock_ai_score_di
                WHERE trade_date = :td
                """
            ),
            {"td": trade_date},
        ).fetchall()
    return {(r[0], r[1]) for r in rows}


def stocks_with_recent_updates(
    trade_date: date,
    lookback_days: int = 7,
    engine: Engine | None = None,
) -> set[str]:
    """delta 模式：近 lookback 日有研报/公告相关更新的股票。"""
    eng = engine or get_engine_stock()
    codes: set[str] = set()
    with eng.connect() as conn:
        for sql in (
            """
            SELECT DISTINCT ts_code FROM ods_report_rc_di
            WHERE report_date >= DATE_SUB(:td, INTERVAL :lb DAY)
              AND report_date <= :td
            """,
            """
            SELECT DISTINCT ts_code FROM ods_fina_indicator
            WHERE ann_date >= DATE_SUB(:td, INTERVAL :lb DAY)
              AND ann_date <= :td
            """,
        ):
            rows = conn.execute(
                text(sql), {"td": trade_date, "lb": lookback_days}
            ).fetchall()
            codes.update(r[0] for r in rows if r[0])
    return codes
