from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.exc import SQLAlchemyError

from app.deps import require_user
from app.dc_registry import NAV_ITEMS
from app import sentiment_service as sentiment_svc

api_router = APIRouter(prefix="/api/v1/sentiment", tags=["sentiment-api"])
page_router = APIRouter(tags=["sentiment-pages"])

_templates: Jinja2Templates | None = None


def init_sentiment_routes(templates: Jinja2Templates) -> None:
    global _templates
    _templates = templates


@page_router.get("/dc/sentiment", response_class=HTMLResponse)
def sentiment_page(request: Request, user: dict = Depends(require_user)):
    return _templates.TemplateResponse(
        request,
        "dc_sentiment.html",
        {
            "user": user,
            "nav_items": NAV_ITEMS,
            "active_nav": "sentiment",
            "title": "板块情绪",
        },
    )


@api_router.get("/trade-dates")
def api_trade_dates(
    limit: int = Query(90, ge=1, le=365),
    _user: dict = Depends(require_user),
):
    try:
        dates = sentiment_svc.list_trade_dates(limit)
        latest = dates[0] if dates else sentiment_svc.latest_trade_date()
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=f"查询交易日失败: {exc}") from exc
    return {"latest": latest, "dates": dates}


@api_router.get("/resolve-board")
def api_resolve_board(
    industry_code: str | None = Query(None),
    keyword: str | None = Query(None),
    trade_date: str | None = Query(None),
    _user: dict = Depends(require_user),
):
    try:
        board = sentiment_svc.resolve_board(industry_code, keyword, trade_date)
        return {"item": board}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=f"查询板块失败: {exc}") from exc


@api_router.get("/history")
def api_history(
    industry_code: str | None = Query(None),
    keyword: str | None = Query(None),
    trade_date: str | None = Query(None),
    days: int = Query(30, ge=30, le=365),
    _user: dict = Depends(require_user),
):
    try:
        return sentiment_svc.get_sentiment_history(
            industry_code,
            keyword=keyword,
            trade_date=trade_date,
            days=days,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=f"查询情绪历史失败: {exc}") from exc
