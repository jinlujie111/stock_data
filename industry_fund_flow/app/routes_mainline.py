from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.exc import SQLAlchemyError

from app.deps import require_user
from app.dc_registry import CONTENT_TYPES, NAV_ITEMS
from app.dc_service import parse_csv_list
from app import mainline_service as ml_svc

api_router = APIRouter(prefix="/api/v1/mainline", tags=["mainline-api"])
page_router = APIRouter(tags=["mainline-pages"])

_templates: Jinja2Templates | None = None


def init_mainline_routes(templates: Jinja2Templates) -> None:
    global _templates
    _templates = templates


@page_router.get("/dc/mainline", response_class=HTMLResponse)
def mainline_page(request: Request, user: dict = Depends(require_user)):
    return _templates.TemplateResponse(
        request,
        "dc_mainline.html",
        {
            "user": user,
            "nav_items": NAV_ITEMS,
            "active_nav": "mainline",
            "content_types": CONTENT_TYPES,
            "title": "主线板块",
        },
    )


@api_router.get("/trade-dates")
def api_mainline_trade_dates(
    limit: int = Query(60, ge=1, le=365),
    _user: dict = Depends(require_user),
):
    try:
        dates = ml_svc.list_trade_dates(limit)
        latest = dates[0] if dates else ml_svc.latest_trade_date()
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=f"查询交易日失败: {exc}") from exc
    return {"latest": latest, "dates": dates}


@api_router.get("/rank")
def api_mainline_rank(
    trade_date: str | None = Query(None),
    content_types: str | None = Query(None),
    level: str | None = Query(None, description="等级过滤，逗号分隔"),
    top: int = Query(20, ge=1, le=200),
    ma_window: int = Query(5, ge=3, le=10),
    top20_only: bool = Query(False),
    industry_codes: str | None = Query(None, description="板块代码，逗号分隔"),
    _user: dict = Depends(require_user),
):
    try:
        if ma_window not in (3, 5, 10):
            raise ValueError("ma_window 仅支持 3、5、10")
        ctypes = parse_csv_list(content_types) or None
        codes = parse_csv_list(industry_codes) or None
        return ml_svc.get_rank(
            trade_date,
            ctypes,
            ml_svc.parse_levels_param(level),
            top,
            ma_window,
            top20_only,
            codes,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=f"查询主线榜失败: {exc}") from exc


@api_router.get("/boards/search")
def api_mainline_boards_search(
    trade_date: str | None = Query(None),
    content_types: str | None = Query(None),
    keyword: str | None = Query(None),
    limit: int = Query(30, ge=1, le=100),
    _user: dict = Depends(require_user),
):
    try:
        ctypes = parse_csv_list(content_types) or None
        return ml_svc.search_boards(trade_date, ctypes, keyword, limit)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=f"搜索板块失败: {exc}") from exc


@api_router.get("/history")
def api_mainline_history(
    industry_code: str = Query(...),
    trade_date: str | None = Query(None),
    days: int = Query(60, ge=1, le=365),
    _user: dict = Depends(require_user),
):
    try:
        return ml_svc.get_industry_history(industry_code, trade_date, days)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=f"查询历史得分失败: {exc}") from exc


@page_router.get("/api/rank/mainline")
def api_rank_mainline_legacy(
    trade_date: str | None = Query(None),
    content_types: str | None = Query(None),
    level: str | None = Query(None),
    top: int = Query(20, ge=1, le=200),
    ma_window: int = Query(5, ge=3, le=10),
    top20_only: bool = Query(False),
    user: dict = Depends(require_user),
):
    """需求文档 §4.5 兼容路径。"""
    return api_mainline_rank(
        trade_date=trade_date,
        content_types=content_types,
        level=level,
        top=top,
        ma_window=ma_window,
        top20_only=top20_only,
        _user=user,
    )
