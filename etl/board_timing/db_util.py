"""四因子择时：配置与库工具。"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy.engine import Engine

from mysql_config import get_engine


@dataclass
class TimingConfig:
    weight_trend: float = 0.30
    weight_fund: float = 0.30
    weight_vp: float = 0.25
    weight_sentiment: float = 0.15
    buy_score: float = 70.0
    sell_score: float = 40.0
    gate_trend: float = 60.0
    gate_fund: float = 55.0
    gate_vp: float = 50.0
    sell_trend: float = 45.0
    stop_loss_pct: float = 0.08
    overheat_limit_up_ratio: float = 0.12
    lookback_days: int = 90
    content_types: tuple[str, ...] = ("行业", "概念")
    retention_days: int = 183


def parse_trade_date(s: str) -> date:
    s = s.strip().replace("-", "")
    if len(s) != 8:
        raise ValueError(f"invalid trade_date: {s}")
    return datetime.strptime(s, "%Y%m%d").date()


def get_engine_stock() -> Engine:
    return get_engine()


def code_variants(industry_code: str) -> list[str]:
    code = industry_code.strip()
    if code.endswith(".DC"):
        return [code, code[:-3]]
    return [code, f"{code}.DC"]
