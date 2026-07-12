"""VPA：数据库工具与配置。"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy import text
from sqlalchemy.engine import Engine

from mysql_config import get_engine


@dataclass
class VpConfig:
    window_default: int = 20
    weight_vol: float = 0.20
    weight_trend: float = 0.20
    weight_continuity: float = 0.25
    weight_breadth: float = 0.15
    weight_breakout: float = 0.15
    weight_leader: float = 0.05
    breakout_vol_mult: float = 1.5
    breakout_lookback: int = 60
    min_member_cnt: int = 5
    score_status_burst: int = 80
    score_status_up: int = 60
    score_status_range: int = 40
    score_status_weak: int = 20
    exclude_st: bool = True
    content_types: tuple[str, ...] = ("行业", "概念")


def parse_trade_date(s: str) -> date:
    s = s.strip().replace("-", "")
    if len(s) != 8:
        raise ValueError(f"invalid trade_date: {s}")
    return datetime.strptime(s, "%Y%m%d").date()


def get_engine_stock() -> Engine:
    return get_engine()


def ensure_schema(engine: Engine | None = None) -> None:
    eng = engine or get_engine_stock()
    with eng.begin() as conn:
        cnt = conn.execute(text("SELECT COUNT(*) FROM dwm_vp_config")).scalar()
        if int(cnt or 0) == 0:
            conn.execute(
                text(
                    """
                    INSERT INTO dwm_vp_config (
                        config_key, window_default, effective_date, is_active
                    ) VALUES ('__global__', 20, CURDATE(), 1)
                    """
                )
            )


def load_config(engine: Engine | None = None) -> VpConfig:
    eng = engine or get_engine_stock()
    cfg = VpConfig()
    with eng.connect() as conn:
        row = conn.execute(
            text(
                """
                SELECT window_default, weight_vol, weight_trend, weight_continuity,
                       weight_breadth, weight_breakout, weight_leader, breakout_vol_mult,
                       breakout_lookback, min_member_cnt, score_status_burst,
                       score_status_up, score_status_range, score_status_weak,
                       exclude_st, content_types
                FROM dwm_vp_config
                WHERE config_key = '__global__' AND is_active = 1
                ORDER BY effective_date DESC
                LIMIT 1
                """
            )
        ).mappings().first()
    if not row:
        return cfg
    cfg.window_default = int(row["window_default"])
    cfg.weight_vol = float(row["weight_vol"])
    cfg.weight_trend = float(row["weight_trend"])
    cfg.weight_continuity = float(row["weight_continuity"])
    cfg.weight_breadth = float(row["weight_breadth"])
    cfg.weight_breakout = float(row["weight_breakout"])
    cfg.weight_leader = float(row.get("weight_leader") or 0.05)
    cfg.breakout_vol_mult = float(row["breakout_vol_mult"])
    cfg.breakout_lookback = int(row["breakout_lookback"])
    cfg.min_member_cnt = int(row["min_member_cnt"])
    cfg.score_status_burst = int(row["score_status_burst"])
    cfg.score_status_up = int(row["score_status_up"])
    cfg.score_status_range = int(row["score_status_range"])
    cfg.score_status_weak = int(row["score_status_weak"])
    cfg.exclude_st = bool(int(row["exclude_st"] or 0))
    ct = str(row.get("content_types") or "行业,概念")
    cfg.content_types = tuple(x.strip() for x in ct.split(",") if x.strip())
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


def load_st_codes(engine: Engine) -> set[str]:
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT ts_code FROM ods_stock_basic_di
                WHERE name LIKE 'ST%%' OR name LIKE '*ST%%' OR name LIKE 'S*ST%%'
                   OR name LIKE '%%退'
                """
            )
        ).fetchall()
    return {r[0] for r in rows if r[0]}
