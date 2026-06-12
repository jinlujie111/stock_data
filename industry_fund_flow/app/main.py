from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import Cookie, Depends, FastAPI, Form, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app import auth_service
from app.config import APP_TITLE, COOKIE_NAME
from app.db import init_schema

_BASE = Path(__file__).resolve().parent
_STATIC = _BASE / "static"
_TEMPLATES = Jinja2Templates(directory=str(_BASE / "templates"))

app = FastAPI(title=APP_TITLE)
app.mount("/static", StaticFiles(directory=str(_STATIC)), name="static")


@app.on_event("startup")
def _startup() -> None:
    init_schema()


def current_user(iff_token: Annotated[str | None, Cookie(alias=COOKIE_NAME)] = None) -> dict | None:
    if not iff_token:
        return None
    payload = auth_service.decode_token(iff_token)
    if not payload:
        return None
    user = auth_service.get_user_by_id(int(payload["sub"]))
    return user


def require_user(user: dict | None = Depends(current_user)) -> dict:
    if not user:
        raise HTTPException(status_code=401, detail="未登录")
    return user


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
        {"title": APP_TITLE, "user": user},
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
