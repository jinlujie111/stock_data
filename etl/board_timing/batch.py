"""东财板块四因子择时日批入口。"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import text

_ROOT = Path(__file__).resolve().parents[2]
for _p in (_ROOT, _ROOT / "dw-utils"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from etl.board_timing.db_util import (  # noqa: E402
    TimingConfig,
    get_engine_stock,
    parse_trade_date,
)
from etl.board_timing.factors import build_panel_for_range  # noqa: E402
from etl.board_timing.scoring import apply_signals  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

UPSERT_SQL = """
INSERT INTO dwm_board_timing_signal_di (
    trade_date, industry_code, industry_name, content_type,
    close, ma20, ma60, score, score_trend, score_fund, score_vp, score_sentiment,
    signal_type, signal_reason, position_state,
    mom20, flow5, net_inflow_days, amount_ratio20, up_ratio, limit_up_ratio,
    sentiment_overheat, last_buy_close, rank_score
) VALUES (
    :trade_date, :industry_code, :industry_name, :content_type,
    :close, :ma20, :ma60, :score, :score_trend, :score_fund, :score_vp, :score_sentiment,
    :signal_type, :signal_reason, :position_state,
    :mom20, :flow5, :net_inflow_days, :amount_ratio20, :up_ratio, :limit_up_ratio,
    :sentiment_overheat, :last_buy_close, :rank_score
)
ON DUPLICATE KEY UPDATE
    industry_name=VALUES(industry_name),
    content_type=VALUES(content_type),
    close=VALUES(close), ma20=VALUES(ma20), ma60=VALUES(ma60),
    score=VALUES(score), score_trend=VALUES(score_trend),
    score_fund=VALUES(score_fund), score_vp=VALUES(score_vp),
    score_sentiment=VALUES(score_sentiment),
    signal_type=VALUES(signal_type), signal_reason=VALUES(signal_reason),
    position_state=VALUES(position_state),
    mom20=VALUES(mom20), flow5=VALUES(flow5),
    net_inflow_days=VALUES(net_inflow_days),
    amount_ratio20=VALUES(amount_ratio20),
    up_ratio=VALUES(up_ratio), limit_up_ratio=VALUES(limit_up_ratio),
    sentiment_overheat=VALUES(sentiment_overheat),
    last_buy_close=VALUES(last_buy_close),
    rank_score=VALUES(rank_score),
    updated_at=CURRENT_TIMESTAMP
"""


def _parse_content_types(s: str) -> list[str]:
    return [x.strip() for x in (s or "").split(",") if x.strip()]


def _null_num(v: Any) -> Any:
    if v is None:
        return None
    try:
        import math

        if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
            return None
    except Exception:
        pass
    try:
        import pandas as pd

        if pd.isna(v):
            return None
    except Exception:
        pass
    return v


def _row_params(r: dict) -> dict:
    return {
        "trade_date": r["trade_date"],
        "industry_code": r["industry_code"],
        "industry_name": r.get("industry_name"),
        "content_type": r.get("content_type"),
        "close": _null_num(r.get("close")),
        "ma20": _null_num(r.get("ma20")),
        "ma60": _null_num(r.get("ma60")),
        "score": _null_num(r.get("score")),
        "score_trend": _null_num(r.get("score_trend")),
        "score_fund": _null_num(r.get("score_fund")),
        "score_vp": _null_num(r.get("score_vp")),
        "score_sentiment": _null_num(r.get("score_sentiment")),
        "signal_type": r.get("signal_type") or "none",
        "signal_reason": r.get("signal_reason"),
        "position_state": r.get("position_state"),
        "mom20": _null_num(r.get("mom20")),
        "flow5": _null_num(r.get("flow5")),
        "net_inflow_days": int(r["net_inflow_days"])
        if r.get("net_inflow_days") is not None and _null_num(r.get("net_inflow_days")) is not None
        else None,
        "amount_ratio20": _null_num(r.get("amount_ratio20")),
        "up_ratio": _null_num(r.get("up_ratio")),
        "limit_up_ratio": _null_num(r.get("limit_up_ratio")),
        "sentiment_overheat": int(r.get("sentiment_overheat") or 0),
        "last_buy_close": _null_num(r.get("last_buy_close")),
        "rank_score": int(r["rank_score"])
        if r.get("rank_score") is not None and _null_num(r.get("rank_score")) is not None
        else None,
    }


def _chunk_insert(conn, sql: str, rows: list[dict], size: int = 500) -> None:
    for i in range(0, len(rows), size):
        chunk = rows[i : i + size]
        if chunk:
            conn.execute(text(sql), chunk)


def purge_old(engine, keep_days: int) -> int:
    cutoff = date.today() - timedelta(days=keep_days)
    with engine.begin() as conn:
        res = conn.execute(
            text("DELETE FROM dwm_board_timing_signal_di WHERE trade_date < :c"),
            {"c": cutoff},
        )
        return int(res.rowcount or 0)


def run_batch(
    trade_date: date,
    *,
    start_date: date | None = None,
    content_types: list[str] | None = None,
    cfg: TimingConfig | None = None,
) -> dict:
    cfg = cfg or TimingConfig()
    ctypes = content_types or list(cfg.content_types)
    engine = get_engine_stock()
    out_start = start_date or trade_date
    out_end = trade_date

    logger.info(
        "board_timing batch start=%s end=%s types=%s",
        out_start,
        out_end,
        ctypes,
    )
    panel = build_panel_for_range(
        engine,
        out_end,
        start=out_start,
        content_types=ctypes,
        cfg=cfg,
    )
    signaled = apply_signals(panel, out_start=out_start, out_end=out_end, cfg=cfg)
    if signaled.empty:
        raise RuntimeError("择时信号未产出任何记录")

    params = [_row_params(r) for r in signaled.to_dict(orient="records")]
    with engine.begin() as conn:
        _chunk_insert(conn, UPSERT_SQL, params)

    deleted = purge_old(engine, cfg.retention_days)
    n_buy = int((signaled["signal_type"] == "buy").sum())
    n_sell = int((signaled["signal_type"] == "sell").sum())
    summary = {
        "start": str(out_start),
        "end": str(out_end),
        "rows": len(params),
        "buy": n_buy,
        "sell": n_sell,
        "purged": deleted,
        "content_types": ctypes,
    }
    logger.info("board_timing done %s", summary)
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="东财板块四因子择时日批")
    parser.add_argument("trade_date", help="结束日 YYYYMMDD")
    parser.add_argument(
        "start_date",
        nargs="?",
        default=None,
        help="可选开始日 YYYYMMDD；省略则只跑结束日",
    )
    parser.add_argument("--content-types", default="行业,概念")
    args = parser.parse_args(argv)

    end = parse_trade_date(args.trade_date)
    start = parse_trade_date(args.start_date) if args.start_date else None
    if start and start > end:
        raise SystemExit("start_date 不能晚于 trade_date")

    run_batch(
        end,
        start_date=start,
        content_types=_parse_content_types(args.content_types),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
