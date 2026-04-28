"""用途：微信登录（MVP 支持 dev_code 直接发 token；生产接 jscode2session）。"""
import httpx
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.responses import ok, err
from app.core.security import create_access_token
from app.config import get_settings
from app.database import get_db

router = APIRouter(prefix="/auth", tags=["auth"])


class WechatLoginBody(BaseModel):
    code: str
    nickname: str | None = None
    avatar_url: str | None = None


@router.post("/wechat/login")
def wechat_login(body: WechatLoginBody, db: Session = Depends(get_db)):
    s = get_settings()
    openid: str | None = None
    sk: str | None = None

    if body.code.startswith("dev_"):
        openid = body.code
    elif s.wechat_appid and s.wechat_secret:
        url = (
            f"https://api.weixin.qq.com/sns/jscode2session"
            f"?appid={s.wechat_appid}&secret={s.wechat_secret}&js_code={body.code}&grant_type=authorization_code"
        )
        r = httpx.get(url, timeout=10.0)
        data = r.json()
        openid = data.get("openid")
        sk = data.get("session_key")
        if not openid:
            return err(40001, "微信登录失败", data)
    else:
        return err(40002, "未配置 WECHAT_APPID/SECRET，请使用 dev_ 前缀 mock 登录")

    row = db.execute(text("SELECT id FROM users WHERE openid=:o"), {"o": openid}).fetchone()
    if row:
        uid = int(row[0])
        db.execute(
            text(
                "UPDATE users SET last_login_at=NOW(), nickname=COALESCE(:n,nickname), "
                "avatar_url=COALESCE(:a,avatar_url), session_key=COALESCE(:s,session_key) WHERE id=:id"
            ),
            {"n": body.nickname, "a": body.avatar_url, "s": sk, "id": uid},
        )
        db.commit()
    else:
        db.execute(
            text(
                "INSERT INTO users(openid, session_key, nickname, avatar_url, last_login_at) "
                "VALUES(:o,:sk,:n,:a,NOW())"
            ),
            {"o": openid, "sk": sk, "n": body.nickname, "a": body.avatar_url},
        )
        db.commit()
        uid = int(
            db.execute(text("SELECT id FROM users WHERE openid=:o"), {"o": openid}).scalar()
        )

    token = create_access_token(str(uid), extra={"openid": openid})
    return ok({"token": token, "user_id": uid})
