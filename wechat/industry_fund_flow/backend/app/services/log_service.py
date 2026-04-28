"""用途：写入 system_logs。"""
import json

from sqlalchemy import text
from sqlalchemy.orm import Session


def log_db(db: Session, level: str, module: str, message: str, context: dict | None = None):
    raw = json.dumps(context, ensure_ascii=False) if context is not None else "null"
    db.execute(
        text(
            "INSERT INTO system_logs(level, module, message, context_json) "
            "VALUES (:level, :module, :message, :ctx)"
        ),
        {"level": level, "module": module, "message": message[:1024], "ctx": raw},
    )
    db.commit()
