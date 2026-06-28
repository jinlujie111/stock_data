from __future__ import annotations

import logging
from pathlib import Path

from fastapi import Depends, FastAPI, Form, HTTPException, Query, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.exc import SQLAlchemyError

from app import auth_service, routes_ai_core, routes_dc, routes_dragon, routes_mainline, routes_quant_mainline
from app.config import APP_TITLE, COOKIE_NAME
from app.db import init_schema
from app.deps import current_user, require_user
from app.dc_registry import NAV_ITEMS
from app import market_breadth_service as mb_svc

logger = logging.getLogger(__name__)

_BASE = Path(__file__).resolve().parent
_STATIC = _BASE / "static"
_TEMPLATES = Jinja2Templates(directory=str(_BASE / "templates"))

app = FastAPI(title=APP_TITLE)
app.mount("/static", StaticFiles(directory=str(_STATIC)), name="static")

routes_dc.init_dc_routes(_TEMPLATES)
routes_dragon.init_dragon_routes(_TEMPLATES)
routes_mainline.init_mainline_routes(_TEMPLATES)
routes_quant_mainline.init_quant_mainline_routes(_TEMPLATES)
routes_ai_core.init_ai_core_routes(_TEMPLATES)
app.include_router(routes_mainline.page_router)
app.include_router(routes_mainline.api_router)
app.include_router(routes_quant_mainline.page_router)
app.include_router(routes_quant_mainline.api_router)
app.include_router(routes_dragon.page_router)
app.include_router(routes_dragon.api_router)
app.include_router(routes_ai_core.page_router)
app.include_router(routes_ai_core.api_router)
app.include_router(routes_dc.page_router)
app.include_router(routes_dc.api_router)


@app.on_event("startup")
def _startup() -> None:
    try:
        init_schema()
        logger.info("app_user 表已就绪")
    except SQLAlchemyError as exc:
        logger.error("初始化数据库失败: %s", exc)


@app.exception_handler(SQLAlchemyError)
async def db_error_handler(_request: Request, exc: SQLAlchemyError):
    logger.exception("数据库错误")
    return JSONResponse(status_code=500, content={"detail": f"数据库错误: {exc}"})


@app.exception_handler(Exception)
async def generic_error_handler(_request: Request, exc: Exception):
    if isinstance(exc, HTTPException):
        raise exc
    logger.exception("未处理异常")
    return JSONResponse(status_code=500, content={"detail": str(exc) or "服务器内部错误"})


def _set_auth_cookie(response: Response, user: dict) -> None:
    token = auth_service.create_access_token(user["id"], user["username"])
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        max_age=60 * 60 * 24 * 7,
        samesite="lax",
        path="/",
    )


@app.get("/", response_class=HTMLResponse)
def home(request: Request, user: dict | None = Depends(current_user)):
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    return _TEMPLATES.TemplateResponse(
        request,
        "home.html",
        {
            "title": APP_TITLE,
            "user": user,
            "nav_items": NAV_ITEMS,
            "active_nav": "home",
        },
    )


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request, user: dict | None = Depends(current_user)):
    if user:
        return RedirectResponse(url="/", status_code=303)
    return _TEMPLATES.TemplateResponse(
        request,
        "login.html",
        {"title": f"登录 - {APP_TITLE}", "error": None},
    )


@app.get("/register", response_class=HTMLResponse)
def register_page(request: Request, user: dict | None = Depends(current_user)):
    if user:
        return RedirectResponse(url="/", status_code=303)
    return _TEMPLATES.TemplateResponse(
        request,
        "register.html",
        {"title": f"注册 - {APP_TITLE}", "error": None},
    )


@app.post("/register")
def register_submit(
    username: str = Form(...),
    password: str = Form(...),
    password2: str = Form(...),
    email: str = Form(""),
):
    if password != password2:
        raise HTTPException(status_code=400, detail="两次密码不一致")
    try:
        user = auth_service.register_user(username, password, email or None)
    except auth_service.AuthError as exc:
        raise HTTPException(status_code=400, detail=exc.message) from exc
    except SQLAlchemyError as exc:
        logger.exception("注册写库失败")
        raise HTTPException(status_code=500, detail=f"数据库错误，请检查 MySQL 与 app_user 表: {exc}") from exc
    resp = RedirectResponse(url="/", status_code=303)
    _set_auth_cookie(resp, user)
    return resp


@app.post("/login")
def login_submit(
    username: str = Form(...),
    password: str = Form(...),
):
    try:
        user = auth_service.login_user(username, password)
    except auth_service.AuthError as exc:
        raise HTTPException(status_code=400, detail=exc.message) from exc
    resp = RedirectResponse(url="/", status_code=303)
    _set_auth_cookie(resp, user)
    return resp


@app.post("/logout")
def logout():
    resp = RedirectResponse(url="/login", status_code=303)
    resp.delete_cookie(COOKIE_NAME, path="/")
    return resp


@app.get("/api/me")
def api_me(user: dict = Depends(require_user)):
    return {
        "id": user["id"],
        "username": user["username"],
        "email": user.get("email"),
    }


@app.get("/api/market-breadth/trade-dates")
def api_market_breadth_dates(
    limit: int = Query(60, ge=1, le=365),
    _user: dict = Depends(require_user),
):
    try:
        dates = mb_svc.list_trade_dates(limit)
        latest = dates[0] if dates else mb_svc.latest_trade_date()
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=f"查询交易日失败: {exc}") from exc
    return {"latest": latest, "dates": dates}


@app.get("/api/market-breadth/history")
def api_market_breadth_history(
    days: int = Query(30, ge=1, le=365),
    _user: dict = Depends(require_user),
):
    try:
        return mb_svc.get_market_breadth_history(days)
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=f"查询市场广度历史失败: {exc}") from exc


@app.get("/api/market-breadth")
def api_market_breadth(
    trade_date: str | None = Query(None),
    _user: dict = Depends(require_user),
):
    try:
        return mb_svc.get_market_breadth(trade_date)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=f"查询市场广度失败: {exc}") from exc
