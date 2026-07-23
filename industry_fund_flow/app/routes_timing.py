"""东财板块四因子择时 Web 路由。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.exc import SQLAlchemyError

from app.deps import require_user
from app.dc_registry import NAV_ITEMS
from app import timing_service as timing_svc

api_router = APIRouter(prefix="/api/v1/timing", tags=["board-timing-api"])
page_router = APIRouter(tags=["board-timing-pages"])

_templates: Jinja2Templates | None = None


def init_timing_routes(templates: Jinja2Templates) -> None:
    global _templates
    _templates = templates


@page_router.get("/dc/board-timing", response_class=HTMLResponse)
def board_timing_page(request: Request, user: dict = Depends(require_user)):
    return _templates.TemplateResponse(
        request,
        "dc_board_timing.html",
        {
            "user": user,
            "nav_items": NAV_ITEMS,
            "active_nav": "board-timing",
            "title": "板块择时",
        },
    )


@api_router.get("/trade-dates")
def api_timing_trade_dates(
    limit: int = Query(120, ge=1, le=183),
    _user: dict = Depends(require_user),
):
    try:
        dates = timing_svc.list_trade_dates(limit)
        latest = dates[0] if dates else timing_svc.latest_trade_date()
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=f"查询交易日失败: {exc}") from exc
    return {"latest": latest, "dates": dates}


@api_router.get("/rank")
def api_timing_rank(
    trade_date: str | None = Query(None),
    content_types: str = Query("行业,概念"),
    signal_type: str | None = Query(None),
    top: int = Query(50, ge=1, le=200),
    sort: str = Query("score"),
    _user: dict = Depends(require_user),
):
    try:
        return timing_svc.rank_boards(
            trade_date,
            content_types=content_types,
            signal_type=signal_type,
            top=top,
            sort=sort,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=f"查询排行失败: {exc}") from exc


@api_router.get("/signals")
def api_timing_signals(
    trade_date: str | None = Query(None),
    signal_type: str | None = Query(None),
    content_types: str = Query("行业,概念"),
    top: int = Query(100, ge=1, le=200),
    _user: dict = Depends(require_user),
):
    try:
        return timing_svc.list_signals(
            trade_date,
            signal_type=signal_type,
            content_types=content_types,
            top=top,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=f"查询信号失败: {exc}") from exc


@api_router.get("/boards/search")
def api_timing_board_search(
    trade_date: str | None = Query(None),
    content_types: str = Query("行业,概念"),
    keyword: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    _user: dict = Depends(require_user),
):
    try:
        return timing_svc.search_boards(
            trade_date,
            content_types=content_types,
            keyword=keyword,
            limit=limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=f"搜索板块失败: {exc}") from exc


@api_router.get("/boards/{industry_code}")
def api_timing_board_detail(
    industry_code: str,
    trade_date: str | None = Query(None),
    _user: dict = Depends(require_user),
):
    try:
        return timing_svc.get_board_detail(industry_code, trade_date)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=f"查询详情失败: {exc}") from exc


@api_router.get("/boards/{industry_code}/kline")
def api_timing_board_kline(
    industry_code: str,
    trade_date: str | None = Query(None),
    start_date: str | None = Query(None),
    days: int = Query(60, ge=5, le=365),
    _user: dict = Depends(require_user),
):
    try:
        return timing_svc.get_board_kline(
            industry_code,
            trade_date,
            start_date=start_date,
            days=days,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=f"查询 K 线失败: {exc}") from exc
