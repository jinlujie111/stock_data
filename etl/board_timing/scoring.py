"""综合分 → BUY/SELL 事件（穿越 + 硬门禁 + 止损 + 抗抖动）。"""
from __future__ import annotations

import logging
from collections import deque
from datetime import date

import pandas as pd

from etl.board_timing.db_util import TimingConfig

logger = logging.getLogger(__name__)


def _confirmed_cross(hist: deque[bool], confirm_n: int) -> bool:
    """
    连续 confirm_n 日为 True，且此前一日为 False（真正进入区间）。
    需要至少 confirm_n+1 个样本；confirm_n=1 即经典单日穿越。
    """
    n = max(1, int(confirm_n))
    if len(hist) < n + 1:
        return False
    window = list(hist)
    streak = window[-(n):]
    before = window[-(n + 1)]
    return (not before) and all(streak)


def apply_signals(
    panel: pd.DataFrame,
    *,
    out_start: date,
    out_end: date,
    cfg: TimingConfig | None = None,
) -> pd.DataFrame:
    """
    对每个板块按时间顺序生成 signal_type / reason / position_state。

    买入：硬门禁 + Score 进入 buy_score 区间并确认 confirm_days 日 + 冷却期外
    卖出：
      - 硬止损：相对 last_buy 回撤 ≥ stop_loss_pct（立即生效，不受最短持仓限制）
      - 软卖出：Score 下穿确认 / 破 MA20 / 资金连降 / 砸盘
        （持仓交易日数 < min_hold_days 时屏蔽）

    成交约定：本函数在「信号日收盘」确认事件；实盘/回测成交为 T+1 开盘
    （见 TimingConfig.exec_model=t1_open）。止损比较用信号日收盘 vs last_buy_close。
    """
    cfg = cfg or TimingConfig()
    if panel.empty:
        return panel

    min_hold = max(1, int(cfg.min_hold_days or 1))
    confirm_n = max(1, int(cfg.confirm_days or 1))
    cooldown_n = max(0, int(cfg.cooldown_days or 0))
    hist_len = confirm_n + 1

    rows: list[dict] = []
    for _ic, g in panel.groupby("industry_code", sort=False):
        g = g.sort_values("trade_date").reset_index(drop=True)
        prev_fund: float | None = None
        fund_down_days = 0
        position = "flat"
        last_buy_close: float | None = None
        hold_days = 0
        cooldown_left = 0
        above_buy_hist: deque[bool] = deque(maxlen=hist_len)
        below_sell_hist: deque[bool] = deque(maxlen=hist_len)

        for _, r in g.iterrows():
            td = r["trade_date"]
            score = float(r["score"]) if pd.notna(r["score"]) else None
            st = float(r["score_trend"]) if pd.notna(r["score_trend"]) else 0.0
            sf = float(r["score_fund"]) if pd.notna(r["score_fund"]) else 0.0
            sv = float(r["score_vp"]) if pd.notna(r["score_vp"]) else 0.0
            close = float(r["close"]) if pd.notna(r["close"]) else None
            ma20 = float(r["ma20"]) if pd.notna(r["ma20"]) else None
            flow5 = float(r["flow5"]) if pd.notna(r["flow5"]) else None
            overheat = int(r.get("sentiment_overheat") or 0)
            vp_dump = float(r.get("vp_dump") or 0) > 0

            if prev_fund is not None and sf < prev_fund:
                fund_down_days += 1
            else:
                fund_down_days = 0

            if position == "long":
                hold_days += 1
            elif cooldown_left > 0:
                cooldown_left -= 1

            signal = "none"
            reasons: list[str] = []

            if score is not None:
                above_buy_hist.append(score >= cfg.buy_score)
                below_sell_hist.append(score <= cfg.sell_score)

            cross_buy = _confirmed_cross(above_buy_hist, confirm_n)
            cross_sell = _confirmed_cross(below_sell_hist, confirm_n)

            hard_ok = (
                st >= cfg.gate_trend
                and sf >= cfg.gate_fund
                and sv >= cfg.gate_vp
                and not overheat
                and (flow5 is None or flow5 > 0)
            )

            hard_stop = (
                position == "long"
                and last_buy_close is not None
                and close is not None
                and last_buy_close > 0
                and (last_buy_close - close) / last_buy_close >= cfg.stop_loss_pct
            )

            soft_reasons: list[str] = []
            if cross_sell:
                if confirm_n > 1:
                    soft_reasons.append(
                        f"Score≤{cfg.sell_score:.0f}确认{confirm_n}日"
                        + (f"({score:.1f})" if score is not None else "")
                    )
                else:
                    soft_reasons.append(
                        f"Score下穿{cfg.sell_score:.0f}"
                        + (f"({score:.1f})" if score is not None else "")
                    )
            if (
                close is not None
                and ma20 is not None
                and close < ma20
                and st < cfg.sell_trend
            ):
                soft_reasons.append(f"跌破MA20且趋势分{st:.0f}<{cfg.sell_trend:.0f}")
            if flow5 is not None and flow5 < 0 and fund_down_days >= 2:
                soft_reasons.append("flow5转负且资金分连降2日")
            if vp_dump:
                soft_reasons.append("放量长阴/量价砸盘")

            allow_soft_sell = hold_days >= min_hold
            soft_sell = bool(soft_reasons) and allow_soft_sell

            can_buy = position != "long" and cross_buy and hard_ok and cooldown_left <= 0

            if can_buy:
                signal = "buy"
                if confirm_n > 1:
                    reasons.append(
                        f"Score≥{cfg.buy_score:.0f}确认{confirm_n}日"
                        + (f"({score:.1f})" if score is not None else "")
                    )
                else:
                    reasons.append(
                        f"Score上穿{cfg.buy_score:.0f}"
                        + (f"({score:.1f})" if score is not None else "")
                    )
                reasons.append(f"趋势{st:.0f}/资金{sf:.0f}/量价{sv:.0f}")
                last_buy_close = close
                position = "long"
                hold_days = 1
                cooldown_left = 0
            elif position == "long" and hard_stop:
                signal = "sell"
                reasons.append(f"相对买入回撤≥{cfg.stop_loss_pct*100:.0f}%")
                position = "flat"
                last_buy_close = None
                hold_days = 0
                cooldown_left = cooldown_n
            elif position == "long" and soft_sell:
                signal = "sell"
                reasons.extend(soft_reasons)
                position = "flat"
                last_buy_close = None
                hold_days = 0
                cooldown_left = cooldown_n
            else:
                reasons = []

            if position == "long":
                state = "long"
            elif score is not None and cfg.sell_score < score < cfg.buy_score:
                state = "watch"
            else:
                state = "flat"

            if out_start <= td <= out_end:
                row = {
                    k: (None if (isinstance(v, float) and pd.isna(v)) else v)
                    for k, v in r.items()
                }
                row["signal_type"] = signal
                row["signal_reason"] = (
                    "；".join(reasons) if signal in ("buy", "sell") and reasons else None
                )
                row["position_state"] = state
                row["last_buy_close"] = last_buy_close
                rows.append(row)

            prev_fund = sf

    out = pd.DataFrame(rows)
    if not out.empty:
        n_buy = int((out["signal_type"] == "buy").sum())
        n_sell = int((out["signal_type"] == "sell").sum())
        logger.info(
            "signals out=%d buy=%d sell=%d range=%s..%s min_hold=%d confirm=%d cooldown=%d",
            len(out),
            n_buy,
            n_sell,
            out_start,
            out_end,
            min_hold,
            confirm_n,
            cooldown_n,
        )
    return out
