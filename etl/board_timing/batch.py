"""东财板块四因子择时日批入口。"""
from __future__ import annotations

import argparse
import gc
import logging
import sys
from calendar import monthrange
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
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

# 超过该日历跨度则按月分块，避免一次打满内存/数据库
CHUNK_SPAN_DAYS = 40


def _parse_content_types(s: str) -> list[str]:
    return [x.strip() for x in (s or "").split(",") if x.strip()]


def _is_na(v: Any) -> bool:
    if v is None:
        return True
    try:
        import math

        if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
            return True
    except Exception:
        pass
    try:
        if not isinstance(v, (list, dict, tuple)) and pd.isna(v):
            return True
    except Exception:
        pass
    return False


def _null_num(v: Any) -> Any:
    if _is_na(v):
        return None
    return v


def _null_str(v: Any) -> str | None:
    if _is_na(v):
        return None
    s = str(v).strip()
    if not s or s.lower() == "nan":
        return None
    return s


def _null_int(v: Any) -> int | None:
    if _is_na(v):
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _row_params(r: dict) -> dict:
    return {
        "trade_date": r["trade_date"],
        "industry_code": str(r["industry_code"]),
        "industry_name": _null_str(r.get("industry_name")),
        "content_type": _null_str(r.get("content_type")),
        "close": _null_num(r.get("close")),
        "ma20": _null_num(r.get("ma20")),
        "ma60": _null_num(r.get("ma60")),
        "score": _null_num(r.get("score")),
        "score_trend": _null_num(r.get("score_trend")),
        "score_fund": _null_num(r.get("score_fund")),
        "score_vp": _null_num(r.get("score_vp")),
        "score_sentiment": _null_num(r.get("score_sentiment")),
        "signal_type": _null_str(r.get("signal_type")) or "none",
        "signal_reason": _null_str(r.get("signal_reason")),
        "position_state": _null_str(r.get("position_state")),
        "mom20": _null_num(r.get("mom20")),
        "flow5": _null_num(r.get("flow5")),
        "net_inflow_days": _null_int(r.get("net_inflow_days")),
        "amount_ratio20": _null_num(r.get("amount_ratio20")),
        "up_ratio": _null_num(r.get("up_ratio")),
        "limit_up_ratio": _null_num(r.get("limit_up_ratio")),
        "sentiment_overheat": int(_null_num(r.get("sentiment_overheat")) or 0),
        "last_buy_close": _null_num(r.get("last_buy_close")),
        "rank_score": _null_int(r.get("rank_score")),
    }


def _chunk_insert(conn, sql: str, rows: list[dict], size: int = 300) -> None:
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


def _month_chunks(start: date, end: date) -> list[tuple[date, date]]:
    """按自然月切分 [start, end]。"""
    chunks: list[tuple[date, date]] = []
    cur = date(start.year, start.month, 1)
    while cur <= end:
        last_day = monthrange(cur.year, cur.month)[1]
        m_end = date(cur.year, cur.month, last_day)
        c_start = max(start, cur)
        c_end = min(end, m_end)
        if c_start <= c_end:
            chunks.append((c_start, c_end))
        if cur.month == 12:
            cur = date(cur.year + 1, 1, 1)
        else:
            cur = date(cur.year, cur.month + 1, 1)
    return chunks


