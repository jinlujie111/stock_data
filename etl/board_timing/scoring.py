"""综合分 → BUY/SELL 事件（穿越 + 硬门禁 + 止损）。"""
from __future__ import annotations

import logging
from datetime import date

import pandas as pd

from etl.board_timing.db_util import TimingConfig

logger = logging.getLogger(__name__)


def apply_signals(
    panel: pd.DataFrame,
    *,
    out_start: date,
    out_end: date,
    cfg: TimingConfig | None = None,
) -> pd.DataFrame:
    """
    对每个板块按时间顺序生成 signal_type / reason / position_state。

    买入：硬门禁 + Score 上穿 buy_score
    卖出：任一卖出规则，或 Score 下穿 sell_score，或相对 last_buy 止损

    成交约定：本函数在「信号日收盘」确认事件；实盘/回测成交为 T+1 开盘
    （见 TimingConfig.exec_model=t1_open）。止损比较用信号日收盘 vs last_buy_close。
    """
    cfg = cfg or TimingConfig()
    if panel.empty:
        return panel

    rows: list[dict] = []
    for ic, g in panel.groupby("industry_code", sort=False):
        g = g.sort_values("trade_date").reset_index(drop=True)
        prev_score: float | None = None
        prev_fund: float | None = None
        fund_down_days = 0
        position = "flat"
        last_buy_close: float | None = None

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

            signal = "none"
            reasons: list[str] = []

            if score is not None and prev_score is not None:
                cross_buy = prev_score < cfg.buy_score <= score
                cross_sell = prev_score > cfg.sell_score >= score
            else:
                cross_buy = False
                cross_sell = False

            hard_ok = (
                st >= cfg.gate_trend
                and sf >= cfg.gate_fund
                and sv >= cfg.gate_vp
                and not overheat
                and (flow5 is None or flow5 > 0)
            )

            if cross_buy and hard_ok:
                signal = "buy"
                reasons.append(
                    f"Score上穿{cfg.buy_score:.0f}({prev_score:.1f}→{score:.1f})"
                )
                reasons.append(f"趋势{st:.0f}/资金{sf:.0f}/量价{sv:.0f}")
                if last_buy_close is None or position != "long":
                    last_buy_close = close
                position = "long"
            else:
                sell_hit = False
                if cross_sell:
                    sell_hit = True
                    reasons.append(
                        f"Score下穿{cfg.sell_score:.0f}({prev_score:.1f}→{score:.1f})"
                    )
                if (
                    close is not None
                    and ma20 is not None
                    and close < ma20
                    and st < cfg.sell_trend
                ):
                    sell_hit = True
                    reasons.append(f"跌破MA20且趋势分{st:.0f}<{cfg.sell_trend:.0f}")
                if flow5 is not None and flow5 < 0 and fund_down_days >= 2:
                    sell_hit = True
                    reasons.append("flow5转负且资金分连降2日")
                if vp_dump:
                    sell_hit = True
                    reasons.append("放量长阴/量价砸盘")
                if (
                    position == "long"
                    and last_buy_close
                    and close is not None
                    and last_buy_close > 0
                    and (last_buy_close - close) / last_buy_close >= cfg.stop_loss_pct
                ):
                    sell_hit = True
                    reasons.append(f"相对买入回撤≥{cfg.stop_loss_pct*100:.0f}%")

                if sell_hit and position == "long":
                    signal = "sell"
                    position = "flat"
                    last_buy_close = None
                else:
                    # 空仓时卖出条件只影响状态，不写 reason（避免噪音 + nan）
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

            if score is not None:
                prev_score = score
            prev_fund = sf

    out = pd.DataFrame(rows)
    if not out.empty:
        n_buy = int((out["signal_type"] == "buy").sum())
        n_sell = int((out["signal_type"] == "sell").sum())
        logger.info(
            "signals out=%d buy=%d sell=%d range=%s..%s",
            len(out),
            n_buy,
            n_sell,
            out_start,
            out_end,
        )
    return out
