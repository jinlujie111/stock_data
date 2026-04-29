#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
ths_industry_di 历史回填（按交易日、全行业）。

背景：ths_industry_etl.run() 使用的 stock_board_industry_summary_ths 等为「当前截面」，
不能把任意 trade_date 当成历史某日快照。回填需使用带 start/end 的接口。

数据源：ak.stock_board_industry_index_ths(symbol=行业名称, start_date, end_date)
  — 同花顺行业指数日 K。入库前换算为与增量 ths_industry_etl（主源 stock_board_industry_summary_ths）
  及 industry_fund_flow_etl 消费 ths_industry_di 时一致：
  · amount：指数 K「成交额」一般为元 → ÷10000 存「万元」（与 _build_ths_industry_turnover_yi_map 假定一致）
  · volume：指数 K「成交量」一般为手 → ÷10000 存万手（见 ths_industry_etl 增量默认亦用指数 K 覆盖，与一览表总成交量非同一口径）
  涨跌幅：收盘价日环比(%)。raw_json 保留接口原始手/元便于核对。

用法（在项目根目录 stock_data）：
  python history_data/ths_industry_history_backfill.py --start-date 2020-01-01 --end-date 2025-12-31

可选：--max-industries 5 试跑；--sleep 0.2 降频。

依赖：akshare、pymysql；MySQL 连接见 industry_indicator/config.py。
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import date, datetime
from pathlib import Path
from typing import Any

import akshare as ak
import pandas as pd
import pymysql

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from industry_indicator.ths_industry_etl import (  # noqa: E402
    THSIndustryETL,
    _normalize_industry_code_cell,
)
from industry_indicator.ths_index_line_fetch import (  # noqa: E402
    fetch_stock_board_industry_index_ths,
)

LOG = logging.getLogger(__name__)

TABLE_NAME = "ths_industry_di"


def _load_mysql_cfg():
    from industry_indicator import config as cfg  # noqa: PLC0415

    return (
        cfg.MYSQL_HOST,
        cfg.MYSQL_PORT,
        cfg.MYSQL_USER,
        cfg.MYSQL_PASSWORD,
        cfg.MYSQL_DATABASE,
    )


def _ymd_compact(d: date) -> str:
    return d.strftime("%Y%m%d")


def _parse_date(s: str) -> date:
    return datetime.strptime(s.strip(), "%Y-%m-%d").date()


def _volume_hand_to_wanshou(vol_hand: float | None) -> float | None:
    """指数日 K 成交量（手）→ 万手，对齐一览表总成交量口径。"""
    if vol_hand is None or (isinstance(vol_hand, float) and pd.isna(vol_hand)):
        return None
    return round(float(vol_hand) / 10000.0, 4)


def _amount_yuan_to_wan(yuan: float | None) -> float | None:
    """指数日 K 成交额（元）→ 万元，对齐 industry_fund_flow_etl 对 amount 的使用。"""
    if yuan is None or (isinstance(yuan, float) and pd.isna(yuan)):
        return None
    return round(float(yuan) / 10000.0, 4)


def _hist_to_records(
    symbol_name: str,
    industry_code: str,
    hist: pd.DataFrame,
    now_str: str,
) -> list[tuple[Any, ...]]:
    """单日行情 DataFrame -> 与 ths_industry_di 对齐的记录（ tuples for upsert）。"""
    if hist is None or hist.empty:
        return []
    df = hist.copy()
    if "收盘价" not in df.columns:
        LOG.warning("指数行情缺少「收盘价」列: %s", symbol_name)
        return []

    df["收盘价"] = pd.to_numeric(df["收盘价"], errors="coerce")
    df["_pct"] = df["收盘价"].pct_change() * 100.0

    vol_col = "成交量" if "成交量" in df.columns else None
    amt_col = "成交额" if "成交额" in df.columns else None
    date_col = "日期" if "日期" in df.columns else None
    if not date_col:
        LOG.warning("指数行情缺少「日期」列: %s", symbol_name)
        return []

    out: list[tuple[Any, ...]] = []
    for _, row in df.iterrows():
        rd = row[date_col]
        if pd.isna(rd):
            continue
        if isinstance(rd, datetime):
            td = rd.date()
        elif isinstance(rd, date):
            td = rd
        else:
            ts = pd.to_datetime(rd, errors="coerce")
            if pd.isna(ts):
                continue
            td = ts.date()

        vol_raw = pd.to_numeric(row.get(vol_col), errors="coerce") if vol_col else None
        amt_raw = pd.to_numeric(row.get(amt_col), errors="coerce") if amt_col else None
        vh = float(vol_raw) if vol_raw is not None and not pd.isna(vol_raw) else None
        ay = float(amt_raw) if amt_raw is not None and not pd.isna(amt_raw) else None
        vol_db = _volume_hand_to_wanshou(vh)
        amt_db = _amount_yuan_to_wan(ay)
        chg = row.get("_pct")
        if pd.isna(chg):
            chg_f = None
        else:
            chg_f = float(round(float(chg), 4))

        raw = {
            "source_api": "stock_board_industry_index_ths",
            "symbol": symbol_name,
            "industry_code": industry_code,
            "volume_hand_raw": vh,
            "amount_yuan_raw": ay,
            "volume_stored_wanshou": vol_db,
            "amount_stored_wanyuan": amt_db,
            "row": {
                k: (None if (isinstance(v, float) and pd.isna(v)) else v)
                for k, v in row.items()
                if k != "_pct"
            },
        }
        out.append(
            (
                td,
                industry_code,
                str(symbol_name).strip(),
                vol_db,
                amt_db,
                chg_f,
                json.dumps(raw, ensure_ascii=False, default=str),
                now_str,
                now_str,
            )
        )
    return out


