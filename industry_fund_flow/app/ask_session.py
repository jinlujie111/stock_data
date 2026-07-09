"""问数多轮会话（内存，最近 3 轮）。"""
from __future__ import annotations

import time
import uuid
from threading import Lock
from typing import Any

_MAX_TURNS = 3
_TTL_SEC = 3600
_lock = Lock()
_store: dict[str, dict[str, Any]] = {}


def _purge_expired() -> None:
    now = time.time()
    expired = [sid for sid, s in _store.items() if now - s.get("updated", 0) > _TTL_SEC]
    for sid in expired:
        _store.pop(sid, None)


def ensure_session(session_id: str | None, user_id: int) -> str:
    with _lock:
        _purge_expired()
        if session_id and session_id in _store:
            sess = _store[session_id]
            if sess.get("user_id") == user_id:
                sess["updated"] = time.time()
                return session_id
        sid = uuid.uuid4().hex
        _store[sid] = {"user_id": user_id, "turns": [], "updated": time.time()}
        return sid


def get_last_turn(session_id: str | None, user_id: int) -> dict[str, Any] | None:
    if not session_id:
        return None
    with _lock:
        sess = _store.get(session_id)
        if not sess or sess.get("user_id") != user_id:
            return None
        turns = sess.get("turns") or []
        return dict(turns[-1]) if turns else None


def append_turn(session_id: str, user_id: int, turn: dict[str, Any]) -> None:
    with _lock:
        sess = _store.get(session_id)
        if not sess or sess.get("user_id") != user_id:
            return
        turns: list[dict[str, Any]] = list(sess.get("turns") or [])
        turns.append(turn)
        sess["turns"] = turns[-_MAX_TURNS:]
        sess["updated"] = time.time()
