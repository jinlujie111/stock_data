"""AI 核心池批处理入口。"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import date
from pathlib import Path

from sqlalchemy import text

_ROOT = Path(__file__).resolve().parents[2]
for _p in (_ROOT, _ROOT / "dw-utils"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from etl.ai_core_pool.context import collect_context  # noqa: E402
from etl.ai_core_pool.db_util import (  # noqa: E402
    CandidateStock,
    ensure_schema,
    existing_score_keys,
    get_engine_stock,
    list_candidates,
    list_tracks,
    load_config,
    parse_trade_date,
    stocks_with_recent_updates,
)
from etl.ai_core_pool.llm_client import analyze_one, resolve_llm_credentials  # noqa: E402
from etl.ai_core_pool.rules import AiScoreRow, apply_rules, build_core_pool  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

SCORE_UPSERT = """
INSERT INTO dwm_industry_stock_ai_score_di (
    trade_date, industry_id, industry_name, ts_code, stock_name,
    industry_match, segment, core_degree, score, level, reason,
    model_name, prompt_version, raw_json
) VALUES (
    :trade_date, :industry_id, :industry_name, :ts_code, :stock_name,
    :industry_match, :segment, :core_degree, :score, :level, :reason,
    :model_name, :prompt_version, CAST(:raw_json AS JSON)
)
ON DUPLICATE KEY UPDATE
    industry_name=VALUES(industry_name), stock_name=VALUES(stock_name),
    industry_match=VALUES(industry_match), segment=VALUES(segment),
    core_degree=VALUES(core_degree), score=VALUES(score), level=VALUES(level),
    reason=VALUES(reason), model_name=VALUES(model_name),
    prompt_version=VALUES(prompt_version), raw_json=VALUES(raw_json),
    updated_at=CURRENT_TIMESTAMP
"""

CORE_UPSERT = """
INSERT INTO dwm_industry_stock_core_di (
    trade_date, industry_id, industry_name, ts_code, stock_name,
    score, level, weight, segment, reason
) VALUES (
    :trade_date, :industry_id, :industry_name, :ts_code, :stock_name,
    :score, :level, :weight, :segment, :reason
)
ON DUPLICATE KEY UPDATE
    industry_name=VALUES(industry_name), stock_name=VALUES(stock_name),
    score=VALUES(score), level=VALUES(level), weight=VALUES(weight),
    segment=VALUES(segment), reason=VALUES(reason),
    updated_at=CURRENT_TIMESTAMP
