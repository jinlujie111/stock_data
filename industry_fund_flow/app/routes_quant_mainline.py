from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.exc import SQLAlchemyError

from app.deps import require_user
from app.dc_registry import CONTENT_TYPES, NAV_ITEMS
from app.dc_service import parse_csv_list
from app import quant_mainline_service as qm_svc

api_router = APIRouter(prefix="/api/v1/quant-mainline", tags=["quant-mainline-api"])
page_router = APIRouter(tags=["quant-mainline-pages"])

_templates: Jinja2Templates | None = None


def init_quant_mainline_routes(templates: Jinja2Templates) -> None:
    global _templates
    _templates = templates


@page_router.get("/dc/quant-mainline", response_class=HTMLResponse)
def quant_mainline_page(request: Request, user: dict = Depends(require_user)):
    return _templates.TemplateResponse(
        request,
        "dc_quant_mainline.html",
        {
            "user": user,
            "nav_items": NAV_ITEMS,
            "active_nav": "quant-mainline",
            "content_types": CONTENT_TYPES,
            "title": "量化主线",
        },
    )


@api_router.get("/trade-dates")
def api_qm_trade_dates(
    limit: int = Query(60, ge=1, le=365),
    _user: dict = Depends(require_user),
):
    try:
        dates = qm_svc.list_trade_dates(limit)
        latest = dates[0] if dates else qm_svc.latest_trade_date()
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=f"查询交易日失败: {exc}") from exc
    return {"latest": latest, "dates": dates}


@api_router.get("/top")
def api_qm_top(
    trade_date: str | None = Query(None),
    content_types: str | None = Query(None, description="单一类型：行业 或 概念"),
    top: int = Query(10, ge=1, le=50),
    top_only: bool = Query(True),
    ma_window: int = Query(5, ge=3, le=10),
    _user: dict = Depends(require_user),
):
    try:
        if ma_window not in (3, 5, 10):
            raise ValueError("ma_window 仅支持 3、5、10")
        ctypes = parse_csv_list(content_types) or ["行业"]
        return qm_svc.get_top(trade_date, ctypes, top, top_only, ma_window)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=f"查询 Top 失败: {exc}") from exc


@api_router.get("/top-groups")
def api_qm_top_groups(
    trade_date: str | None = Query(None),
    content_types: str | None = Query(None, description="行业,概念 或子集"),
    top: int = Query(10, ge=1, le=50),
    top_only: bool = Query(True),
    ma_window: int = Query(5, ge=3, le=10),
    _user: dict = Depends(require_user),
):
    try:
        if ma_window not in (3, 5, 10):
            raise ValueError("ma_window 仅支持 3、5、10")
        ctypes = parse_csv_list(content_types) or None
        return qm_svc.get_top_groups(trade_date, ctypes, top, top_only, ma_window)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=f"查询 Top 分组失败: {exc}") from exc


@api_router.get("/signals")
def api_qm_signals(
    trade_date: str | None = Query(None),
    content_types: str | None = Query(None),
    status: str | None = Query(None, description="启动/退潮/观察"),
    limit: int = Query(100, ge=1, le=500),
    _user: dict = Depends(require_user),
):
    try:
        ctypes = parse_csv_list(content_types) or None
        return qm_svc.get_signals(trade_date, ctypes, status, limit)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=f"查询信号失败: {exc}") from exc


@api_router.get("/history")
def api_qm_history(
    industry_code: str = Query(...),
    trade_date: str | None = Query(None),
    days: int = Query(60, ge=5, le=365),
    _user: dict = Depends(require_user),
):
    try:
        return qm_svc.get_history(industry_code, trade_date, days)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=f"查询历史失败: {exc}") from exc


@api_router.get("/config")
def api_qm_config(_user: dict = Depends(require_user)):
    try:
        return qm_svc.get_config()
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=f"查询配置失败: {exc}") from exc
