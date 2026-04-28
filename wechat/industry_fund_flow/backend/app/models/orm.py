"""用途：ORM 实体，与 sql/schema.sql 对齐（核心表）。"""
from datetime import date, datetime
from sqlalchemy import Date, DateTime, Integer, String, Text, Numeric, JSON, BigInteger, SmallInteger, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    openid: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    unionid: Mapped[str | None] = mapped_column(String(64))
    session_key: Mapped[str | None] = mapped_column(String(128))
    nickname: Mapped[str | None] = mapped_column(String(64))
    avatar_url: Mapped[str | None] = mapped_column(String(512))
    phone: Mapped[str | None] = mapped_column(String(20))
    is_vip: Mapped[int] = mapped_column(SmallInteger, default=0)
    vip_expire_at: Mapped[datetime | None] = mapped_column(DateTime)
    status: Mapped[int] = mapped_column(SmallInteger, default=1)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class MarketDaily(Base):
    __tablename__ = "market_daily_di"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    trade_date: Mapped[date] = mapped_column(Date, nullable=False, unique=True)
    total_turnover_yi: Mapped[float | None] = mapped_column(Numeric(20, 4))
    sh_up: Mapped[int | None] = mapped_column(Integer)
    sh_down: Mapped[int | None] = mapped_column(Integer)
    sz_up: Mapped[int | None] = mapped_column(Integer)
    sz_down: Mapped[int | None] = mapped_column(Integer)
    up_count: Mapped[int | None] = mapped_column(Integer)
    down_count: Mapped[int | None] = mapped_column(Integer)
    risk_note: Mapped[str | None] = mapped_column(String(512))
    raw_json: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class IndustryScore(Base):
    __tablename__ = "industry_score_di"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    trade_date: Mapped[date] = mapped_column(Date, nullable=False)
    industry_name: Mapped[str] = mapped_column(String(128), nullable=False)
    industry_code: Mapped[str | None] = mapped_column(String(32))
    score_rank_today: Mapped[float | None] = mapped_column(Numeric(10, 6))
    score_sum5: Mapped[float | None] = mapped_column(Numeric(10, 6))
    score_turnover_amp: Mapped[float | None] = mapped_column(Numeric(10, 6))
    score_chg_strength: Mapped[float | None] = mapped_column(Numeric(10, 6))
    total_score: Mapped[float] = mapped_column(Numeric(12, 6), nullable=False)
    latent_rank: Mapped[int | None] = mapped_column(Integer)
    risk_level: Mapped[str | None] = mapped_column(String(16))
    detail_json: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class SystemLog(Base):
    __tablename__ = "system_logs"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    level: Mapped[str] = mapped_column(String(16), default="INFO")
    module: Mapped[str | None] = mapped_column(String(64))
    message: Mapped[str] = mapped_column(String(1024), nullable=False)
    context_json: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
