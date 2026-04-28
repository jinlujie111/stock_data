"""用途：依赖注入：DB、当前用户、VIP 校验。"""
from typing import Annotated, Optional

from fastapi import Depends, Header
from sqlalchemy.orm import Session

from app.database import get_db
from app.core.security import verify_token
from app.core.exceptions import Unauthorized, Forbidden
from app.models.orm import User


get_db_session = get_db


def get_current_user(
    authorization: Annotated[Optional[str], Header()] = None,
    db: Session = Depends(get_db),
) -> User | None:
    if not authorization or not authorization.lower().startswith("bearer "):
        return None
    token = authorization.split(" ", 1)[1].strip()
    payload = verify_token(token)
    if not payload or "sub" not in payload:
        return None
    uid = int(payload["sub"])
    return db.get(User, uid)


def require_user(user: User | None = Depends(get_current_user)) -> User:
    if user is None:
        raise Unauthorized()
    if user.status != 1:
        raise Forbidden("账号已禁用")
    return user


def require_vip(user: User = Depends(require_user)) -> User:
    from datetime import datetime

    if user.is_vip == 1 and user.vip_expire_at and user.vip_expire_at > datetime.utcnow():
        return user
    raise Forbidden("需要 VIP")
