"""VIP 板块启动信号：短期 / 中期报表页面与 API。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.exc import SQLAlchemyError

from app.deps import require_user
from app.dc_registry import CONTENT_TYPES, NAV_ITEMS
from app import start_signal_service as ss_svc

api_router = APIRouter(prefix="/api/v1/start-signal", tags=["start-signal-api"])
page_router = APIRouter(tags=["start-signal-pages"])

_templates: Jinja2Templates | None = None

PAGE_META = {
    "short": {
        "active_nav": "vip-start-short",
        "title": "VIP-短期板块启动",
        "subtitle": "1~5 天启动筛选：抓异动方向、量价与短期资金加速（文档 §11.1）",
        "mode": "short",
    },
    "mid": {
        "active_nav": "vip-start-mid",
        "title": "VIP-中期板块启动",
        "subtitle": "1~8 周主升跟踪：主线等级、均线走强与持续资金流入（文档 §11.2）",
        "mode": "mid",
    },
}


def init_start_signal_routes(templates: Jinja2Templates) -> None:
    global _templates
    _templates = templates


def _page(request: Request, user: dict, mode: str):
    meta = PAGE_META[mode]
    return _templates.TemplateResponse(
        request,
        "dc_start_signal.html",
        {
            "user": user,
            "nav_items": NAV_ITEMS,
            "active_nav": meta["active_nav"],
            "content_types": [ct for ct in CONTENT_TYPES if ct in ("行业", "概念")],
            "title": meta["title"],
            "subtitle": meta["subtitle"],
            "mode": meta["mode"],
        },
    )


@page_router.get("/vip/start-short", response_class=HTMLResponse)
def start_short_page(request: Request, user: dict = Depends(require_user)):
    return _page(request, user, "short")


@page_router.get("/vip/start-mid", response_class=HTMLResponse)
def start_mid_page(request: Request, user: dict = Depends(require_user)):
    return _page(request, user, "mid")


@api_router.get("/trade-dates")
def api_trade_dates(
    limit: int = Query(60, ge=1, le=365),
    _user: dict = Depends(require_user),
):
    try:
        dates = ss_svc.list_trade_dates(limit)
        latest = dates[0] if dates else ss_svc.latest_trade_date()
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=f"查询交易日失败: {exc}") from exc
    return {"latest": latest, "dates": dates}


@api_router.get("/evaluate")
def api_evaluate(
    trade_date: str | None = Query(None),
    mode: str = Query("short", description="short | mid"),
    content_types: str | None = Query("行业,概念"),
    status: str | None = Query(None, description="启动/观察/放弃"),
    top: int = Query(100, ge=1, le=500),
    _user: dict = Depends(require_user),
):
    if mode not in (ss_svc.MODE_SHORT, ss_svc.MODE_MID):
        raise HTTPException(status_code=400, detail="mode 仅支持 short / mid")
    try:
        return ss_svc.evaluate(
            trade_date,
            mode=mode,
            content_types=content_types,
            status_filter=status,
            top=top,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=f"查询启动信号失败: {exc}") from exc
