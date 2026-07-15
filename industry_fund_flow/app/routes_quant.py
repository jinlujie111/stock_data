from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from sqlalchemy.exc import SQLAlchemyError

from app.deps import require_user
from app.dc_registry import NAV_ITEMS
from app import quant_service as q_svc

api_router = APIRouter(prefix="/api/v1/quant", tags=["quant-api"])
page_router = APIRouter(tags=["quant-pages"])

_templates: Jinja2Templates | None = None


def init_quant_routes(templates: Jinja2Templates) -> None:
    global _templates
    _templates = templates


def _page(request: Request, user: dict, template: str, active_nav: str, title: str) -> HTMLResponse:
    return _templates.TemplateResponse(
        request,
        template,
        {"user": user, "nav_items": NAV_ITEMS, "active_nav": active_nav, "title": title},
    )


# ----------------------------- Pages -----------------------------
@page_router.get("/quant/strategies", response_class=HTMLResponse)
def page_strategies(request: Request, user: dict = Depends(require_user)):
    return _page(request, user, "quant_strategies.html", "quant-strategies", "量化策略")


@page_router.get("/quant/signals", response_class=HTMLResponse)
def page_signals(request: Request, user: dict = Depends(require_user)):
    return _page(request, user, "quant_signals.html", "quant-signals", "选股信号")


@page_router.get("/quant/backtest", response_class=HTMLResponse)
def page_backtest(request: Request, user: dict = Depends(require_user)):
    return _page(request, user, "quant_backtest.html", "quant-backtest", "策略回测")


@page_router.get("/quant/trades", response_class=HTMLResponse)
def page_trades(request: Request, user: dict = Depends(require_user)):
    return _page(request, user, "quant_trades.html", "quant-trades", "买卖点记录")


# ----------------------------- Models -----------------------------
class StrategyBody(BaseModel):
    code: str | None = None
    name: str | None = None
    horizon: str = "short"
    description: str | None = None
    config: dict | None = None
    is_active: bool | None = None


class BacktestBody(BaseModel):
    strategy_id: int
    start_date: str
    end_date: str
    init_capital: float | None = None
    name: str | None = None


class TradeBody(BaseModel):
    ts_code: str
    side: str
    trade_date: str
    price: float
    shares: int | None = None
    stock_name: str | None = None
    note: str | None = None
    strategy_id: int | None = None


# ----------------------------- Strategy API -----------------------------
@api_router.get("/strategies")
def api_list_strategies(user: dict = Depends(require_user)):
    try:
        return {"items": q_svc.list_strategies(user["id"])}
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@api_router.post("/strategies")
def api_create_strategy(body: StrategyBody, user: dict = Depends(require_user)):
    try:
        return q_svc.create_strategy(
            user["id"], body.code or "", body.name or "", body.horizon,
            body.description, body.config or {},
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@api_router.put("/strategies/{strategy_id}")
def api_update_strategy(strategy_id: int, body: StrategyBody, user: dict = Depends(require_user)):
    try:
        return q_svc.update_strategy(
            user["id"], strategy_id, name=body.name, description=body.description,
            config=body.config, is_active=body.is_active,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@api_router.delete("/strategies/{strategy_id}")
def api_delete_strategy(strategy_id: int, user: dict = Depends(require_user)):
    try:
        ok = q_svc.delete_strategy(user["id"], strategy_id)
        if not ok:
            raise HTTPException(status_code=404, detail="策略不存在")
        return {"ok": True}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# ----------------------------- Signals API -----------------------------
@api_router.get("/strategies/{strategy_id}/signal-dates")
def api_signal_dates(strategy_id: int, _user: dict = Depends(require_user)):
    try:
        dates = q_svc.signal_trade_dates(strategy_id)
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
        return q_svc.list_signals(strategy_id, trade_date)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# ----------------------------- Backtest API -----------------------------
@api_router.get("/backtests")
def api_list_backtests(user: dict = Depends(require_user)):
    try:
        return {"items": q_svc.list_backtests(user["id"])}
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@api_router.post("/backtests")
def api_create_backtest(body: BacktestBody, user: dict = Depends(require_user)):
    try:
        run_id = q_svc.create_backtest(
            user["id"], body.strategy_id, body.start_date, body.end_date,
            body.init_capital or q_svc.DEFAULT_INIT_CAPITAL, body.name,
        )
        return {"run_id": run_id, "status": "pending"}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@api_router.get("/backtests/{run_id}")
def api_get_backtest(run_id: int, user: dict = Depends(require_user)):
    try:
        run = q_svc.get_backtest(user["id"], run_id)
        if not run:
            raise HTTPException(status_code=404, detail="回测不存在")
        return run
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# ----------------------------- Trades API -----------------------------
@api_router.get("/trades")
def api_list_trades(
    ts_code: str | None = Query(None),
    user: dict = Depends(require_user),
):
    try:
        return {"items": q_svc.list_trades(user["id"], ts_code)}
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@api_router.post("/trades")
def api_add_trade(body: TradeBody, user: dict = Depends(require_user)):
    try:
        return q_svc.add_trade(
            user["id"], body.ts_code, body.side, body.trade_date, body.price,
            body.shares, body.stock_name, body.note,
            source="strategy" if body.strategy_id else "manual",
            strategy_id=body.strategy_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@api_router.delete("/trades/{trade_id}")
def api_delete_trade(trade_id: int, user: dict = Depends(require_user)):
    try:
        ok = q_svc.delete_trade(user["id"], trade_id)
        if not ok:
            raise HTTPException(status_code=404, detail="记录不存在")
        return {"ok": True}
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@api_router.get("/positions")
def api_positions(user: dict = Depends(require_user)):
    try:
        return {"items": q_svc.positions_summary(user["id"])}
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
