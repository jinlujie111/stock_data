from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.exc import SQLAlchemyError

from app.deps import require_user
from app.dc_registry import DC_DIMENSIONS, NAV_ITEMS, get_dimension
from app.dc_service import (
    latest_trade_date,
    list_boards,
    list_trade_dates,
    parse_csv_list,
    parse_trade_date,
    query_dimension,
)
from app import fund_flow_service as ff_svc

api_router = APIRouter(prefix="/api/dc", tags=["dc-api"])
page_router = APIRouter(tags=["dc-pages"])

_templates: Jinja2Templates | None = None


def init_dc_routes(templates: Jinja2Templates) -> None:
    global _templates
    _templates = templates


def _ctx(user: dict, active_nav: str, **extra):
    return {
        "user": user,
        "nav_items": NAV_ITEMS,
        "active_nav": active_nav,
        "content_types": ["行业", "概念", "地域"],
        **extra,
    }


@page_router.get("/dc/{slug}", response_class=HTMLResponse)
def dc_list_page(slug: str, request: Request, user: dict = Depends(require_user)):
    try:
        dim = get_dimension(slug)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="未知维度") from exc
    template = "dc_fund_flow.html" if slug == "fund-flow" else "dc_list.html"
    page_cfg = {
        "slug": dim["slug"],
        "title": dim["title"],
        "columns": dim["columns"],
        "sort_hint": dim.get("sort_hint", ""),
        "default_sort_key": dim.get("default_sort_key", ""),
        "default_sort_dir": dim.get("default_sort_dir", "asc"),
    }
    if slug == "fund-flow":
        page_cfg["chart_default_boards"] = ff_svc.DEFAULT_CHART_BOARDS
    return _templates.TemplateResponse(
        request,
        template,
        _ctx(
            user,
            slug,
            dimension=dim,
            dimension_json=json.dumps(page_cfg, ensure_ascii=False),
        ),
    )


@api_router.get("/dimensions")
def api_dimensions(_user: dict = Depends(require_user)):
    return [
        {
            "slug": d["slug"],
            "title": d["title"],
            "subtitle": d["subtitle"],
            "href": f"/dc/{d['slug']}",
        }
        for d in DC_DIMENSIONS.values()
    ]


@api_router.get("/meta/trade-dates")
def api_trade_dates(
    slug: str = Query(...),
    limit: int = Query(60, ge=1, le=365),
    _user: dict = Depends(require_user),
):
    try:
        get_dimension(slug)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="未知维度") from exc
    try:
        dates = list_trade_dates(slug, limit)
        latest = dates[0] if dates else latest_trade_date(slug)
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=f"查询交易日失败: {exc}") from exc
    return {"slug": slug, "latest": latest, "dates": dates}


@api_router.get("/meta/boards")
def api_boards(
    slug: str = Query(...),
    trade_date: str = Query(...),
    content_types: str | None = Query(None),
    keyword: str | None = Query(None),
    _user: dict = Depends(require_user),
):
    try:
        get_dimension(slug)
        td = parse_trade_date(trade_date)
        if not td:
            raise ValueError("trade_date 必填")
        cts = parse_csv_list(content_types) or None
        boards = list_boards(slug, td, cts, keyword)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="未知维度") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=f"查询板块失败: {exc}") from exc
    return {"trade_date": td, "boards": boards}


@api_router.get("/fund-flow/trends")
def api_fund_flow_trends(
    trade_date: str | None = Query(None),
    industry_codes: str | None = Query(None),
    board_keywords: str | None = Query(None),
    days: int = Query(30, ge=1, le=120),
    _user: dict = Depends(require_user),
):
    try:
        codes = parse_csv_list(industry_codes) or None
        keywords = ff_svc.parse_board_keywords(board_keywords)
        return ff_svc.get_fund_flow_trends(trade_date, codes, keywords, days)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=f"查询趋势失败: {exc}") from exc


@api_router.get("/{slug}")
def api_dimension_list(
    slug: str,
    trade_date: str | None = Query(None),
    content_types: str | None = Query(None),
    industry_codes: str | None = Query(None),
    _user: dict = Depends(require_user),
):
    try:
        get_dimension(slug)
        td = parse_trade_date(trade_date) if trade_date else latest_trade_date(slug)
        if not td:
            raise HTTPException(status_code=404, detail="暂无交易数据")
        cts = parse_csv_list(content_types) or None
        codes = parse_csv_list(industry_codes) or None
        return query_dimension(slug, td, cts, codes)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="未知维度") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=f"查询失败: {exc}") from exc
