from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.exc import SQLAlchemyError

from app.deps import require_user
from app.dc_registry import NAV_ITEMS
from app import vp_service as vp_svc

api_router = APIRouter(prefix="/api/v1/vp", tags=["vp-api"])
page_router = APIRouter(tags=["vp-pages"])

_templates: Jinja2Templates | None = None


def init_vp_routes(templates: Jinja2Templates) -> None:
    global _templates
    _templates = templates


@page_router.get("/dc/volume-price", response_class=HTMLResponse)
def volume_price_page(request: Request, user: dict = Depends(require_user)):
    raise HTTPException(status_code=404, detail="板块量价已下线（决策链路已移除）")


@api_router.get("/trade-dates")
def api_vp_trade_dates(
    limit: int = Query(120, ge=1, le=183),
    _user: dict = Depends(require_user),
):
    try:
        dates = vp_svc.list_trade_dates(limit)
        latest = dates[0] if dates else vp_svc.latest_trade_date()
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=f"查询交易日失败: {exc}") from exc
    return {"latest": latest, "dates": dates}


@api_router.get("/boards/search")
def api_vp_board_search(
    trade_date: str | None = Query(None),
    content_types: str = Query("行业,概念"),
    keyword: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    _user: dict = Depends(require_user),
):
    try:
        return vp_svc.search_boards(
            trade_date,
            content_types=content_types,
            keyword=keyword,
            limit=limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=f"查询板块列表失败: {exc}") from exc


@api_router.get("/industries/rank")
def api_vp_industries_rank(
    trade_date: str | None = Query(None),
    content_types: str = Query("行业,概念"),
    industry_codes: str | None = Query(None, description="板块代码，逗号分隔"),
    window: int = Query(20, ge=3, le=120),
    top: int = Query(50, ge=1, le=200),
    sort: str = Query("vp_score"),
    _user: dict = Depends(require_user),
):
    codes = [x.strip() for x in (industry_codes or "").split(",") if x.strip()] or None
    try:
        return vp_svc.rank_industries(
            trade_date,
            content_types=content_types,
            industry_codes=codes,
            window=window,
            top=top,
            sort=sort,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=f"查询排行榜失败: {exc}") from exc


@api_router.get("/industries/{industry_code}")
def api_vp_industry_detail(
    industry_code: str,
    trade_date: str | None = Query(None),
    window: int = Query(20, ge=3, le=120),
    _user: dict = Depends(require_user),
):
    try:
        return vp_svc.get_industry_detail(industry_code, trade_date, window=window)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=f"查询板块详情失败: {exc}") from exc


@api_router.get("/industries/{industry_code}/stocks")
def api_vp_industry_stocks(
    industry_code: str,
    trade_date: str | None = Query(None),
    window: int = Query(20, ge=3, le=120),
    limit: int = Query(100, ge=1, le=500),
    sort: str = Query("vol_ratio_20"),
    order: str = Query("desc", description="asc 或 desc"),
    _user: dict = Depends(require_user),
):
    try:
        return vp_svc.list_industry_stocks(
            industry_code,
            trade_date,
            window=window,
            limit=limit,
            sort=sort,
            order=order,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=f"查询成分股失败: {exc}") from exc


@api_router.get("/industries/{industry_code}/kline")
def api_vp_industry_kline(
    industry_code: str,
    trade_date: str | None = Query(None, description="区间结束日 YYYYMMDD"),
    start_date: str | None = Query(None, description="区间开始日 YYYYMMDD"),
    days: int = Query(60, ge=5, le=365, description="未指定 start_date 时向前交易日数"),
    window: int = Query(20, ge=3, le=120),
    _user: dict = Depends(require_user),
):
    try:
        return vp_svc.get_industry_vp_kline(
            industry_code,
            trade_date,
            start_date=start_date,
            days=days,
            window=window,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=f"查询 K 线失败: {exc}") from exc


@api_router.get("/signals")
def api_vp_signals(
    trade_date: str | None = Query(None),
    signal_type: str | None = Query(None),
    industry_codes: str | None = Query(None, description="板块代码，逗号分隔"),
    window: int = Query(20, ge=3, le=120),
    top: int = Query(50, ge=1, le=200),
    _user: dict = Depends(require_user),
):
    codes = [x.strip() for x in (industry_codes or "").split(",") if x.strip()] or None
    try:
        return vp_svc.list_signals(
            trade_date,
            signal_type=signal_type,
            industry_codes=codes,
            window=window,
            top=top,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=f"查询信号失败: {exc}") from exc
