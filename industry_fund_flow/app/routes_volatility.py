from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.exc import SQLAlchemyError

from app.deps import require_user
from app.dc_registry import CONTENT_TYPES, NAV_ITEMS
from app import volatility_service as vol_svc

api_router = APIRouter(prefix="/api/v1/volatility", tags=["volatility-api"])
page_router = APIRouter(tags=["volatility-pages"])

_templates: Jinja2Templates | None = None


def init_volatility_routes(templates: Jinja2Templates) -> None:
    global _templates
    _templates = templates


@page_router.get("/dc/volatility", response_class=HTMLResponse)
def volatility_page(request: Request, user: dict = Depends(require_user)):
    return _templates.TemplateResponse(
        request,
        "dc_volatility.html",
        {
            "user": user,
            "nav_items": NAV_ITEMS,
            "active_nav": "volatility",
            "content_types": CONTENT_TYPES,
            "title": "波动率",
        },
    )


@api_router.get("/trade-dates")
def api_trade_dates(
    limit: int = Query(365, ge=1, le=365),
    _user: dict = Depends(require_user),
):
    try:
        dates = vol_svc.list_trade_dates(limit)
        latest = dates[0] if dates else vol_svc.latest_trade_date()
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=f"查询交易日失败: {exc}") from exc
    return {"latest": latest, "dates": dates}


@api_router.get("/market/history")
def api_market_history(
    trade_date: str | None = Query(None),
    window: int = Query(20, ge=20, le=60),
    days: int = Query(365, ge=30, le=365),
    _user: dict = Depends(require_user),
):
    try:
        return vol_svc.get_market_history(trade_date, window=window, days=days)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=f"查询大盘波动率失败: {exc}") from exc


@api_router.get("/boards/search")
def api_board_search(
    trade_date: str | None = Query(None),
    content_types: str = Query("行业,概念"),
    keyword: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    _user: dict = Depends(require_user),
):
    try:
        return vol_svc.search_boards(
            trade_date,
            content_types=content_types,
            keyword=keyword,
            limit=limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=f"查询板块列表失败: {exc}") from exc


@api_router.get("/boards/history")
def api_board_history(
    trade_date: str | None = Query(None),
    window: int = Query(20, ge=20, le=60),
    content_types: str = Query("行业,概念"),
    industry_codes: str | None = Query(None, description="板块代码，逗号分隔"),
    board_keywords: str | None = Query(None, description="板块名称关键词，逗号分隔"),
    days: int = Query(365, ge=30, le=365),
    _user: dict = Depends(require_user),
):
    codes = [x.strip() for x in (industry_codes or "").split(",") if x.strip()] or None
    keywords = [x.strip() for x in (board_keywords or "").split(",") if x.strip()] or None
    try:
        return vol_svc.get_industry_history(
            trade_date,
            window=window,
            content_types=content_types,
            industry_codes=codes,
            board_keywords=keywords,
            days=days,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=f"查询板块波动率失败: {exc}") from exc


@api_router.get("/boards/rank")
def api_board_rank(
    trade_date: str | None = Query(None),
    window: int = Query(20, ge=20, le=60),
    content_types: str = Query("行业,概念"),
    top: int = Query(50, ge=1, le=200),
    _user: dict = Depends(require_user),
):
    try:
        return vol_svc.rank_industries(
            trade_date,
            window=window,
            content_types=content_types,
            top=top,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=f"查询板块波动率排行失败: {exc}") from exc
