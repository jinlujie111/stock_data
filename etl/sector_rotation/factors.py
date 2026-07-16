"""申万一级行业面板：行情 + 资金流因子。"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine

from etl.sector_rotation.sw_dc_map import DC_NAME_TO_SW_L1

logger = logging.getLogger(__name__)

SW2021_L1: dict[str, str] = {
    "801010.SI": "农林牧渔",
    "801030.SI": "基础化工",
    "801040.SI": "钢铁",
    "801050.SI": "有色金属",
    "801080.SI": "电子",
    "801110.SI": "家用电器",
    "801120.SI": "食品饮料",
    "801130.SI": "纺织服饰",
    "801140.SI": "轻工制造",
    "801150.SI": "医药生物",
    "801160.SI": "公用事业",
    "801170.SI": "交通运输",
    "801180.SI": "房地产",
    "801200.SI": "商贸零售",
    "801210.SI": "社会服务",
    "801230.SI": "综合",
    "801710.SI": "建筑材料",
    "801720.SI": "建筑装饰",
    "801730.SI": "电力设备",
    "801740.SI": "国防军工",
    "801750.SI": "计算机",
    "801760.SI": "传媒",
    "801770.SI": "通信",
    "801780.SI": "银行",
    "801790.SI": "非银金融",
    "801880.SI": "汽车",
    "801890.SI": "机械设备",
    "801950.SI": "煤炭",
    "801960.SI": "石油石化",
    "801970.SI": "环保",
    "801980.SI": "美容护理",
}

CACHE_DIR = Path(__file__).resolve().parent / "cache"
NAME_TO_CODE = {v: k for k, v in SW2021_L1.items()}


def _as_date(v) -> date:
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    s = str(v).strip().replace("-", "")[:8]
    return datetime.strptime(s, "%Y%m%d").date()


@dataclass
class SectorPanel:
    close: pd.DataFrame
    names: dict[str, str]
    amount: pd.DataFrame | None = None
    # 申万代码宽表：当日主力净流入（由东财细分行业聚合）
    net_flow: pd.DataFrame | None = None

    def trading_days(self, start: date, end: date) -> list[date]:
        idx = [_as_date(d) for d in self.close.index]
        return [d for d in idx if start <= d <= end]

    def close_on(self, d: date) -> pd.Series:
        if d in self.close.index:
            return self.close.loc[d]
        key = pd.Timestamp(d)
        if key in self.close.index:
            return self.close.loc[key]
        raise KeyError(d)


def merge_mcp_dumps(dump_dir: Path, out_csv: Path | None = None) -> pd.DataFrame:
    """合并 agent-tools 中的 sw_daily / index_daily JSON。"""
    rows: list[dict] = []
    for path in sorted(dump_dir.glob("*.txt")):
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        data = raw.get("data") if isinstance(raw, dict) else None
        if not data or "fields" not in data or "items" not in data:
            continue
        fields = list(data["fields"])
        if "trade_date" not in fields or "close" not in fields:
            continue
        # 跳过资金流（另存）
        if "net_amount" in fields and "content_type" in fields:
            continue
        if "net_amount" in fields and "industry" in fields:
            continue
        code_key = "symbol" if "symbol" in fields else ("ts_code" if "ts_code" in fields else None)
        if not code_key:
            continue
        for item in data["items"]:
            rec = dict(zip(fields, item))
            code = str(rec.get(code_key) or "")
            if not (code.endswith(".SI") or code == "000300.SH"):
                continue
            rows.append(
                {
                    "ts_code": code,
                    "trade_date": _as_date(rec["trade_date"]),
                    "name": rec.get("name") or SW2021_L1.get(code, code),
                    "open": rec.get("open"),
                    "high": rec.get("high"),
                    "low": rec.get("low"),
                    "close": float(rec["close"]),
                    "pct_change": rec.get("pct_change") or rec.get("pct_chg"),
                    "vol": rec.get("vol"),
                    "amount": rec.get("amount"),
                }
            )
    if not rows:
        raise RuntimeError(f"未在 {dump_dir} 找到可用的 sw_daily/index_daily JSON")
    df = pd.DataFrame(rows)
    df = df.drop_duplicates(subset=["ts_code", "trade_date"], keep="last")
    df = df.sort_values(["ts_code", "trade_date"]).reset_index(drop=True)
    if out_csv is not None:
        out_csv.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(out_csv, index=False, encoding="utf-8-sig")
        logger.info("写入 cache %s rows=%d codes=%d", out_csv, len(df), df["ts_code"].nunique())
    return df


def merge_mcp_fund_flow(dump_dir: Path, out_csv: Path | None = None) -> pd.DataFrame:
    """合并 moneyflow_ind_dc，按 DC→申万 L1 映射聚合金流入。"""
    rows: list[dict] = []
    for path in sorted(dump_dir.glob("*.txt")):
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        data = raw.get("data") if isinstance(raw, dict) else None
        if not data or "fields" not in data or "items" not in data:
            continue
        fields = list(data["fields"])
        if "net_amount" not in fields or "trade_date" not in fields:
            continue
        name_key = "name" if "name" in fields else ("industry" if "industry" in fields else None)
        if not name_key:
            continue
        for item in data["items"]:
            rec = dict(zip(fields, item))
            if rec.get("content_type") not in (None, "行业", "行业板块"):
                # THS 无 content_type；DC 需行业
                if "content_type" in fields and rec.get("content_type") != "行业":
                    continue
            nm = str(rec.get(name_key) or "")
            sw = DC_NAME_TO_SW_L1.get(nm)
            if not sw:
                continue
            code = NAME_TO_CODE.get(sw)
            if not code:
                continue
            net = rec.get("net_amount")
            if net is None:
                continue
            rows.append(
                {
                    "ts_code": code,
                    "name": sw,
                    "trade_date": _as_date(rec["trade_date"]),
                    "net_amount": float(net),
                    "dc_name": nm,
                }
            )
    if not rows:
        raise RuntimeError(f"未在 {dump_dir} 找到可映射的资金流 JSON")
    raw_df = pd.DataFrame(rows)
    agg = (
        raw_df.groupby(["ts_code", "name", "trade_date"], as_index=False)["net_amount"]
        .sum()
        .sort_values(["ts_code", "trade_date"])
        .reset_index(drop=True)
    )
    if out_csv is not None:
        out_csv.parent.mkdir(parents=True, exist_ok=True)
        agg.to_csv(out_csv, index=False, encoding="utf-8-sig")
        logger.info(
            "写入资金流 cache %s rows=%d codes=%d",
            out_csv,
            len(agg),
            agg["ts_code"].nunique(),
        )
    return agg


def load_panel_from_csv(
    csv_path: Path,
    flow_csv: Path | None = None,
    codes: list[str] | None = None,
) -> SectorPanel:
    df = pd.read_csv(csv_path)
    df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.date
    if codes is None:
        codes = [c for c in SW2021_L1 if c in set(df["ts_code"])]
    sub = df[df["ts_code"].isin(codes)].copy()
    close = sub.pivot(index="trade_date", columns="ts_code", values="close").sort_index()
    amount = None
    if "amount" in sub.columns:
        amount = sub.pivot(index="trade_date", columns="ts_code", values="amount").sort_index()
    names = {
        str(c): str(
            sub.loc[sub["ts_code"] == c, "name"].dropna().iloc[0]
            if (sub["ts_code"] == c).any()
            else SW2021_L1.get(c, c)
        )
        for c in close.columns
    }
    net_flow = None
    if flow_csv is not None and flow_csv.exists():
        net_flow = _load_flow_wide(flow_csv, list(close.columns)).reindex(close.index)
    return SectorPanel(close=close, names=names, amount=amount, net_flow=net_flow)


def _load_flow_wide(flow_csv: Path, codes: list[str]) -> pd.DataFrame:
    fdf = pd.read_csv(flow_csv)
    fdf["trade_date"] = pd.to_datetime(fdf["trade_date"]).dt.date
    fdf = fdf[fdf["ts_code"].isin(codes)]
    return fdf.pivot(index="trade_date", columns="ts_code", values="net_amount").sort_index()


def load_benchmark_from_csv(csv_path: Path, code: str = "000300.SH") -> dict[date, float]:
    df = pd.read_csv(csv_path)
    df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.date
    sub = df[df["ts_code"] == code]
    return {r.trade_date: float(r.close) for r in sub.itertuples() if pd.notna(r.close)}


def load_panel_from_mysql(
    engine: Engine,
    start: date,
    end: date,
    *,
    lookback_days: int = 130,
) -> SectorPanel:
    """从 ods_industry_daily_di + ods_industry_fund_flow_di 加载（生产路径）。"""
    pad_start = pd.Timestamp(start) - pd.Timedelta(days=lookback_days * 2)
    sql = """
        SELECT ts_code, trade_date, name, close, amount
        FROM ods_industry_daily_di
        WHERE trade_date BETWEEN :s AND :e
          AND ts_code IN :codes
        ORDER BY trade_date, ts_code
    """
    codes = list(SW2021_L1.keys())
    with engine.connect() as conn:
        rows = conn.execute(
            text(sql.replace("IN :codes", f"IN ({','.join(repr(c) for c in codes)})")),
            {"s": pad_start.date().isoformat(), "e": end.isoformat()},
        ).mappings().all()
    if not rows:
        raise RuntimeError("ods_industry_daily_di 无申万一级行情，请先恢复 sw_daily 同步并回填")
    df = pd.DataFrame([dict(r) for r in rows])
    df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.date
    close = df.pivot(index="trade_date", columns="ts_code", values="close").sort_index()
    amount = df.pivot(index="trade_date", columns="ts_code", values="amount").sort_index()
    names = {c: SW2021_L1.get(c, c) for c in close.columns}
    for _, r in df.dropna(subset=["name"]).iterrows():
        names[str(r["ts_code"])] = str(r["name"])

    net_flow = _load_flow_from_mysql(engine, pad_start.date(), end, list(close.columns))
    return SectorPanel(close=close, names=names, amount=amount, net_flow=net_flow)


def _load_flow_from_mysql(
    engine: Engine, start: date, end: date, codes: list[str]
) -> pd.DataFrame | None:
    """从东财行业资金流表按名称映射聚合到申万代码。"""
    sql = """
        SELECT trade_date, name, net_amount
        FROM ods_industry_fund_flow_di
        WHERE trade_date BETWEEN :s AND :e
          AND content_type = '行业'
    """
    try:
        with engine.connect() as conn:
            rows = conn.execute(
                text(sql), {"s": start.isoformat(), "e": end.isoformat()}
            ).mappings().all()
    except Exception as exc:
        logger.warning("读取 ods_industry_fund_flow_di 失败: %s", exc)
        return None
    if not rows:
        return None
    mapped = []
    for r in rows:
        sw = DC_NAME_TO_SW_L1.get(str(r["name"] or ""))
        if not sw:
            continue
        code = NAME_TO_CODE.get(sw)
        if not code or code not in codes:
            continue
        if r["net_amount"] is None:
            continue
        mapped.append(
            {
                "trade_date": _as_date(r["trade_date"]),
                "ts_code": code,
                "net_amount": float(r["net_amount"]),
            }
        )
    if not mapped:
        return None
    fdf = pd.DataFrame(mapped)
    return (
        fdf.groupby(["trade_date", "ts_code"], as_index=False)["net_amount"]
        .sum()
        .pivot(index="trade_date", columns="ts_code", values="net_amount")
        .sort_index()
    )


def load_benchmark_from_mysql(
    engine: Engine, start: date, end: date, code: str = "000300.SH"
) -> dict[date, float]:
    sql = """
        SELECT trade_date, close FROM ods_index_daily_di
        WHERE ts_code = :c AND trade_date BETWEEN :s AND :e
        ORDER BY trade_date
    """
    try:
        with engine.connect() as conn:
            rows = conn.execute(
                text(sql),
                {"c": code, "s": start.isoformat(), "e": end.isoformat()},
            ).fetchall()
    except Exception as exc:
        logger.warning("基准读取失败: %s", exc)
        return {}
    out: dict[date, float] = {}
    for r in rows:
        if r[1] is not None:
            out[_as_date(r[0])] = float(r[1])
    return out


def compute_momentum(close: pd.DataFrame, windows: list[int]) -> dict[int, pd.DataFrame]:
    out: dict[int, pd.DataFrame] = {}
    for w in windows:
        out[w] = close / close.shift(w) - 1.0
    return out


def compute_flow_sum(net_flow: pd.DataFrame | None, windows: list[int]) -> dict[int, pd.DataFrame]:
    if net_flow is None or net_flow.empty:
        return {}
    out: dict[int, pd.DataFrame] = {}
    for w in windows:
        out[w] = net_flow.rolling(w, min_periods=max(1, w // 2)).sum()
    return out


def compute_amt_ratio(amount: pd.DataFrame | None, window: int = 20) -> pd.DataFrame | None:
    """成交额相对均量：amount / MA(window) - 1，衡量活跃度。"""
    if amount is None or amount.empty:
        return None
    ma = amount.rolling(window, min_periods=max(5, window // 2)).mean()
    return amount / ma - 1.0


def cross_section_rank(factor: pd.Series, ascending: bool = False) -> pd.Series:
    valid = factor.dropna()
    if valid.empty:
        return factor * np.nan
    ranks = valid.rank(ascending=ascending, method="average", pct=True)
    return ranks.reindex(factor.index)