def _run_one_span(
    engine,
    out_start: date,
    out_end: date,
    *,
    content_types: list[str],
    cfg: TimingConfig,
    use_member_join: bool,
) -> dict:
    logger.info("---- chunk %s .. %s ----", out_start, out_end)
    panel = build_panel_for_range(
        engine,
        out_end,
        start=out_start,
        content_types=content_types,
        cfg=cfg,
        use_member_join=use_member_join,
    )
    signaled = apply_signals(panel, out_start=out_start, out_end=out_end, cfg=cfg)
    del panel
    gc.collect()

    if signaled.empty:
        logger.warning("chunk %s..%s 无输出行，跳过写入", out_start, out_end)
        return {"rows": 0, "buy": 0, "sell": 0}

    clean = signaled.astype(object).where(pd.notnull(signaled), None)
    params = [_row_params(r) for r in clean.to_dict(orient="records")]
    n_buy = int((signaled["signal_type"] == "buy").sum())
    n_sell = int((signaled["signal_type"] == "sell").sum())
    del signaled, clean
    gc.collect()

    with engine.begin() as conn:
        _chunk_insert(conn, UPSERT_SQL, params)

    summary = {
        "start": str(out_start),
        "end": str(out_end),
        "rows": len(params),
        "buy": n_buy,
        "sell": n_sell,
    }
    logger.info("chunk done %s", summary)
    return summary


def run_batch(
    trade_date: date,
    *,
    start_date: date | None = None,
    content_types: list[str] | None = None,
    cfg: TimingConfig | None = None,
    use_member_join: bool = False,
    chunk_days: int = CHUNK_SPAN_DAYS,
) -> dict:
    cfg = cfg or TimingConfig()
    ctypes = content_types or list(cfg.content_types)
    engine = get_engine_stock()
    out_start = start_date or trade_date
    out_end = trade_date

    logger.info(
        "board_timing batch start=%s end=%s types=%s member_join=%s",
        out_start,
        out_end,
        ctypes,
        use_member_join,
    )

    span = (out_end - out_start).days
    if span > chunk_days:
        chunks = _month_chunks(out_start, out_end)
        logger.info("长区间按月分块: %d 段", len(chunks))
    else:
        chunks = [(out_start, out_end)]

    total_rows = total_buy = total_sell = 0
    for i, (cs, ce) in enumerate(chunks, 1):
        logger.info("[%d/%d] processing %s .. %s", i, len(chunks), cs, ce)
        part = _run_one_span(
            engine,
            cs,
            ce,
            content_types=ctypes,
            cfg=cfg,
            use_member_join=use_member_join and span <= 7,
        )
        total_rows += int(part.get("rows") or 0)
        total_buy += int(part.get("buy") or 0)
        total_sell += int(part.get("sell") or 0)

    # 仅日批做保留期清理；长回填不在中途把刚写入的历史删掉
    deleted = 0
    if start_date is None or span <= 3:
        deleted = purge_old(engine, cfg.retention_days)
    else:
        logger.info(
            "跳过 purge（区间回填）；表默认保留约 %d 天，过旧数据请另跑日批清理",
            cfg.retention_days,
        )

    summary = {
        "start": str(out_start),
        "end": str(out_end),
        "chunks": len(chunks),
        "rows": total_rows,
        "buy": total_buy,
        "sell": total_sell,
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
    parser.add_argument(
        "--member-join",
        action="store_true",
        help="强制用成分×涨停 JOIN（仅建议单日；长区间会卡库）",
    )
    parser.add_argument(
        "--chunk-days",
        type=int,
        default=CHUNK_SPAN_DAYS,
        help="超过该日历跨度则按月分块（默认 40）",
    )
    args = parser.parse_args(argv)

    end = parse_trade_date(args.trade_date)
    start = parse_trade_date(args.start_date) if args.start_date else None
    if start and start > end:
        raise SystemExit("start_date 不能晚于 trade_date")

    # 长回填默认只保留近半年写入窗口提示（表仍会写全区间；purge 在结束后按 retention）
    if start and (end - start).days > 200:
        logger.warning(
            "长区间回填 %s..%s：已按月分块 + 禁用成分涨停重 JOIN；"
            "请确认已先杀掉旧进程，避免双开打满机器",
            start,
            end,
        )

    run_batch(
        end,
        start_date=start,
        content_types=_parse_content_types(args.content_types),
        use_member_join=bool(args.member_join),
        chunk_days=max(7, int(args.chunk_days)),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
