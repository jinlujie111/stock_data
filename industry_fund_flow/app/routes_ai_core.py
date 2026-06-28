from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.exc import SQLAlchemyError

from app.deps import require_user
from app.dc_registry import NAV_ITEMS
from app import ai_core_service as ai_core_svc

api_router = APIRouter(prefix="/api/v1/ai-core", tags=["ai-core-api"])
page_router = APIRouter(tags=["ai-core-pages"])

_templates: Jinja2Templates | None = None


def init_ai_core_routes(templates: Jinja2Templates) -> None:
    global _templates
    _templates = templates


@page_router.get("/dc/ai-core", response_class=HTMLResponse)
def ai_core_page(request: Request, user: dict = Depends(require_user)):
    return _templates.TemplateResponse(
        request,
        "dc_ai_core.html",
        {
            "user": user,
            "nav_items": NAV_ITEMS,
            "active_nav": "ai-core",
            "title": "AI 核心池",
        },
    )


@api_router.get("/trade-dates")
def api_ai_core_trade_dates(
    limit: int = Query(60, ge=1, le=365),
    _user: dict = Depends(require_user),
):
    try:
        dates = ai_core_svc.list_trade_dates(limit)
        latest = dates[0] if dates else ai_core_svc.latest_trade_date()
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=f"查询交易日失败: {exc}") from exc
    return {"latest": latest, "dates": dates}


@api_router.get("/tracks")
def api_ai_core_tracks(
    trade_date: str | None = Query(None),
    keyword: str | None = Query(None),
    _user: dict = Depends(require_user),
):
    try:
        items = ai_core_svc.list_tracks(trade_date, keyword)
        td = items[0]["trade_date"] if items else ai_core_svc.latest_trade_date()
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=f"查询赛道失败: {exc}") from exc
    return {"trade_date": td, "items": items}


@api_router.get("/pool")
def api_ai_core_pool(
    industry_id: str = Query(...),
    trade_date: str | None = Query(None),
    level: str | None = Query(None),
    _user: dict = Depends(require_user),
):
    try:
        return ai_core_svc.get_core_pool(industry_id, trade_date, level)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=f"查询核心池失败: {exc}") from exc


@api_router.get("/scores")
def api_ai_core_scores(
    industry_id: str = Query(...),
    trade_date: str | None = Query(None),
    include_rejected: bool = Query(False),
    _user: dict = Depends(require_user),
):
    try:
        return ai_core_svc.get_scores(industry_id, trade_date, include_rejected)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=f"查询评分失败: {exc}") from exc
