"""用途：从行业表聚合生成 market_daily_di 粗略快照（MVP）；后续可接行情总貌接口覆盖。"""
from datetime import date

import pandas as pd
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services import industry_query


def refresh_market_daily(db: Session, trade_date: date) -> None:
    rows = industry_query.fund_flow_day(db, trade_date)
    if not rows:
        return
    df = pd.DataFrame(rows)
    up = int((pd.to_numeric(df["industry_change_pct"], errors="coerce").fillna(0) > 0).sum())
    down = int((pd.to_numeric(df["industry_change_pct"], errors="coerce").fillna(0) < 0).sum())
    tt = pd.to_numeric(df["industry_turnover"], errors="coerce").sum()
    risk = "热点分化，注意高位板块获利了结" if down > up else "赚钱效应回升，关注主线持续性"

    db.execute(
        text("DELETE FROM market_daily_di WHERE trade_date = :d"),
        {"d": trade_date},
    )
    db.execute(
        text(
            """
            INSERT INTO market_daily_di(
              trade_date, total_turnover_yi, up_count, down_count, risk_note, raw_json
            ) VALUES (
              :d, :tt, :u, :dn, :r, :j
            )
            """
        ),
        {
            "d": trade_date,
            "tt": float(tt) if tt == tt else None,
            "u": up,
            "dn": down,
            "r": risk,
            "j": {"source": "derived_from_industry_fund_flow_di"},
        },
    )
    db.commit()
