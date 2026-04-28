"""用途：首页仪表盘 API。"""
from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.responses import ok
from app.database import get_db
from app.services import industry_query
from app.cache import get_json, set_json

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("")
def dashboard(
    trade_date: date | None = Query(None),
    db: Session = Depends(get_db),
):
    td = trade_date or industry_query.latest_trade_date(db)
    if not td:
        return ok({"trade_date": None, "message": "尚无资金流数据"})
    cache_key = f"dash:{td}"
    cached = get_json(cache_key)
    if cached:
        return ok(cached)

    items = industry_query.fund_flow_day(db, td)
    top10 = items[:10]
    mkt = industry_query.market_daily(db, td)
    data = {
        "trade_date": str(td),
        "mainline_top10": top10,
        "rank_full_hint": "详见榜单页；免费用户仅展示前3（客户端限制）",
        "market": mkt,
        "risk_note": (mkt or {}).get("risk_note") if mkt else "注意仓位与节奏，勿追高杀跌",
    }
    set_json(cache_key, data, 120)
    return ok(data)
