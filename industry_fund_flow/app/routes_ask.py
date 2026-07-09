from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
from sqlalchemy.exc import SQLAlchemyError

from app import ask_service as ask_svc
from app.deps import require_user
from app.dc_registry import NAV_ITEMS

api_router = APIRouter(prefix="/api/v1/ask", tags=["ask-api"])
page_router = APIRouter(tags=["ask-pages"])

_templates: Jinja2Templates | None = None


def init_ask_routes(templates: Jinja2Templates) -> None:
    global _templates
    _templates = templates


class AskBody(BaseModel):
    question: str = Field(..., min_length=1, max_length=500)
    trade_date: str | None = None
    session_id: str | None = Field(None, max_length=64)


@page_router.get("/ask", response_class=HTMLResponse)
def ask_page(request: Request, user: dict = Depends(require_user)):
    return _templates.TemplateResponse(
        request,
        "ask.html",
        {
            "user": user,
            "nav_items": NAV_ITEMS,
            "active_nav": "ask",
            "title": "问数助手",
            "suggestions": ask_svc.list_suggestions(),
        },
    )


@api_router.get("/suggestions")
def api_ask_suggestions(_user: dict = Depends(require_user)):
    return {"items": ask_svc.list_suggestions()}


@api_router.post("")
def api_ask(body: AskBody, user: dict = Depends(require_user)):
    try:
        return ask_svc.ask(
            body.question.strip(),
            body.trade_date,
            session_id=body.session_id,
            user_id=user["id"],
        )
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=f"查询失败: {exc}") from exc
