"""东财板块四因子择时 Web 路由。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
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


@page_router.get("/dc/timing-kline", response_class=HTMLResponse)
def timing_kline_page(request: Request, user: dict = Depends(require_user)):
    """兼容旧入口：合并进板块择时工作台。"""
    qs = request.url.query
    target = "/dc/board-timing"
    if qs:
        target = f"{target}?{qs}"
    return RedirectResponse(url=target, status_code=302)


@api_router.get("/trade-dates")
def api_timing_trade_dates(
    limit: int = Query(120, ge=1, le=730),
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
    mainline_levels: str | None = Query(None, description="主线等级过滤,逗号分隔"),
    vp_status: str | None = Query(None, description="量价状态过滤,逗号分隔"),
    with_metrics: bool = Query(True),
    _user: dict = Depends(require_user),
):
    try:
        return timing_svc.rank_boards(
            trade_date,
            content_types=content_types,
            signal_type=signal_type,
            top=top,
            sort=sort,
            mainline_levels=mainline_levels,
            vp_status=vp_status,
            with_metrics=with_metrics,
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


@api_router.get("/backtest/summary")
def api_timing_bt_summary(
    run_code: str = Query("daily_default"),
    _user: dict = Depends(require_user),
):
    try:
        return timing_svc.get_backtest_summary(run_code)
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=f"查询回测摘要失败: {exc}") from exc


@api_router.get("/backtest/metrics")
def api_timing_bt_metrics(
    run_code: str = Query("daily_default"),
    content_types: str = Query("行业,概念"),
    top: int = Query(50, ge=1, le=200),
    sort: str = Query("total_return"),
    _user: dict = Depends(require_user),
):
    try:
        return timing_svc.list_board_metrics(
            run_code=run_code,
            content_types=content_types,
            top=top,
            sort=sort,
        )
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=f"查询回测指标失败: {exc}") from exc


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


@api_router.get("/boards/{industry_code}/trades")
def api_timing_board_trades(
    industry_code: str,
    run_code: str = Query("daily_default"),
    limit: int = Query(100, ge=1, le=500),
    _user: dict = Depends(require_user),
):
    try:
        return timing_svc.get_board_trades(
            industry_code, run_code=run_code, limit=limit
        )
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=f"查询成交明细失败: {exc}") from exc


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
