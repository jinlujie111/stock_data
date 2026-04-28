"""用途：FastAPI 入口，挂载路由、中间件、定时任务。"""
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.middleware.logging_middleware import AccessLogMiddleware, register_exception_handlers
from app.api import auth, dashboard, rank, industry, user
from app.tasks.scheduler import setup_scheduler, shutdown_scheduler

logging.basicConfig(level=logging.INFO)
LOG = logging.getLogger("app")

settings = get_settings()
app = FastAPI(title=settings.app_name, debug=settings.debug)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(AccessLogMiddleware)
register_exception_handlers(app)

app.include_router(auth.router, prefix="/api/v1")
app.include_router(dashboard.router, prefix="/api/v1")
app.include_router(rank.router, prefix="/api/v1")
app.include_router(industry.router, prefix="/api/v1")
app.include_router(user.router, prefix="/api/v1")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.on_event("startup")
def on_start():
    setup_scheduler()
    LOG.info("scheduler started")


@app.on_event("shutdown")
def on_stop():
    shutdown_scheduler()
