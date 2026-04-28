"""用途：APScheduler 每个交易日 15:10 跑批：市场快照、行业评分、日志。"""
import logging
from datetime import date, datetime

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.services import industry_query
from app.services.score_engine import compute_and_persist
from app.services.market_snapshot_job import refresh_market_daily
from app.services.log_service import log_db

LOG = logging.getLogger("scheduler")
sched: BackgroundScheduler | None = None


def job_daily_pipeline():
    """收盘后：取最近交易日数据，生成 market_daily + industry_score。"""
    db: Session = SessionLocal()
    try:
        td = industry_query.latest_trade_date(db)
        if not td:
            log_db(db, "WARN", "job", "无 industry_fund_flow_di 数据，跳过", None)
            return
        refresh_market_daily(db, td)
        n = compute_and_persist(db, td)
        log_db(
            db,
            "INFO",
            "job",
            f"日终完成 trade_date={td} scores={n}",
            {"trade_date": str(td)},
        )
        # 推送订阅消息：需配置模板ID，此处仅记录
        log_db(db, "INFO", "push", "订阅消息待对接 wechat template", {"trade_date": str(td)})
    except Exception as exc:  # noqa: BLE001
        LOG.exception("job failed: %s", exc)
        try:
            log_db(db, "ERROR", "job", str(exc)[:1000], None)
        except Exception:
            pass
    finally:
        db.close()


def setup_scheduler():
    global sched
    if sched is not None:
        return
    sched = BackgroundScheduler(timezone="Asia/Shanghai")
    # 每个交易日 15:10（周末也会触发但库无新数据时任务很轻；生产可接交易日历）
    sched.add_job(job_daily_pipeline, "cron", hour=15, minute=10, id="daily_pipeline")
    sched.start()


def shutdown_scheduler():
    global sched
    if sched:
        sched.shutdown(wait=False)
        sched = None