"""


def _score_params(trade_date: date, row: AiScoreRow) -> dict:
    return {
        "trade_date": trade_date,
        "industry_id": row.industry_id,
        "industry_name": row.industry_name,
        "ts_code": row.ts_code,
        "stock_name": row.stock_name,
        "industry_match": 1 if row.industry_match else 0,
        "segment": row.segment,
        "core_degree": row.core_degree,
        "score": row.score,
        "level": row.level,
        "reason": row.reason,
        "model_name": row.model_name,
        "prompt_version": row.prompt_version,
        "raw_json": json.dumps(row.raw_json, ensure_ascii=False) if row.raw_json else None,
    }


def filter_candidates(
    candidates: list[CandidateStock],
    trade_date: date,
    *,
    mode: str,
    force: bool,
    max_stocks: int | None,
    engine,
) -> list[CandidateStock]:
    if max_stocks is not None and max_stocks > 0:
        candidates = candidates[:max_stocks]

    if force or mode == "full":
        return candidates

    existing = existing_score_keys(trade_date, engine)
    updated = stocks_with_recent_updates(trade_date, engine=engine)
    out: list[CandidateStock] = []
    for c in candidates:
        key = (c.industry_id, c.ts_code)
        if key in existing and c.ts_code not in updated:
            continue
        out.append(c)
    return out


def run_batch(
    trade_date: date,
    *,
    mode: str = "delta",
    industry_id: str | None = None,
    dry_run: bool = False,
    force: bool = False,
    max_stocks: int | None = None,
    use_rules: bool = False,
) -> dict:
    engine = get_engine_stock()
    ensure_schema(engine)
    cfg = load_config(trade_date, engine)
    llm_cred = resolve_llm_credentials(cfg)

    as_of = trade_date
    tracks = list_tracks(as_of, industry_id=industry_id, engine=engine)
    if not tracks:
        logger.warning("dim_industry_track 无数据 as_of=%s，请先 run_dim_industry_track", as_of)
        return {"ok": False, "message": "no tracks", "scores": 0, "core": 0}

    candidates = list_candidates(as_of, industry_id=industry_id, engine=engine)
    raw_candidate_cnt = len(candidates)
    candidates = filter_candidates(
        candidates, trade_date, mode=mode, force=force, max_stocks=max_stocks, engine=engine
    )
    if not candidates:
        if raw_candidate_cnt == 0:
            msg = (
                f"无候选股：dim_industry_track_stock(as_of={as_of}) 为空。"
                "请检查 ods_dc_member_di 是否有当日数据，并重跑 run_dim_industry_track"
            )
        else:
            msg = (
                f"delta 模式过滤后 0 只待处理（原始 {raw_candidate_cnt} 只）。"
                "首跑请用 --mode full --force"
            )
        logger.error(msg)
        return {"ok": False, "message": msg, "scores": 0, "core": 0}

    logger.info(
        "ai_core_pool trade_date=%s mode=%s tracks=%s candidates=%s llm=%s provider=%s rules=%s",
        trade_date,
        mode,
        len(tracks),
        len(candidates),
        llm_cred is not None and not use_rules,
        llm_cred.provider if llm_cred else None,
        use_rules or llm_cred is None,
    )

    scored: list[AiScoreRow] = []
    min_interval = 60.0 / max(cfg.rate_limit_rpm, 1)
    last_call = 0.0

    for i, cand in enumerate(candidates, start=1):
        ctx = collect_context(
            cand.ts_code, cand.stock_name, cand.industry_name, trade_date, engine
        )
        if use_rules or llm_cred is None:
            row = analyze_one(
                cand.industry_id, cand.industry_name, ctx, cfg, force_rules=True
            )
        else:
            elapsed = time.monotonic() - last_call
            if elapsed < min_interval:
                time.sleep(min_interval - elapsed)
            row = analyze_one(cand.industry_id, cand.industry_name, ctx, cfg, creds=llm_cred)
            last_call = time.monotonic()

        row = apply_rules(row, ctx, cfg)
        scored.append(row)

        if i % cfg.batch_size == 0 or i == len(candidates):
            logger.info("进度 %s/%s 最近=%s score=%s level=%s", i, len(candidates), cand.ts_code, row.score, row.level)

    core_rows = build_core_pool(scored, cfg)

    if dry_run:
        logger.info("dry-run: scores=%s core=%s", len(scored), len(core_rows))
        return {"ok": True, "dry_run": True, "scores": len(scored), "core": len(core_rows)}

    with engine.begin() as conn:
        if force or mode == "full":
            conn.execute(
                text("DELETE FROM dwm_industry_stock_core_di WHERE trade_date = :td"),
                {"td": trade_date},
            )
        for row in scored:
            conn.execute(text(SCORE_UPSERT), _score_params(trade_date, row))
        for cr in core_rows:
            conn.execute(
                text(CORE_UPSERT),
                {
                    "trade_date": trade_date,
                    "industry_id": cr.industry_id,
                    "industry_name": cr.industry_name,
                    "ts_code": cr.ts_code,
                    "stock_name": cr.stock_name,
                    "score": cr.score,
                    "level": cr.level,
                    "weight": cr.weight,
                    "segment": cr.segment,
                    "reason": cr.reason,
                },
            )

    logger.info(
        "完成 ai_core_pool scores=%s core=%s tracks=%s",
        len(scored),
        len(core_rows),
        len(tracks),
    )
    return {"ok": True, "scores": len(scored), "core": len(core_rows), "tracks": len(tracks)}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="需求4 AI 核心池批处理")
    p.add_argument("trade_date", nargs="?", help="YYYYMMDD")
    p.add_argument("--mode", choices=("delta", "full"), default="delta")
    p.add_argument("--industry-id", default=None, help="单赛道 industry_id")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--force", action="store_true", help="忽略已有评分，重建核心池")
    p.add_argument("--max-stocks", type=int, default=None, help="限制候选股数量(调试)")
    p.add_argument("--use-rules", action="store_true", help="强制规则引擎，不调用 LLM")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.trade_date:
        td = parse_trade_date(args.trade_date)
    else:
        td = date.today()
    result = run_batch(
        td,
        mode=args.mode,
        industry_id=args.industry_id,
        dry_run=args.dry_run,
        force=args.force,
        max_stocks=args.max_stocks,
        use_rules=args.use_rules,
    )
    if not result.get("ok"):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
