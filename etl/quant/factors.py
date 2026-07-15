"""因子层：加载行情面板并计算截面打分所需的原始因子。

技术因子（滚动，全区间一次算好）：mom20/mom60/mom120、ma20/ma60 及是否站上、
量价形态分 vp_score、突破 breakout、近 5/20 日主力净流入、换手率。
基本面因子（point-in-time as-of，按需按日取）：roe、净利同比 growth、pe_inv、pb_inv、总市值。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date

import numpy as np
import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine

from etl.quant.db_util import iso

logger = logging.getLogger(__name__)

# 技术因子列（面板计算产出）
TECH_FACTORS = (
    "mom20",
    "mom60",
    "mom120",
    "above_ma20",
    "above_ma60",
    "vp_score",
    "breakout",
    "netflow5",
    "netflow20",
    "turnover",
)
# 基本面因子列（as-of 产出）
FUNDAMENTAL_FACTORS = ("roe", "growth", "pe_inv", "pb_inv")


@dataclass
class StockMeta:
    name: str
    list_date: date | None
    is_st: bool


@dataclass
class PricePanel:
    """按交易日切片的行情+技术因子面板。"""

    df: pd.DataFrame  # 列: trade_date, ts_code, close, adj_close, amount, up_limit_hit, <TECH_FACTORS>
    by_date: dict[date, pd.DataFrame] = field(default_factory=dict)

    def slice(self, d: date) -> pd.DataFrame:
        return self.by_date.get(d, self.df.iloc[0:0])


def load_stock_meta(engine: Engine) -> dict[str, StockMeta]:
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT ts_code, name, list_date, list_status
                FROM ods_stock_basic_di
                """
            )
        ).mappings().all()
    out: dict[str, StockMeta] = {}
    for r in rows:
        name = r.get("name") or ""
        ld = r.get("list_date")
        ld_date: date | None = None
        if ld:
            try:
                if isinstance(ld, date):
                    ld_date = ld
                else:
                    s = str(ld).replace("-", "")[:8]
                    ld_date = date(int(s[:4]), int(s[4:6]), int(s[6:8]))
            except Exception:
                ld_date = None
        is_st = (
            "ST" in name.upper()
            or name.endswith("退")
            or "退市" in name
        )
        out[r["ts_code"]] = StockMeta(name=name, list_date=ld_date, is_st=is_st)
    return out


