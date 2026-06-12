from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

import bcrypt
from jose import JWTError, jwt

from app.config import JWT_ALGORITHM, JWT_EXPIRE_HOURS, JWT_SECRET
from app.db import execute, fetch_one

_USERNAME_RE = re.compile(r"^[a-zA-Z0-9_]{3,32}$")


class AuthError(Exception):
    def __init__(self, message: str, code: str = "auth_error"):
        self.message = message
        self.code = code
        super().__init__(message)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


def create_access_token(user_id: int, username: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRE_HOURS)
    payload = {"sub": str(user_id), "username": username, "exp": expire}
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except JWTError:
        return None


def get_user_by_username(username: str) -> dict | None:
    return fetch_one(
        """
        SELECT id, username, email, password_hash, status
        FROM app_user
        WHERE username = :username
        LIMIT 1
        """,
        {"username": username},
    )


def get_user_by_id(user_id: int) -> dict | None:
    return fetch_one(
        """
        SELECT id, username, email, status, created_at
        FROM app_user
        WHERE id = :id
        LIMIT 1
        """,
        {"id": user_id},
    )


def register_user(username: str, password: str, email: str | None) -> dict:
    username = username.strip()
    if not _USERNAME_RE.match(username):
        raise AuthError("用户名须为 3–32 位字母、数字或下划线", "invalid_username")
    if len(password) < 8:
        raise AuthError("密码至少 8 位", "weak_password")
    if get_user_by_username(username):
        raise AuthError("用户名已存在", "username_taken")
    if email:
        email = email.strip()
        if fetch_one("SELECT id FROM app_user WHERE email = :email LIMIT 1", {"email": email}):
            raise AuthError("邮箱已被注册", "email_taken")

    execute(
        """
        INSERT INTO app_user (username, email, password_hash)
        VALUES (:username, :email, :password_hash)
        """,
        {
            "username": username,
            "email": email or None,
            "password_hash": hash_password(password),
        },
    )
    user = get_user_by_username(username)
    if not user:
        raise AuthError("注册失败，请重试", "register_failed")
    return user


def login_user(username: str, password: str) -> dict:
    user = get_user_by_username(username.strip())
    if not user or not verify_password(password, user["password_hash"]):
        raise AuthError("用户名或密码错误", "invalid_credentials")
    if int(user.get("status") or 0) != 1:
        raise AuthError("账号已禁用", "account_disabled")
    return user
