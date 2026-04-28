"""用途：我的 / 会员信息。"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.responses import ok
from app.database import get_db
from app.deps import require_user
from app.models.orm import User

router = APIRouter(prefix="/user", tags=["user"])


@router.get("/me")
def me(user: User = Depends(require_user)):
    return ok(
        {
            "id": user.id,
            "nickname": user.nickname,
            "avatar_url": user.avatar_url,
            "is_vip": user.is_vip,
            "vip_expire_at": user.vip_expire_at,
        }
    )
