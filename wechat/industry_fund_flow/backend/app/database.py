"""用途：SQLAlchemy 引擎与会话。"""
from urllib.parse import quote_plus

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

from app.config import get_settings


class Base(DeclarativeBase):
    pass


def _mysql_url() -> str:
    s = get_settings()
    user = quote_plus(s.mysql_user)
    pwd = quote_plus(s.mysql_password or "")
    return (
        f"mysql+pymysql://{user}:{pwd}@{s.mysql_host}:{s.mysql_port}/"
        f"{s.mysql_database}?charset=utf8mb4"
    )


engine = create_engine(_mysql_url(), pool_pre_ping=True, pool_size=10, max_overflow=20)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
