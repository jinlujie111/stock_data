from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from sqlalchemy.exc import SQLAlchemyError

from app.deps import require_user
from app.dc_registry import CONTENT_TYPES, NAV_ITEMS
from app.dc_service import parse_csv_list, parse_trade_date
from app import favorite_service as fav_svc
from app import sector_service as sec_svc
from app import chart_service as chart_svc

api_router = APIRouter(prefix="/api/v1/sectors", tags=["sectors-api"])
fav_router = APIRouter(prefix="/api/v1/favorites", tags=["favorites-api"])
page_router = APIRouter(tags=["sectors-pages"])

_templates: Jinja2Templates | None = None


def init_sectors_routes(templates: Jinja2Templates) -> None:
    global _templates
    _templates = templates


def _render_favorites_page(request: Request, user: dict, title: str, active_nav: str, template_name: str, favorites_kind: str) -> HTMLResponse:
    return _templates.TemplateResponse(
        request,
        template_name,
        {
            "user": user,
            "nav_items": NAV_ITEMS,
            "active_nav": active_nav,
            "title": title,
            "favorites_kind": favorites_kind,
        },
    )


class BoardFavoriteBody(BaseModel):
    industry_code: str
    industry_name: str | None = None
    content_type: str | None = None


class StockFavoriteBody(BaseModel):
    ts_code: str
    stock_name: str | None = None


@page_router.get("/dc/sectors", response_class=HTMLResponse)
def sectors_page(request: Request, user: dict = Depends(require_user)):
    return _templates.TemplateResponse(
        request,
        "dc_sectors.html",
        {
            "user": user,
            "nav_items": NAV_ITEMS,
            "active_nav": "sectors",
            "content_types": CONTENT_TYPES,
            "title": "行业板块",
        },
    )


@page_router.get("/favorites/boards", response_class=HTMLResponse)
def board_favorites_page(request: Request, user: dict = Depends(require_user)):
    return _templates.TemplateResponse(
        request,
        "favorites_board.html",
        {
            "user": user,
            "nav_items": NAV_ITEMS,
            "active_nav": "board-favorites",
            "title": "板块自选",
            "favorites_kind": "board",
            "content_types": CONTENT_TYPES,
        },
    )


@page_router.get("/favorites/stocks", response_class=HTMLResponse)
def stock_favorites_page(request: Request, user: dict = Depends(require_user)):
    return _templates.TemplateResponse(
        request,
        "favorites_stock.html",
        {
            "user": user,
            "nav_items": NAV_ITEMS,
            "active_nav": "stock-favorites",
            "title": "股票自选",
            "favorites_kind": "stock",
        },
    )


@api_router.get("/trade-dates")
def api_sectors_trade_dates(
    limit: int = Query(90, ge=1, le=365),
    _user: dict = Depends(require_user),
):
    try:
        dates = sec_svc.list_trade_dates(limit)
        latest = dates[0] if dates else sec_svc.latest_trade_date()
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=f"查询交易日失败: {exc}") from exc
    return {"latest": latest, "dates": dates}


def _resolve_fav_trade_date(trade_date: str | None) -> str:
    if trade_date:
        td = parse_trade_date(trade_date)
        if not td:
            raise ValueError("trade_date 无效")
        return td
    latest = sec_svc.latest_trade_date()
    if not latest:
        raise ValueError("暂无板块交易日数据")
    return latest


@api_router.get("/list")
def api_sectors_list(
    trade_date: str | None = Query(None),
    content_type: str = Query("行业"),
    keyword: str | None = Query(None),
    industry_codes: str | None = Query(None, description="逗号分隔板块代码"),
    limit: int = Query(500, ge=1, le=1000),
    _user: dict = Depends(require_user),
):
    try:
        codes = parse_csv_list(industry_codes) if industry_codes else None
        return sec_svc.get_sector_list(trade_date, content_type, keyword, limit, codes)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=f"查询板块列表失败: {exc}") from exc


