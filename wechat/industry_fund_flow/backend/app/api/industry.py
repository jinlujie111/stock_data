"""用途：行业详情。"""
from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.orm import Session

from app.core.responses import ok
from app.database import get_db
from app.config import get_settings
from app.services import industry_query

router = APIRouter(prefix="/industry", tags=["industry"])


@router.get("/{name}/detail")
def industry_detail(
    name: str,
    trade_date: date | None = Query(None),
    db: Session = Depends(get_db),
):
    td = trade_date or industry_query.latest_trade_date(db)
    if not td:
        return ok({})
    hist = industry_query.industry_history(db, name, td, days=20)
    score = None
    leaders = []
    try:
        score = db.execute(
            text(
                "SELECT * FROM industry_score_di WHERE trade_date=:d AND industry_name=:n LIMIT 1"
            ),
            {"d": td, "n": name},
        ).mappings().first()
        leaders = db.execute(
            text(
                "SELECT stock_code, stock_name, change_pct, main_net_inflow, role_type "
                "FROM stock_pool_di WHERE trade_date=:d AND industry_name=:n LIMIT 20"
            ),
            {"d": td, "n": name},
        ).mappings().all()
    except (ProgrammingError, OperationalError) as exc:
        if not industry_query._is_no_such_table(exc):
            raise
    if not leaders:
        # MVP：从资金流当日行取领涨股占位
        row = db.execute(
            text(
                "SELECT top_stock_name FROM industry_fund_flow_di "
                "WHERE trade_date=:d AND period_type=:p AND industry_name=:n LIMIT 1"
            ),
            {"d": td, "n": name, "p": get_settings().period_instant},
        ).fetchone()
        leaders = []
        if row and row[0]:
            leaders = [{"stock_name": row[0], "stock_code": "", "role_type": "leader"}]

    return ok(
        {
            "trade_date": str(td),
            "industry_name": name,
            "fund_trend_20d": hist,
            "score": dict(score) if score else None,
            "leaders": [dict(x) for x in leaders],
        }
    )
