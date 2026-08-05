"""K 线分析页路由。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.exc import SQLAlchemyError

from app import chart_service as chart_svc
from app.deps import require_user
from app.dc_registry import NAV_ITEMS
from app.indicator_service import INDICATOR_KEYS
from app.sector_service import lookup_board, lookup_stock

page_router = APIRouter(tags=["chart-pages"])
api_router = APIRouter(prefix="/api/v1/chart", tags=["chart-api"])

_templates: Jinja2Templates | None = None

INDICATOR_OPTIONS = [
    {"key": "ma", "label": "均线"},
    {"key": "fibonacci", "label": "斐波那契"},
    {"key": "volume_price", "label": "量价关系"},
    {"key": "trendline", "label": "趋势线"},
]


def init_chart_routes(templates: Jinja2Templates) -> None:
    global _templates
    _templates = templates


@page_router.get("/dc/kline", response_class=HTMLResponse)
def kline_page(request: Request, user: dict = Depends(require_user)):
    raise HTTPException(status_code=404, detail="K线分析页已下线，请使用板块择时")


@api_router.get("/kline")
def api_chart_kline(
    kind: str = Query("stock", pattern="^(stock|board)$"),
    code: str = Query(..., min_length=1),
    trade_date: str | None = Query(None),
    days: int = Query(60, ge=20, le=365),
    _user: dict = Depends(require_user),
):
    try:
        if kind == "board":
            return chart_svc.get_board_kline(code, trade_date, days)
        return chart_svc.get_stock_kline(code, trade_date, days)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=f"查询 K 线失败: {exc}") from exc


@api_router.get("/search")
def api_chart_search(
    kind: str = Query("stock", pattern="^(stock|board)$"),
    keyword: str = Query(..., min_length=1),
    trade_date: str | None = Query(None),
    _user: dict = Depends(require_user),
):
    try:
        if kind == "board":
            return {"items": lookup_board(trade_date, keyword)}
        return {"items": lookup_stock(trade_date, keyword)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@api_router.get("/indicators")
def api_chart_indicators(_user: dict = Depends(require_user)):
    return {"items": INDICATOR_OPTIONS, "keys": list(INDICATOR_KEYS)}
