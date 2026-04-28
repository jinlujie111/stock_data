"""用途：评分引擎 — 40%今日排名 30%五日累计 20%成交额放大 10%涨幅强度；结果写入 industry_score_di。"""
from __future__ import annotations

import json
from datetime import date, timedelta
from typing import Any

import numpy as np
import pandas as pd
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.services import industry_query


def _pct_rank(series: pd.Series) -> pd.Series:
    if series.empty:
        return series
    return series.rank(pct=True, method="average") * 100


def compute_and_persist(db: Session, trade_date: date) -> int:
    """根据 industry_fund_flow_di 计算 industry_score_di；返回写入行数。"""
    s = get_settings()
    end = trade_date
    start5 = end - timedelta(days=14)  # 多取几天跨过周末

    rows = industry_query.fund_flow_range(db, start5, end)
    if not rows:
        return 0

    df = pd.DataFrame(rows)
    df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.date
    last_df = df[df["trade_date"] == end].copy()
    if last_df.empty:
        return 0

    # 今日净流入排名分：按 main_net_inflow 降序百分位
    last_df = last_df.copy()
    last_df["main_net_inflow"] = pd.to_numeric(last_df["main_net_inflow"], errors="coerce").fillna(0)
    last_df["score_rank_today"] = _pct_rank(last_df["main_net_inflow"])

    # 5日累计（仅交易日有数据则自然合并）
    g5 = (
        df.groupby("industry_name", as_index=False)["main_net_inflow"]
        .sum()
        .rename(columns={"main_net_inflow": "sum5"})
    )
    # 简化为：窗口内所有出现天的 sum；生产可改为严格滚动5交易日
    mask = df["trade_date"] >= (end - timedelta(days=7))
    df5 = df.loc[mask]
    g5 = (
        df5.groupby("industry_name", as_index=False)["main_net_inflow"]
        .sum()
        .rename(columns={"main_net_inflow": "sum5"})
    )
    g5["score_sum5"] = _pct_rank(pd.to_numeric(g5["sum5"], errors="coerce").fillna(0))

    merged = last_df.merge(g5[["industry_name", "sum5", "score_sum5"]], on="industry_name", how="left")
    merged["sum5"] = pd.to_numeric(merged["sum5"], errors="coerce").fillna(0)
    merged["score_sum5"] = pd.to_numeric(merged["score_sum5"], errors="coerce").fillna(0)

    # 成交额放大：今日 turnover vs 近5日均值
    def turnover_amp(nm: str) -> float:
        sub = df[(df["industry_name"] == nm) & (df["trade_date"] >= (end - timedelta(days=7)))]
        t = pd.to_numeric(sub["industry_turnover"], errors="coerce")
        if len(t) < 2 or t.iloc[-1] is None:
            return 0.0
        today_v = float(t.iloc[-1]) if not np.isnan(t.iloc[-1]) else 0.0
        ma = float(t.mean()) if len(t) else 0.0
        if ma <= 0:
            return 0.0
        return today_v / ma

    merged["turnover_amp"] = merged["industry_name"].map(turnover_amp)
    merged["score_turnover_amp"] = _pct_rank(merged["turnover_amp"])

    merged["industry_change_pct"] = pd.to_numeric(merged["industry_change_pct"], errors="coerce").fillna(0)
    merged["score_chg_strength"] = _pct_rank(merged["industry_change_pct"])

    w1, w2, w3, w4 = 0.4, 0.3, 0.2, 0.1
    merged["total_score"] = (
        w1 * merged["score_rank_today"]
        + w2 * merged["score_sum5"]
        + w3 * merged["score_turnover_amp"]
        + w4 * merged["score_chg_strength"]
    )

    merged = merged.sort_values("total_score", ascending=False).reset_index(drop=True)
    merged["latent_rank"] = np.arange(1, len(merged) + 1)

    def risk_row(chg: float, inflow: float) -> str:
        if chg < -2 and inflow < 0:
            return "high"
        if chg < 0 or inflow < 0:
            return "medium"
        return "low"

    merged["risk_level"] = [
        risk_row(c, f)
        for c, f in zip(merged["industry_change_pct"], merged["main_net_inflow"])
    ]

    # 覆盖写入当日
    db.execute(text("DELETE FROM industry_score_di WHERE trade_date = :d"), {"d": end})
    db.commit()

    inserted = 0
    for _, r in merged.iterrows():
        detail = {
            "sum5": float(r.get("sum5", 0)),
            "turnover_amp": float(r.get("turnover_amp", 0)),
            "weights": {"rank_today": w1, "sum5": w2, "turnover_amp": w3, "chg": w4},
        }
        icode = r.get("industry_code")
        if icode is None or (isinstance(icode, float) and pd.isna(icode)):
            icode = None
        elif icode is not None:
            icode = str(icode).strip() or None

        db.execute(
            text(
                """
                INSERT INTO industry_score_di(
                  trade_date, industry_name, industry_code,
                  score_rank_today, score_sum5, score_turnover_amp, score_chg_strength,
                  total_score, latent_rank, risk_level, detail_json
                ) VALUES (
                  :trade_date, :industry_name, :industry_code,
                  :sr, :s5, :st, :sc,
                  :ts, :lr, :risk, :dj
                )
                """
            ),
            {
                "trade_date": end,
                "industry_name": str(r["industry_name"]),
                "industry_code": icode,
                "sr": float(r["score_rank_today"]),
                "s5": float(r["score_sum5"]),
                "st": float(r["score_turnover_amp"]),
                "sc": float(r["score_chg_strength"]),
                "ts": float(r["total_score"]),
                "lr": int(r["latent_rank"]),
                "risk": r["risk_level"],
                "dj": json.dumps(detail, ensure_ascii=False),
            },
        )
        inserted += 1
    db.commit()
    return inserted
