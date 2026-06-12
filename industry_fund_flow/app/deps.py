from __future__ import annotations

from typing import Annotated

from fastapi import Cookie, Depends, HTTPException

from app import auth_service
from app.config import COOKIE_NAME


def current_user(
    iff_token: Annotated[str | None, Cookie(alias=COOKIE_NAME)] = None,
) -> dict | None:
    if not iff_token:
        return None
    payload = auth_service.decode_token(iff_token)
    if not payload:
        return None
    return auth_service.get_user_by_id(int(payload["sub"]))


def require_user(user: dict | None = Depends(current_user)) -> dict:
    if not user:
        raise HTTPException(status_code=401, detail="未登录")
    return user
