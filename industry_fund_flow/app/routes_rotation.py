from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from sqlalchemy.exc import SQLAlchemyError

from app.deps import require_user
from app.dc_registry import NAV_ITEMS
from app import rotation_service as r_svc

api_router = APIRouter(prefix="/api/v1/rotation", tags=["rotation-api"])
page_router = APIRouter(tags=["rotation-pages"])

_templates: Jinja2Templates | None = None


def init_rotation_routes(templates: Jinja2Templates) -> None:
    global _templates
    _templates = templates


def _page(request: Request, user: dict, template: str, active_nav: str, title: str) -> HTMLResponse:
    return _templates.TemplateResponse(
        request,
        template,
        {"user": user, "nav_items": NAV_ITEMS, "active_nav": active_nav, "title": title},
    )


@page_router.get("/rotation/strategies", response_class=HTMLResponse)
def page_strategies(request: Request, user: dict = Depends(require_user)):
    return _page(request, user, "rotation_strategies.html", "rotation-strategies", "选板块策略")


@page_router.get("/rotation/signals", response_class=HTMLResponse)
def page_signals(request: Request, user: dict = Depends(require_user)):
    return _page(request, user, "rotation_signals.html", "rotation-signals", "选板块信号")


@page_router.get("/rotation/backtest", response_class=HTMLResponse)
def page_backtest(request: Request, user: dict = Depends(require_user)):
    return _page(request, user, "rotation_backtest.html", "rotation-backtest", "选板块回测")


class StrategyBody(BaseModel):
    code: str | None = None
    name: str | None = None
    description: str | None = None
    config: dict | None = None
    is_active: bool | None = None


class BacktestBody(BaseModel):
    strategy_id: int
    start_date: str
    end_date: str
    init_capital: float | None = None
    name: str | None = None


@api_router.get("/strategies")
def api_list_strategies(user: dict = Depends(require_user)):
    try:
        return {"items": r_svc.list_strategies(user["id"])}
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@api_router.post("/strategies")
def api_create_strategy(body: StrategyBody, user: dict = Depends(require_user)):
    try:
        return r_svc.create_strategy(
            user["id"], body.code or "", body.name or "", body.description, body.config or {}
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@api_router.put("/strategies/{strategy_id}")
def api_update_strategy(strategy_id: int, body: StrategyBody, user: dict = Depends(require_user)):
    try:
        return r_svc.update_strategy(
            user["id"],
            strategy_id,
            name=body.name,
            description=body.description,
            config=body.config,
            is_active=body.is_active,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@api_router.delete("/strategies/{strategy_id}")
def api_delete_strategy(strategy_id: int, user: dict = Depends(require_user)):
    try:
        ok = r_svc.delete_strategy(user["id"], strategy_id)
        if not ok:
            raise HTTPException(status_code=404, detail="策略不存在")
        return {"ok": True}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@api_router.get("/strategies/{strategy_id}/signal-dates")
def api_signal_dates(strategy_id: int, _user: dict = Depends(require_user)):
    try:
        dates = r_svc.signal_trade_dates(strategy_id)
        return {"latest": dates[0] if dates else None, "dates": dates}
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@api_router.get("/strategies/{strategy_id}/signals")
def api_signals(
    strategy_id: int,
    trade_date: str | None = Query(None),
    _user: dict = Depends(require_user),
):
    try:
        return r_svc.list_signals(strategy_id, trade_date)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@api_router.get("/backtests")
def api_list_backtests(user: dict = Depends(require_user)):
    try:
        return {"items": r_svc.list_backtests(user["id"])}
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@api_router.post("/backtests")
def api_create_backtest(body: BacktestBody, user: dict = Depends(require_user)):
    try:
        run_id = r_svc.create_backtest(
            user["id"],
            body.strategy_id,
            body.start_date,
            body.end_date,
            body.init_capital or r_svc.DEFAULT_INIT_CAPITAL,
            body.name,
        )
        return {"run_id": run_id, "status": "pending"}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@api_router.get("/backtests/{run_id}")
def api_get_backtest(run_id: int, user: dict = Depends(require_user)):
    try:
        run = r_svc.get_backtest(user["id"], run_id)
        if not run:
            raise HTTPException(status_code=404, detail="回测不存在")
        return run
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
