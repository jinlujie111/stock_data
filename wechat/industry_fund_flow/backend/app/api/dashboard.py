"""用途：首页仪表盘 API。"""
from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.responses import ok
from app.database import get_db
from app.services import industry_query
from app.cache import get_json, set_json

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


def _industry_up_down_counts(rows: list[dict]) -> tuple[int, int]:
    """按行业涨跌幅统计上涨行业数、下跌行业数（平盘不计入两者）。"""
    up = down = 0
    for x in rows:
        try:
            v = float(x.get("industry_change_pct") or 0)
        except (TypeError, ValueError):
            v = 0.0
        if v > 0:
            up += 1
        elif v < 0:
            down += 1
    return up, down


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
    up_all, down_all = _industry_up_down_counts(items)
    mkt = industry_query.market_daily(db, td)
    data = {
        "trade_date": str(td),
        "mainline_top10": top10,
        "industry_summary": {
            "up_count": up_all,
            "down_count": down_all,
            "note": "统计口径：当日 instant 口径下每一行业一行，按 industry_change_pct 正负计数",
        },
        "rank_full_hint": "详见榜单页",
        "market": mkt,
        "risk_note": (mkt or {}).get("risk_note") if mkt else "注意仓位与节奏，勿追高杀跌",
    }
    set_json(cache_key, data, 120)
    return ok(data)