def load_price_panel(engine: Engine, start: date, end: date) -> PricePanel:
    """加载 [start, end] 全市场行情并计算技术因子。

    start 应已包含 mom120/ma60 所需的前置回溯交易日。
    """
    price_sql = """
        SELECT d.trade_date, d.ts_code, d.close, d.amount, d.pct_chg,
               a.adj_factor,
               b.turnover_rate,
               l.up_limit
        FROM ods_stock_detail_di d
        LEFT JOIN ods_adj_factor_di a
          ON a.trade_date = d.trade_date AND a.ts_code = d.ts_code
        LEFT JOIN ods_daily_basic_di b
          ON b.trade_date = d.trade_date AND b.ts_code = d.ts_code
        LEFT JOIN ods_stk_limit_di l
          ON l.trade_date = d.trade_date AND l.ts_code = d.ts_code
        WHERE d.trade_date BETWEEN :s AND :e
          AND d.close IS NOT NULL AND d.close > 0
    """
    with engine.connect() as conn:
        df = pd.read_sql(text(price_sql), conn, params={"s": iso(start), "e": iso(end)})
    if df.empty:
        raise RuntimeError(f"ods_stock_detail_di 无数据: {start} ~ {end}")

    flow_sql = """
        SELECT trade_date, ts_code, net_mf_amount
        FROM ods_stock_fund_flow_di
        WHERE trade_date BETWEEN :s AND :e
    """
    with engine.connect() as conn:
        flow = pd.read_sql(text(flow_sql), conn, params={"s": iso(start), "e": iso(end)})

    vp_sql = """
        SELECT trade_date, ts_code, vp_pattern_score, is_breakout_strict
        FROM dwm_stock_vp_factor_di
        WHERE trade_date BETWEEN :s AND :e
    """
    with engine.connect() as conn:
        vp = pd.read_sql(text(vp_sql), conn, params={"s": iso(start), "e": iso(end)})

    df["trade_date"] = pd.to_datetime(df["trade_date"])
    df = df.sort_values(["ts_code", "trade_date"])
    df["adj_factor"] = pd.to_numeric(df["adj_factor"], errors="coerce").fillna(1.0)
    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    df["adj_close"] = df["close"] * df["adj_factor"]
    df["amount"] = pd.to_numeric(df["amount"], errors="coerce")
    df["turnover_rate"] = pd.to_numeric(df["turnover_rate"], errors="coerce")
    df["up_limit"] = pd.to_numeric(df["up_limit"], errors="coerce")
    # 涨停：收盘触及涨停价（无涨停价则判为否）
    df["up_limit_hit"] = (
        df["up_limit"].notna() & (df["close"] >= df["up_limit"] - 1e-6)
    ).astype(int)

    if not flow.empty:
        flow["trade_date"] = pd.to_datetime(flow["trade_date"])
        flow["net_mf_amount"] = pd.to_numeric(flow["net_mf_amount"], errors="coerce")
        df = df.merge(flow, on=["trade_date", "ts_code"], how="left")
    else:
        df["net_mf_amount"] = np.nan

    if not vp.empty:
        vp["trade_date"] = pd.to_datetime(vp["trade_date"])
        vp["vp_pattern_score"] = pd.to_numeric(vp["vp_pattern_score"], errors="coerce")
        vp["is_breakout_strict"] = pd.to_numeric(vp["is_breakout_strict"], errors="coerce")
        df = df.merge(vp, on=["trade_date", "ts_code"], how="left")
    else:
        df["vp_pattern_score"] = np.nan
        df["is_breakout_strict"] = np.nan

    parts: list[pd.DataFrame] = []
    for _, grp in df.groupby("ts_code", sort=False):
        g = grp.sort_values("trade_date").copy()
        ac = g["adj_close"]
        g["mom20"] = ac / ac.shift(20) - 1.0
        g["mom60"] = ac / ac.shift(60) - 1.0
        g["mom120"] = ac / ac.shift(120) - 1.0
        ma20 = ac.rolling(20, min_periods=20).mean()
        ma60 = ac.rolling(60, min_periods=60).mean()
        g["above_ma20"] = (ac > ma20).astype(float)
        g["above_ma60"] = (ac > ma60).astype(float)
        g.loc[ma20.isna(), "above_ma20"] = np.nan
        g.loc[ma60.isna(), "above_ma60"] = np.nan
        g["netflow5"] = g["net_mf_amount"].rolling(5, min_periods=1).sum()
        g["netflow20"] = g["net_mf_amount"].rolling(20, min_periods=1).sum()
        parts.append(g)

    all_df = pd.concat(parts, ignore_index=True)
    all_df["vp_score"] = all_df["vp_pattern_score"]
    all_df["breakout"] = all_df["is_breakout_strict"]
    all_df["turnover"] = all_df["turnover_rate"]

    keep = [
        "trade_date",
        "ts_code",
        "close",
        "adj_close",
        "amount",
        "up_limit_hit",
        *TECH_FACTORS,
    ]
    all_df = all_df[keep]
    by_date: dict[date, pd.DataFrame] = {}
    for td, g in all_df.groupby("trade_date"):
        by_date[td.date()] = g.reset_index(drop=True)
    logger.info(
        "price_panel loaded rows=%d dates=%d %s~%s",
        len(all_df),
        len(by_date),
        start,
        end,
    )
    return PricePanel(df=all_df, by_date=by_date)


def load_fundamental_asof(engine: Engine, as_of: date) -> pd.DataFrame:
    """as_of 当日的 point-in-time 基本面因子（每股一行）。

    - pe/pb/total_mv 取 as_of 当日 ods_daily_basic_di
    - roe/净利同比 取 ann_date <= as_of 的最新一期 ods_fina_indicator
    """
    basic_sql = """
        SELECT ts_code, pe, pb, total_mv
        FROM ods_daily_basic_di
        WHERE trade_date = :d
    """
    with engine.connect() as conn:
        basic = pd.read_sql(text(basic_sql), conn, params={"d": iso(as_of)})

    fina_sql = """
        SELECT ts_code, roe, netprofit_yoy
        FROM (
            SELECT f.ts_code, f.roe, f.netprofit_yoy,
                   ROW_NUMBER() OVER (
                       PARTITION BY f.ts_code
                       ORDER BY f.end_date DESC, f.ann_date DESC
                   ) AS rn
            FROM ods_fina_indicator f
            WHERE f.ann_date <= :d
        ) t
        WHERE t.rn = 1
    """
    with engine.connect() as conn:
        fina = pd.read_sql(text(fina_sql), conn, params={"d": iso(as_of)})

    if basic.empty:
        basic = pd.DataFrame(columns=["ts_code", "pe", "pb", "total_mv"])
    df = basic.merge(fina, on="ts_code", how="outer")
    for col in ("pe", "pb", "total_mv", "roe", "netprofit_yoy"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    # 估值取倒数（越低估值 → 分越高）；负/零 PE、PB 视为无效
    df["pe_inv"] = np.where(df["pe"] > 0, 1.0 / df["pe"], np.nan)
    df["pb_inv"] = np.where(df["pb"] > 0, 1.0 / df["pb"], np.nan)
    df["growth"] = df["netprofit_yoy"]
    return df[["ts_code", "roe", "growth", "pe_inv", "pb_inv", "total_mv"]]
