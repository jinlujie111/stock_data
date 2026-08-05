"""四因子择时：配置与库工具。

成交约定（冻结）：
  - 信号在交易日收盘后确认（signal_type 写在信号日）
  - 实盘/回测成交：T+1 开盘（exec_model=t1_open）
  - 未平仓头寸在回测窗口末日按收盘盯市
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, fields
from datetime import date, datetime
from typing import Any

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
    # 抗抖动：买入信号日起未满 N 个交易日仅允许止损卖出
    min_hold_days: int = 3
    # Score 上穿买入 / 下穿卖出需连续 N 日满足阈值侧（含当日）
    confirm_days: int = 2
    # 卖出后冷却 N 个交易日禁止新买入
    cooldown_days: int = 2
    overheat_limit_up_ratio: float = 0.12
    lookback_days: int = 90
    content_types: tuple[str, ...] = ("行业", "概念")
    # 热表保留日历天；更早行在 purge 前写入 archive
    retention_days: int = 730
    # 成交模型：t1_open = 信号日确认，下一交易日开盘成交
    exec_model: str = "t1_open"
    # 单边交易成本（基点），买卖各扣一次；默认 3bp 更接近实盘
    cost_bps: float = 3.0
    # 日批默认回测回看交易日数（不足则取全部可得）
    backtest_lookback_days: int = 120

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["content_types"] = list(self.content_types)
        return d

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True)

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> "TimingConfig":
        if not raw:
            return cls()
        allowed = {f.name for f in fields(cls)}
        kwargs: dict[str, Any] = {}
        for k, v in raw.items():
            if k not in allowed:
                continue
            if k == "content_types":
                if isinstance(v, str):
                    kwargs[k] = tuple(x.strip() for x in v.split(",") if x.strip())
                else:
                    kwargs[k] = tuple(v)
            else:
                kwargs[k] = v
        return cls(**kwargs)


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