@api_router.get("/lookup/board")
def api_lookup_board(
    keyword: str = Query(..., min_length=1),
    trade_date: str | None = Query(None),
    _user: dict = Depends(require_user),
):
    try:
        return {"items": sec_svc.lookup_board(trade_date, keyword)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@api_router.get("/lookup/stock")
def api_lookup_stock(
    keyword: str = Query(..., min_length=1),
    trade_date: str | None = Query(None),
    _user: dict = Depends(require_user),
):
    try:
        return {"items": sec_svc.lookup_stock(trade_date, keyword)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@api_router.get("/stock/{ts_code}/kline")
def api_stock_kline(
    ts_code: str,
    trade_date: str | None = Query(None),
    days: int = Query(120, ge=20, le=365),
    _user: dict = Depends(require_user),
):
    try:
        return chart_svc.get_stock_kline(ts_code, trade_date, days)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=f"查询 K 线失败: {exc}") from exc


@api_router.get("/{industry_code}/kline")
def api_board_kline(
    industry_code: str,
    trade_date: str | None = Query(None),
    days: int = Query(120, ge=20, le=365),
    _user: dict = Depends(require_user),
):
    try:
        return chart_svc.get_board_kline(industry_code, trade_date, days)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=f"查询 K 线失败: {exc}") from exc


@api_router.get("/{industry_code}/members")
def api_sector_members(
    industry_code: str,
    trade_date: str | None = Query(None),
    limit: int = Query(500, ge=1, le=2000),
    _user: dict = Depends(require_user),
):
    try:
        return sec_svc.get_sector_members(industry_code, trade_date, limit)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=f"查询成分股失败: {exc}") from exc


@fav_router.get("/boards/table")
def api_board_favorites_table(
    trade_date: str | None = Query(None),
    content_type: str = Query("全部"),
    industry_codes: str | None = Query(None, description="逗号分隔，筛选自选板块子集"),
    user: dict = Depends(require_user),
):
    try:
        codes = parse_csv_list(industry_codes) if industry_codes else None
        return fav_svc.get_board_favorites_table(
            user["id"], trade_date, content_type, codes
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@fav_router.get("/boards")
def api_list_board_favorites(
    trade_date: str | None = Query(None),
    user: dict = Depends(require_user),
):
    try:
        td = _resolve_fav_trade_date(trade_date) if trade_date else None
        return {"items": fav_svc.list_board_favorites(user["id"], td)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@fav_router.post("/boards")
def api_add_board_favorite(body: BoardFavoriteBody, user: dict = Depends(require_user)):
    try:
        return fav_svc.add_board_favorite(
            user["id"], body.industry_code, body.industry_name, body.content_type
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@fav_router.delete("/boards/{industry_code}")
def api_remove_board_favorite(industry_code: str, user: dict = Depends(require_user)):
    try:
        ok = fav_svc.remove_board_favorite(user["id"], industry_code)
        if not ok:
            raise HTTPException(status_code=404, detail="未找到自选板块")
        return {"ok": True}
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@fav_router.get("/stocks")
def api_list_stock_favorites(
    trade_date: str | None = Query(None),
    user: dict = Depends(require_user),
):
    try:
        td = _resolve_fav_trade_date(trade_date)
        return {"items": fav_svc.list_stock_favorites(user["id"], td), "trade_date": td}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@fav_router.post("/stocks")
def api_add_stock_favorite(body: StockFavoriteBody, user: dict = Depends(require_user)):
    try:
        return fav_svc.add_stock_favorite(user["id"], body.ts_code, body.stock_name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@fav_router.delete("/stocks/{ts_code}")
def api_remove_stock_favorite(ts_code: str, user: dict = Depends(require_user)):
    try:
        ok = fav_svc.remove_stock_favorite(user["id"], ts_code)
        if not ok:
            raise HTTPException(status_code=404, detail="未找到自选股票")
        return {"ok": True}
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
