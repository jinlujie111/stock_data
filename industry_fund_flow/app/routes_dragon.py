from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.exc import SQLAlchemyError

from app.deps import require_user
from app.dc_registry import CONTENT_TYPES, NAV_ITEMS
from app import dragon_service as dragon_svc

api_router = APIRouter(prefix="/api/v1/dragon", tags=["dragon-api"])
page_router = APIRouter(tags=["dragon-pages"])

_templates: Jinja2Templates | None = None


def init_dragon_routes(templates: Jinja2Templates) -> None:
    global _templates
    _templates = templates


@page_router.get("/dc/dragon", response_class=HTMLResponse)
def dragon_page(request: Request, user: dict = Depends(require_user)):
    return _templates.TemplateResponse(
        request,
        "dc_dragon.html",
        {
            "user": user,
            "nav_items": NAV_ITEMS,
            "active_nav": "dragon",
            "content_types": CONTENT_TYPES,
            "title": "板块龙头",
        },
    )


@api_router.get("/trade-dates")
def api_dragon_trade_dates(
    limit: int = Query(60, ge=1, le=365),
    _user: dict = Depends(require_user),
):
    try:
        dates = dragon_svc.list_trade_dates(limit)
        latest = dates[0] if dates else dragon_svc.latest_trade_date()
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=f"查询交易日失败: {exc}") from exc
    return {"latest": latest, "dates": dates}


@api_router.get("/boards")
def api_dragon_boards(
    trade_date: str | None = Query(None),
    content_types: str | None = Query(None),
    keyword: str | None = Query(None),
    _user: dict = Depends(require_user),
):
    try:
        items = dragon_svc.list_boards(
            trade_date,
            dragon_svc.parse_content_types_param(content_types),
            keyword,
        )
        td = items[0]["trade_date"] if items else dragon_svc.latest_trade_date()
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=f"查询板块列表失败: {exc}") from exc
    return {"trade_date": td, "items": items}


@api_router.get("/boards/{industry_code}/scores")
def api_dragon_scores(
    industry_code: str,
    trade_date: str | None = Query(None),
    mode: str = Query("mvp"),
    top: int = Query(10, ge=1, le=200),
    sort: str = Query("composite", pattern="^(composite|fund|trend|inst)$"),
    order: str = Query("desc", pattern="^(asc|desc)$"),
    _user: dict = Depends(require_user),
):
    try:
        return dragon_svc.get_board_scores(industry_code, trade_date, mode, top, sort, order)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=f"查询评分失败: {exc}") from exc


@api_router.get("/boards/{industry_code}/summary")
def api_dragon_summary(
    industry_code: str,
    trade_date: str | None = Query(None),
    _user: dict = Depends(require_user),
):
    try:
        return dragon_svc.get_board_summary(industry_code, trade_date)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=f"查询摘要失败: {exc}") from exc


@api_router.get("/leaders")
def api_dragon_leaders(
    trade_date: str | None = Query(None),
    content_types: str | None = Query(None),
    industry_codes: str | None = Query(None),
    top: int = Query(10, ge=1, le=200),
    sort: str = Query("composite"),
    keyword: str | None = Query(None),
    _user: dict = Depends(require_user),
):
    try:
        items = dragon_svc.get_leaders(
            trade_date,
            dragon_svc.parse_content_types_param(content_types),
            dragon_svc.parse_content_types_param(industry_codes),
            top,
            sort,
            keyword,
        )
        td = items[0]["trade_date"] if items else dragon_svc.latest_trade_date()
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=f"查询龙头榜失败: {exc}") from exc
    return {"trade_date": td, "items": items}
