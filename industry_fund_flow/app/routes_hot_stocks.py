from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.exc import SQLAlchemyError

from app.deps import require_user
from app.dc_registry import NAV_ITEMS
from app import hot_stock_service as hot_svc

api_router = APIRouter(prefix="/api/v1/hot-stocks", tags=["hot-stocks-api"])
page_router = APIRouter(tags=["hot-stocks-pages"])

_templates: Jinja2Templates | None = None


def init_hot_stocks_routes(templates: Jinja2Templates) -> None:
    global _templates
    _templates = templates


@page_router.get("/dc/hot-stocks", response_class=HTMLResponse)
def hot_stocks_page(request: Request, user: dict = Depends(require_user)):
    return _templates.TemplateResponse(
        request,
        "dc_hot_stocks.html",
        {
            "user": user,
            "nav_items": NAV_ITEMS,
            "active_nav": "hot-stocks",
            "hot_types": hot_svc.HOT_TYPES,
            "markets": hot_svc.MARKETS,
            "title": "热点股预览",
        },
    )


@api_router.get("/trade-dates")
def api_hot_stocks_trade_dates(
    limit: int = Query(90, ge=1, le=365),
    _user: dict = Depends(require_user),
):
    try:
        dates = hot_svc.list_trade_dates(limit)
        latest = dates[0] if dates else hot_svc.latest_trade_date()
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=f"查询交易日失败: {exc}") from exc
    return {"latest": latest, "dates": dates}


@api_router.get("/list")
def api_hot_stocks_list(
    trade_date: str | None = Query(None),
    hot_type: str = Query("人气榜"),
    market: str = Query(hot_svc.DEFAULT_MARKET),
    limit: int = Query(100, ge=1, le=200),
    _user: dict = Depends(require_user),
):
    try:
        return hot_svc.get_hot_stocks(trade_date, hot_type, market, limit)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=f"查询热榜失败: {exc}") from exc
