"""用途：当前用户信息（登录可选，无会员/VIP 字段）。"""
from fastapi import APIRouter, Depends

from app.core.responses import ok
from app.deps import get_current_user
from app.models.orm import User

router = APIRouter(prefix="/user", tags=["user"])


@router.get("/me")
def me(user: User | None = Depends(get_current_user)):
    if user is None:
        return ok({"logged_in": False})
    return ok(
        {
            "logged_in": True,
            "id": user.id,
            "nickname": user.nickname,
            "avatar_url": user.avatar_url,
        }
    )
