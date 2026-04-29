"""用途：排行榜 — 主力净流入、连续吸筹、出货、潜伏。"""
from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.responses import ok
from app.database import get_db
from app.services import industry_query
from app.services import insight_service

router = APIRouter(prefix="/rank", tags=["rank"])


@router.get("/inflow")
def rank_inflow(
    trade_date: date | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    td = trade_date or industry_query.latest_trade_date(db)
    if not td:
        return ok({"items": [], "total": 0})
    rows = industry_query.fund_flow_day(db, td)
    total = len(rows)
    start = (page - 1) * page_size
    slice_rows = rows[start : start + page_size]
    return ok({"trade_date": str(td), "items": slice_rows, "total": total, "page": page})


@router.get("/accumulate")
def rank_accumulate(
    days: int = Query(3, ge=3, le=10),
    trade_date: date | None = Query(None),
    db: Session = Depends(get_db),
):
    td = trade_date or industry_query.latest_trade_date(db)
    if not td:
        return ok([])
    items = insight_service.consecutive_positive_days(db, td, min_days=days)
    return ok({"trade_date": str(td), "min_days": days, "items": items})


@router.get("/exit")
def rank_exit(
    trade_date: date | None = Query(None),
    db: Session = Depends(get_db),
):
    td = trade_date or industry_query.latest_trade_date(db)
    if not td:
        return ok([])
    items = insight_service.exit_warning(db, td)
    return ok({"trade_date": str(td), "items": items})


@router.get("/latent")
def rank_latent(
    trade_date: date | None = Query(None),
    db: Session = Depends(get_db),
):
    """次日潜伏 TOP5（全量）。数据来自 **industry_score_di**，由 **score_engine** 日终任务写入；非 industry_fund_flow_di 直出。"""
    td = trade_date or industry_query.latest_trade_date(db)
    if not td:
        return ok(
            {
                "trade_date": None,
                "items": [],
                "hint": "库内尚无 industry_fund_flow_di 可用交易日，无法生成潜伏榜。",
            }
        )
    rows = industry_query.latent_scores(db, td, limit=10)
    top = rows[:5]
    hint = None
    if not top:
        hint = (
            "当日 industry_score_di 无数据。需先跑评分："
            "日终任务 job_daily_pipeline（默认 15:10）或手动 score_engine.compute_and_persist(当日)。"
            "表未创建时也会为空。"
        )
    return ok({"trade_date": str(td), "items": top, "hint": hint})
