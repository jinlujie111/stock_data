from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.exc import SQLAlchemyError

from app.deps import require_user
from app.dc_registry import NAV_ITEMS
from app import limit_up_service as lu_svc

api_router = APIRouter(prefix="/api/v1/limit-up", tags=["limit-up-api"])
page_router = APIRouter(tags=["limit-up-pages"])

_templates: Jinja2Templates | None = None


def init_limit_up_routes(templates: Jinja2Templates) -> None:
    global _templates
    _templates = templates


@page_router.get("/dc/limit-up", response_class=HTMLResponse)
def limit_up_page(request: Request, user: dict = Depends(require_user)):
    return _templates.TemplateResponse(
        request,
        "dc_limit_up.html",
        {
            "user": user,
            "nav_items": NAV_ITEMS,
            "active_nav": "limit-up",
            "title": "涨停分析",
        },
    )


@api_router.get("/trade-dates")
def api_limit_up_trade_dates(
    limit: int = Query(90, ge=1, le=365),
    _user: dict = Depends(require_user),
):
    try:
        dates = lu_svc.list_trade_dates(limit)
        latest = dates[0] if dates else lu_svc.latest_trade_date()
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=f"查询交易日失败: {exc}") from exc
    return {"latest": latest, "dates": dates}


@api_router.get("/ladder")
def api_limit_up_ladder(
    trade_date: str | None = Query(None),
    _user: dict = Depends(require_user),
):
    try:
        return lu_svc.get_limit_up_ladder(trade_date)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=f"查询涨停天梯失败: {exc}") from exc
