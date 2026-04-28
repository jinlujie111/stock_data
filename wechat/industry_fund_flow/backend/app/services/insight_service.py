"""用途：连续吸筹、出货预警等派生分析。"""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
from sqlalchemy.orm import Session

from app.services import industry_query


def consecutive_positive_days(db: Session, end: date, min_days: int = 3) -> list[dict]:
    """统计连续 min_days 日主力净流入>0 的行业，按最近一日净流入强度排序。"""
    start = end - timedelta(days=30)
    rows = industry_query.fund_flow_range(db, start, end)
    if not rows:
        return []
    df = pd.DataFrame(rows)
    df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.date
    df["main_net_inflow"] = pd.to_numeric(df["main_net_inflow"], errors="coerce").fillna(0)
    dates = sorted(df["trade_date"].unique())
    if end not in dates:
        return []

    def streak_for(name: str) -> int:
        dlist = sorted(df[df["industry_name"] == name]["trade_date"].unique(), reverse=True)
        streak = 0
        for d in dlist:
            v = float(
                df[(df["industry_name"] == name) & (df["trade_date"] == d)]["main_net_inflow"].sum()
            )
            if v > 0:
                streak += 1
            else:
                break
        return streak

    last = df[df["trade_date"] == end].copy()
    out: list[dict] = []
    for _, r in last.iterrows():
        nm = str(r["industry_name"])
        st = streak_for(nm)
        if st >= min_days:
            out.append(
                {
                    "industry_name": nm,
                    "streak_days": st,
                    "main_net_inflow": float(r["main_net_inflow"]),
                    "industry_change_pct": float(r.get("industry_change_pct") or 0),
                }
            )
    out.sort(key=lambda x: (x["streak_days"], x["main_net_inflow"]), reverse=True)
    return out


def exit_warning(db: Session, end: date) -> list[dict]:
    """
    出货预警：近3日连续净流出 + 当日涨跌幅<0 + 成交额高于近5日均（放量出货代理）。
    """
    start = end - timedelta(days=10)
    rows = industry_query.fund_flow_range(db, start, end)
    if not rows:
        return []
    df = pd.DataFrame(rows)
    df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.date
    df["main_net_inflow"] = pd.to_numeric(df["main_net_inflow"], errors="coerce").fillna(0)
    df["industry_change_pct"] = pd.to_numeric(df["industry_change_pct"], errors="coerce").fillna(0)
    df["industry_turnover"] = pd.to_numeric(df["industry_turnover"], errors="coerce")
    last = df[df["trade_date"] == end]
    out: list[dict] = []
    for _, r in last.iterrows():
        nm = str(r["industry_name"])
        sub = df[df["industry_name"] == nm].sort_values("trade_date")
        if len(sub) < 3:
            continue
        tail = sub.tail(3)
        if (tail["main_net_inflow"] < 0).all() and float(r["industry_change_pct"]) < 0:
            t = sub["industry_turnover"]
            ma5 = t.tail(5).mean() if len(t) >= 5 else t.mean()
            today_t = float(r.get("industry_turnover") or 0)
            vol_high = ma5 and today_t >= ma5 * 1.1
            if vol_high:
                out.append(
                    {
                        "industry_name": nm,
                        "main_net_inflow": float(r["main_net_inflow"]),
                        "industry_change_pct": float(r["industry_change_pct"]),
                        "reason": "连续净流出+下跌+放量",
                    }
                )
    out.sort(key=lambda x: x["main_net_inflow"])
    return out
