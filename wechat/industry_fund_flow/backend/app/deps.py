"""用途：依赖注入：DB、可选当前用户。"""
from typing import Annotated, Optional

from fastapi import Depends, Header
from sqlalchemy.orm import Session

from app.database import get_db
from app.core.security import verify_token
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