def _upsert_batch(
    conn: pymysql.connections.Connection,
    rows: list[tuple[Any, ...]],
) -> int:
    if not rows:
        return 0
    sql = f"""
    INSERT INTO `{TABLE_NAME}` (
        trade_date, industry_code, industry_name,
        volume, amount, change_pct,
        raw_json, created_at, updated_at
    ) VALUES (
        %s, %s, %s, %s, %s, %s, CAST(%s AS JSON), %s, %s
    )
    ON DUPLICATE KEY UPDATE
        industry_name = VALUES(industry_name),
        volume = VALUES(volume),
        amount = VALUES(amount),
        change_pct = VALUES(change_pct),
        raw_json = VALUES(raw_json),
        updated_at = VALUES(updated_at);
    """
    with conn.cursor() as cur:
        cur.executemany(sql, rows)
    conn.commit()
    return len(rows)


def backfill(
    start: date,
    end: date,
    *,
    sleep_seconds: float = 0.15,
    max_industries: int | None = None,
    batch_flush: int = 800,
) -> int:
    """按行业拉指数日 K 并写入 ths_industry_di，返回写入行数（含更新）。"""
    start_s, end_s = _ymd_compact(start), _ymd_compact(end)
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    ref = ak.stock_board_industry_name_ths()
    if ref is None or ref.empty or not {"name", "code"}.issubset(ref.columns):
        LOG.error("无法获取 stock_board_industry_name_ths（需要 name、code 列）")
        return 0

    ref = ref[["name", "code"]].copy()
    ref["name"] = ref["name"].astype(str).str.strip()
    ref["code"] = ref["code"].map(_normalize_industry_code_cell)
    if max_industries is not None:
        ref = ref.head(max_industries)

    etl = THSIndustryETL()
    etl.create_table()

    host, port, user, password, database = _load_mysql_cfg()
    conn = pymysql.connect(
        host=host,
        port=port,
        user=user,
        password=password,
        database=database,
        charset="utf8mb4",
        autocommit=False,
    )
    total = 0
    buf: list[tuple[Any, ...]] = []
    try:
        for i, (_, r) in enumerate(ref.iterrows(), start=1):
            name = str(r["name"]).strip()
            c = r.get("code")
            code = str(c).strip() if c is not None and not (isinstance(c, float) and pd.isna(c)) else ""
            if not name:
                continue
            icode = code if code else name[:32]
            try:
                hist = fetch_stock_board_industry_index_ths(
                    symbol=name,
                    start_date=start_s,
                    end_date=end_s,
                )
            except Exception as exc:  # noqa: BLE001
                LOG.warning("拉取行业指数 K 线失败 %s: %s", name, exc)
                hist = None
            if hist is None or hist.empty:
                time.sleep(sleep_seconds)
                continue

            if isinstance(hist.index, pd.DatetimeIndex):
                hist = hist.reset_index()
            if "日期" in hist.columns:
                hist["_d"] = pd.to_datetime(hist["日期"], errors="coerce")
                hist = hist[(hist["_d"].dt.date >= start) & (hist["_d"].dt.date <= end)]
                hist = hist.drop(columns=["_d"], errors="ignore")
            recs = _hist_to_records(name, icode, hist, now_str)
            buf.extend(recs)
            while len(buf) >= batch_flush:
                total += _upsert_batch(conn, buf[:batch_flush])
                buf = buf[batch_flush:]
            LOG.info("行业进度 %s/%s %s 行=%s", i, len(ref), name, len(hist))
            time.sleep(sleep_seconds)

        if buf:
            total += _upsert_batch(conn, buf)
    finally:
        conn.close()

    LOG.info("回填结束，累计写入/更新约 %s 行", total)
    return total


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    p = argparse.ArgumentParser(description="ths_industry_di 历史回填（同花顺行业指数日 K）")
    p.add_argument("--start-date", required=True, help="YYYY-MM-DD")
    p.add_argument("--end-date", required=True, help="YYYY-MM-DD")
    p.add_argument("--sleep", type=float, default=0.15, help="每行业请求间隔秒")
    p.add_argument("--max-industries", type=int, default=None, help="仅调试用，限制行业数量")
    p.add_argument("--batch", type=int, default=800, help="每批 UPSERT 条数")
    args = p.parse_args()

    start, end = _parse_date(args.start_date), _parse_date(args.end_date)
    if start > end:
        raise SystemExit("start-date 不能晚于 end-date")

    n = backfill(
        start,
        end,
        sleep_seconds=args.sleep,
        max_industries=args.max_industries,
        batch_flush=max(100, args.batch),
    )
    raise SystemExit(0 if n >= 0 else 1)


if __name__ == "__main__":
    main()

##使用方法：python3.11 ths_industry_history_backfill.py --start-date 2026-04-01 --end-date 2026-04-02