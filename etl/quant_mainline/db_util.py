"""量化主线：建表、配置与交易日工具。"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine

from mysql_config import get_engine

DEFAULT_SIGNAL_THRESHOLDS: dict[str, Any] = {
    "rs_gt": 1.2,
    "a_up_3d": True,
    "z_gt_market_mult": 1.5,
    "leader_new_high": True,
    "r_le_days": 3,
    "rs_lt": 0.9,
    "a_down_2d": True,
    "leader_ash_pct": -7.0,
    "blast_gt": 0.4,
}


@dataclass
class QuantMainlineConfig:
    config_key: str = "__global__"
    content_types: tuple[str, ...] = ("行业", "概念")
    top_n: int = 10
    w_f: float = 0.2
    w_t: float = 0.2
    w_e: float = 0.2
    w_l: float = 0.2
    w_p: float = 0.2
    f_weights: dict[str, float] = field(
        default_factory=lambda: {"A": 0.4, "V": 0.3, "ETF": 0.2, "H": 0.1}
    )
    t_weights: dict[str, float] = field(
        default_factory=lambda: {"RS": 0.4, "N": 0.3, "R": 0.2, "M": 0.1}
    )
    e_weights: dict[str, float] = field(
        default_factory=lambda: {"Z": 0.35, "J": 0.25, "B": 0.2, "U": 0.2}
    )
    l_weights: dict[str, float] = field(
        default_factory=lambda: {"LR": 0.5, "LC": 0.3, "LP": 0.2}
    )
    p_weights: dict[str, float] = field(
        default_factory=lambda: {"Earnings": 0.5, "Policy": 0.3, "Forecast": 0.2}
    )
    signal_thresholds: dict[str, Any] = field(
        default_factory=lambda: dict(DEFAULT_SIGNAL_THRESHOLDS)
    )
    ma_window_rank: int = 5


def parse_trade_date(s: str) -> date:
    s = s.strip().replace("-", "")
    if len(s) != 8:
        raise ValueError(f"invalid trade_date: {s}")
    return datetime.strptime(s, "%Y%m%d").date()


def get_engine_stock() -> Engine:
    return get_engine()


def _parse_json_weights(raw: Any, default: dict[str, float]) -> dict[str, float]:
    if raw is None:
        return dict(default)
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            return dict(default)
    if not isinstance(raw, dict):
        return dict(default)
    out = dict(default)
    for k, v in raw.items():
        try:
            out[str(k)] = float(v)
        except (TypeError, ValueError):
            continue
    return out


def ensure_schema(engine: Engine) -> None:
    """表结构以 mysql_tables/stock_data.sql 为准；此处仅种子默认配置。"""
    with engine.begin() as conn:
        cnt = conn.execute(
            text("SELECT COUNT(*) FROM dwm_dc_mainline_config WHERE config_key='__global__'")
        ).scalar()
        if not cnt:
            conn.execute(
                text(
                    """
                    INSERT INTO dwm_dc_mainline_config (
                        config_key, content_types, top_n,
                        w_f, w_t, w_e, w_l, w_p,
                        f_weights, t_weights, e_weights, l_weights, p_weights,
                        signal_thresholds, ma_window_rank, effective_date, is_active
                    ) VALUES (
                        '__global__', '行业,概念', 10,
                        0.2, 0.2, 0.2, 0.2, 0.2,
                        :f_w, :t_w, :e_w, :l_w, :p_w,
                        :sig, 5, CURDATE(), 1
                    )
                    """
                ),
                {
                    "f_w": json.dumps({"A": 0.4, "V": 0.3, "ETF": 0.2, "H": 0.1}),
                    "t_w": json.dumps({"RS": 0.4, "N": 0.3, "R": 0.2, "M": 0.1}),
                    "e_w": json.dumps({"Z": 0.35, "J": 0.25, "B": 0.2, "U": 0.2}),
                    "l_w": json.dumps({"LR": 0.5, "LC": 0.3, "LP": 0.2}),
                    "p_w": json.dumps({"Earnings": 0.5, "Policy": 0.3, "Forecast": 0.2}),
                    "sig": json.dumps(DEFAULT_SIGNAL_THRESHOLDS),
                },
            )


def load_config(engine: Engine, trade_date: date) -> QuantMainlineConfig:
    sql = """
    SELECT *
    FROM dwm_dc_mainline_config
    WHERE config_key = '__global__'
      AND is_active = 1
      AND effective_date <= :td
    ORDER BY effective_date DESC
    LIMIT 1
    """
    with engine.connect() as conn:
        row = conn.execute(text(sql), {"td": trade_date}).mappings().first()
    if not row:
        return QuantMainlineConfig()
    ctypes = tuple(x.strip() for x in str(row["content_types"]).split(",") if x.strip())
    sig = row.get("signal_thresholds")
    if isinstance(sig, str):
        try:
            sig = json.loads(sig)
        except json.JSONDecodeError:
            sig = dict(DEFAULT_SIGNAL_THRESHOLDS)
    if not isinstance(sig, dict):
        sig = dict(DEFAULT_SIGNAL_THRESHOLDS)
    return QuantMainlineConfig(
        config_key=str(row["config_key"]),
        content_types=ctypes or ("行业", "概念"),
        top_n=int(row.get("top_n") or 10),
        w_f=float(row.get("w_f") or 0.2),
        w_t=float(row.get("w_t") or 0.2),
        w_e=float(row.get("w_e") or 0.2),
        w_l=float(row.get("w_l") or 0.2),
        w_p=float(row.get("w_p") or 0.2),
        f_weights=_parse_json_weights(row.get("f_weights"), QuantMainlineConfig().f_weights),
        t_weights=_parse_json_weights(row.get("t_weights"), QuantMainlineConfig().t_weights),
        e_weights=_parse_json_weights(row.get("e_weights"), QuantMainlineConfig().e_weights),
        l_weights=_parse_json_weights(row.get("l_weights"), QuantMainlineConfig().l_weights),
        p_weights=_parse_json_weights(row.get("p_weights"), QuantMainlineConfig().p_weights),
        signal_thresholds=sig,
        ma_window_rank=int(row.get("ma_window_rank") or 5),
    )


def list_prev_trade_dates(engine: Engine, trade_date: date, limit: int = 10) -> list[date]:
    sql = """
    SELECT trade_date
    FROM ods_trading_day
    WHERE trade_date < :td
    ORDER BY trade_date DESC
    LIMIT :lim
    """
    with engine.connect() as conn:
        rows = conn.execute(text(sql), {"td": trade_date, "lim": limit}).fetchall()
    if rows:
        return [r[0] for r in rows]
    sql2 = """
    SELECT DISTINCT trade_date
    FROM dwm_dc_industry_fund_flow_di
    WHERE trade_date < :td
    ORDER BY trade_date DESC
    LIMIT :lim
    """
    with engine.connect() as conn:
        rows = conn.execute(text(sql2), {"td": trade_date, "lim": limit}).fetchall()
    return [r[0] for r in rows]
