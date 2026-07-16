"""板块截面打分 + 动量/反转状态机。"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Literal

import pandas as pd

from etl.sector_rotation.factors import (
    SectorPanel,
    compute_amt_ratio,
    compute_flow_sum,
    compute_momentum,
    cross_section_rank,
)

RegimeMode = Literal["momentum", "reversal", "auto"]
RegimeState = Literal["momentum", "reversal"]


@dataclass
class FactorSpec:
    name: str  # mom20/mom60/mom120/flow5/flow20/amt_ratio20
    weight: float
    direction: int = 1


@dataclass
class RotationConfig:
    top_n: int = 5
    rebalance: str = "weekly"
    factors: list[FactorSpec] = field(
        default_factory=lambda: [
            FactorSpec("mom20", 0.35, 1),
            FactorSpec("mom60", 0.25, 1),
            FactorSpec("flow5", 0.25, 1),
            FactorSpec("amt_ratio20", 0.15, 1),
        ]
    )
    # fixed_momentum / fixed_reversal / auto（状态机）
    regime: RegimeMode = "auto"
    # 状态机：用过去 lookback 个调仓日的「动量组合 vs 反转组合」前瞻收益择优
    regime_lookback: int = 4
    regime_confirm: int = 2  # 连续 N 次同向才切换，防抖
    buy_cost: float = 0.0003
    sell_cost: float = 0.0003
    init_capital: float = 1_000_000.0

    @staticmethod
    def from_json(cfg: str | dict) -> "RotationConfig":
        data: dict[str, Any] = json.loads(cfg) if isinstance(cfg, str) else dict(cfg)
        sel = data.get("select") or {}
        cost = data.get("cost") or {}
        regime_cfg = data.get("regime") or {}
        factors = [
            FactorSpec(
                name=f["name"],
                weight=float(f.get("weight", 0.0)),
                direction=int(f.get("direction", 1)),
            )
            for f in data.get("factors", [])
            if f.get("name")
        ]
        if not factors:
            factors = RotationConfig().factors
        regime = data.get("style") or regime_cfg.get("mode") or data.get("regime") or "auto"
        if isinstance(regime, dict):
            regime = regime.get("mode", "auto")
        if regime in ("fixed_momentum", "momentum"):
            regime_mode: RegimeMode = "momentum"
        elif regime in ("fixed_reversal", "reversal"):
            regime_mode = "reversal"
        else:
            regime_mode = "auto"
        return RotationConfig(
            top_n=int(sel.get("top_n", 5) or 5),
            rebalance=str(sel.get("rebalance", "weekly") or "weekly"),
            factors=factors,
            regime=regime_mode,
            regime_lookback=int(regime_cfg.get("lookback", 4) or 4),
            regime_confirm=int(regime_cfg.get("confirm", 2) or 2),
            buy_cost=float(cost.get("buy", 0.0003) or 0.0003),
            sell_cost=float(cost.get("sell", 0.0003) or 0.0003),
            init_capital=float(data.get("init_capital", 1_000_000) or 1_000_000),
        )

    def to_json(self) -> str:
        return json.dumps(
            {
                "universe": {"source": "sw2021_l1"},
                "factors": [
                    {"name": f.name, "weight": f.weight, "direction": f.direction}
                    for f in self.factors
                ],
                "select": {"top_n": self.top_n, "rebalance": self.rebalance},
                "regime": {
                    "mode": self.regime,
                    "lookback": self.regime_lookback,
                    "confirm": self.regime_confirm,
                },
                "cost": {"buy": self.buy_cost, "sell": self.sell_cost},
            },
            ensure_ascii=False,
        )

    def mom_windows(self) -> list[int]:
        out: list[int] = []
        for f in self.factors:
            if f.name.startswith("mom"):
                out.append(int(f.name.replace("mom", "")))
        return sorted(set(out))

    def flow_windows(self) -> list[int]:
        out: list[int] = []
        for f in self.factors:
            if f.name.startswith("flow"):
                out.append(int(f.name.replace("flow", "")))
        return sorted(set(out))


def _factor_raw_map(
    as_of: date, panel: SectorPanel, cfg: RotationConfig
) -> dict[str, pd.Series]:
    """ ass_of 日各因子原始值 Series(index=ts_code)。"""
    key = as_of if as_of in panel.close.index else pd.Timestamp(as_of)
    moms = compute_momentum(panel.close, cfg.mom_windows() or [20, 60])
    flows = compute_flow_sum(panel.net_flow, cfg.flow_windows() or [5, 20])
    amt_ratio = compute_amt_ratio(panel.amount, 20)

    out: dict[str, pd.Series] = {}
    for f in cfg.factors:
        if f.name.startswith("mom"):
            w = int(f.name.replace("mom", ""))
            if w in moms and key in moms[w].index:
                out[f.name] = moms[w].loc[key]
        elif f.name.startswith("flow"):
            w = int(f.name.replace("flow", ""))
            if w in flows and key in flows[w].index:
                out[f.name] = flows[w].loc[key]
        elif f.name == "amt_ratio20" and amt_ratio is not None and key in amt_ratio.index:
            out[f.name] = amt_ratio.loc[key]
    return out


def score_date(
    as_of: date,
    panel: SectorPanel,
    cfg: RotationConfig,
    *,
    regime: RegimeState = "momentum",
) -> pd.DataFrame:
    """截面打分。regime=reversal 时对动量类因子方向取反（买弱），资金流仍追流入。"""
    if as_of not in panel.close.index and pd.Timestamp(as_of) not in panel.close.index:
        return pd.DataFrame()
    key = as_of if as_of in panel.close.index else pd.Timestamp(as_of)
    raw_map = _factor_raw_map(as_of, panel, cfg)

    rows = []
    for code in panel.close.columns:
        detail = {
            name: (float(s[code]) if code in s.index and pd.notna(s[code]) else None)
            for name, s in raw_map.items()
        }
        rows.append({"ts_code": code, "name": panel.names.get(code, code), **detail})
    df = pd.DataFrame(rows)
    if df.empty:
        return df

    weighted = pd.Series(0.0, index=df["ts_code"])
    wsum = 0.0
    for f in cfg.factors:
        if f.name not in df.columns:
            continue
        direction = f.direction
        # 反转态：仅翻转 mom* 方向；资金流/活跃度仍偏好流入与放量
        if regime == "reversal" and f.name.startswith("mom"):
            direction = -direction
        ranks = cross_section_rank(
            df.set_index("ts_code")[f.name], ascending=(direction < 0)
        )
        weighted = weighted.add(ranks.fillna(0.5).astype(float) * f.weight, fill_value=0.0)
        wsum += abs(f.weight)
    if wsum > 0:
        weighted = weighted / wsum
    df["score"] = df["ts_code"].map(weighted.to_dict())
    df["close"] = df["ts_code"].map(panel.close.loc[key].to_dict())
    df["regime"] = regime
    # 动量因子齐备才可买；资金流缺失用中性分，不阻断
    mom_need = [f.name for f in cfg.factors if f.name.startswith("mom")]
    if mom_need:
        df["can_buy"] = df[mom_need].notna().all(axis=1)
    else:
        df["can_buy"] = True
    return df.sort_values("score", ascending=False).reset_index(drop=True)


def paper_forward_return(
    panel: SectorPanel,
    cfg: RotationConfig,
    signal_day: date,
    hold_days: list[date],
    regime: RegimeState,
) -> float | None:
    """信号日选 TopN，持有到 hold_days 末（等权）的前瞻收益。"""
    if not hold_days:
        return None
    ranked = score_date(signal_day, panel, cfg, regime=regime)
    if ranked.empty:
        return None
    codes = list(ranked[ranked["can_buy"]].head(cfg.top_n)["ts_code"])
    if not codes:
        return None
    end = hold_days[-1]
    rets = []
    for c in codes:
        try:
            p0 = float(panel.close_on(signal_day)[c])
            p1 = float(panel.close_on(end)[c])
        except Exception:
            continue
        if p0 > 0 and pd.notna(p0) and pd.notna(p1):
            rets.append(p1 / p0 - 1.0)
    if not rets:
        return None
    return float(sum(rets) / len(rets))


class RegimeMachine:
    """动量/反转状态机：比较近 lookback 段纸面组合前瞻收益，带确认防抖。"""

    def __init__(self, cfg: RotationConfig):
        self.cfg = cfg
        self.state: RegimeState = "momentum"
        self._pending: RegimeState | None = None
        self._pending_count = 0
        self.history: list[dict] = []

    def decide(
        self,
        panel: SectorPanel,
        rebal_days: list[date],
        idx: int,
        all_days: list[date],
    ) -> RegimeState:
        if self.cfg.regime == "momentum":
            self.state = "momentum"
            return self.state
        if self.cfg.regime == "reversal":
            self.state = "reversal"
            return self.state

        # auto：用过去 lookback 个调仓区间的已实现纸面收益比较
        lookback = max(1, self.cfg.regime_lookback)
        start_i = max(0, idx - lookback)
        past = rebal_days[start_i:idx]
        if len(past) < 2:
            return self.state

        mom_rets: list[float] = []
        rev_rets: list[float] = []
        day_index = {d: i for i, d in enumerate(all_days)}
        for j, sig in enumerate(past[:-1]):
            nxt = past[j + 1]
            i0 = day_index.get(sig)
            i1 = day_index.get(nxt)
            if i0 is None or i1 is None or i1 <= i0:
                continue
            hold = all_days[i0 : i1 + 1]
            mr = paper_forward_return(panel, self.cfg, sig, hold, "momentum")
            rr = paper_forward_return(panel, self.cfg, sig, hold, "reversal")
            if mr is not None:
                mom_rets.append(mr)
            if rr is not None:
                rev_rets.append(rr)
        if not mom_rets or not rev_rets:
            return self.state

        mom_avg = sum(mom_rets) / len(mom_rets)
        rev_avg = sum(rev_rets) / len(rev_rets)
        suggested: RegimeState = "momentum" if mom_avg >= rev_avg else "reversal"

        if suggested == self.state:
            self._pending = None
            self._pending_count = 0
        else:
            if self._pending == suggested:
                self._pending_count += 1
            else:
                self._pending = suggested
                self._pending_count = 1
            if self._pending_count >= max(1, self.cfg.regime_confirm):
                self.state = suggested
                self._pending = None
                self._pending_count = 0

        self.history.append(
            {
                "trade_date": rebal_days[idx],
                "regime": self.state,
                "suggested": suggested,
                "mom_avg": round(mom_avg, 4),
                "rev_avg": round(rev_avg, 4),
            }
        )
        return self.state
