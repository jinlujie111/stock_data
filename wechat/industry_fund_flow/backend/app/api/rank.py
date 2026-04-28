"""用途：排行榜 — 主力净流入、连续吸筹、出货、潜伏（VIP）。"""
from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.responses import ok
from app.database import get_db
from app.models.orm import User
from app.deps import get_current_user
from app.services import industry_query
from app.services import insight_service

router = APIRouter(prefix="/rank", tags=["rank"])


@router.get("/inflow")
def rank_inflow(
    trade_date: date | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user),
):
    td = trade_date or industry_query.latest_trade_date(db)
    if not td:
        return ok({"items": [], "total": 0})
    rows = industry_query.fund_flow_day(db, td)
    total = len(rows)
    if user is None or not _is_vip(user):
        rows = rows[:3]
        total = min(total, 3)
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
    user: User | None = Depends(get_current_user),
):
    """次日潜伏 TOP5：VIP 看满额；免费仅前 3 条可见详情（客户端再遮罩）。"""
    td = trade_date or industry_query.latest_trade_date(db)
    if not td:
        return ok([])
    rows = industry_query.latent_scores(db, td, limit=10)
    vip = user is not None and _is_vip(user)
    top = rows[:5] if vip else rows[:3]
    return ok(
        {
            "trade_date": str(td),
            "vip": vip,
            "items": top,
            "hint": None if vip else "开通VIP解锁TOP5与完整评分拆解",
        }
    )


def _is_vip(user: User) -> bool:
    from datetime import datetime

    return bool(
        user.is_vip == 1 and user.vip_expire_at and user.vip_expire_at > datetime.utcnow()
    )
