"""板块择时信号 QA：孤儿买点、覆盖率、与日线对齐。"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
from sqlalchemy import text

_ROOT = Path(__file__).resolve().parents[2]
for _p in (_ROOT, _ROOT / "dw-utils"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from etl.board_timing.db_util import (  # noqa: E402
    TimingConfig,
    get_engine_stock,
    parse_trade_date,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

HOT = "dwm_board_timing_signal_di"
ARCH = "dwm_board_timing_signal_arch"
DAILY = "ods_dc_daily_di"


def _signal_union_sql(start: date, end: date) -> tuple[str, dict[str, Any]]:
    params = {"start": start, "end": end}
    sql = f"""
        SELECT trade_date, industry_code, signal_type, position_state, close
        FROM {HOT}
        WHERE trade_date BETWEEN :start AND :end
        UNION ALL
        SELECT a.trade_date, a.industry_code, a.signal_type, a.position_state, a.close
        FROM {ARCH} a
        WHERE a.trade_date BETWEEN :start AND :end
          AND NOT EXISTS (
            SELECT 1 FROM {HOT} h
            WHERE h.trade_date = a.trade_date AND h.industry_code = a.industry_code
          )
    """
    return sql, params


def run_qa(end: date, *, lookback_days: int = 120) -> dict:
    engine = get_engine_stock()
    start = end - timedelta(days=int(lookback_days * 1.6))
    sql, params = _signal_union_sql(start, end)
    with engine.connect() as conn:
        sig = pd.read_sql(text(sql), conn, params=params)
        daily_cnt = conn.execute(
            text(
                f"""
                SELECT COUNT(DISTINCT trade_date) AS n
                FROM {DAILY}
                WHERE trade_date BETWEEN :start AND :end
                """
            ),
            params,
        ).scalar()
        sig_days = conn.execute(
            text(
                f"""
                SELECT COUNT(DISTINCT trade_date) AS n
                FROM {HOT}
                WHERE trade_date BETWEEN :start AND :end
                """
            ),
            params,
        ).scalar()

    if sig.empty:
        report = {
            "start": str(start),
            "end": str(end),
            "rows": 0,
            "orphan_buys": 0,
            "buy_count": 0,
            "sell_count": 0,
            "coverage_days_signal": int(sig_days or 0),
            "coverage_days_daily": int(daily_cnt or 0),
            "ok": False,
            "issues": ["区间内无信号行"],
        }
        logger.warning("QA %s", report)
        return report

    sig["trade_date"] = pd.to_datetime(sig["trade_date"]).dt.date
    sig["industry_code"] = (
        sig["industry_code"].astype(str).str.replace(r"\.DC$", "", regex=True)
    )
    buys = int((sig["signal_type"] == "buy").sum())
    sells = int((sig["signal_type"] == "sell").sum())

    orphan = 0
    for code, g in sig.groupby("industry_code"):
        g = g.sort_values("trade_date")
        long = False
        for _, r in g.iterrows():
            st = r["signal_type"]
            if st == "buy":
                long = True
            elif st == "sell":
                long = False
        # 末状态仍 long 不算 orphan；orphan = 有 buy 后始终无 sell，且最后不是窗口内合理持仓
        # 简化：统计「buy 次数 - sell 次数」若 buy 明显多于 sell 且末笔非 buy 持仓说明异常
        nb = int((g["signal_type"] == "buy").sum())
        ns = int((g["signal_type"] == "sell").sum())
        if nb > ns + 1:
            orphan += nb - ns - 1

    # 日线对齐：信号日在 ods 是否有 close
    codes = sorted(sig["industry_code"].unique())
    missing_ohlc = 0
    with engine.connect() as conn:
        for i in range(0, len(codes), 200):
            chunk = codes[i : i + 200]
            ph = ", ".join(f":c{j}" for j in range(len(chunk)))
            p = {**params, **{f"c{j}": c for j, c in enumerate(chunk)}, **{f"d{j}": f"{c}.DC" for j, c in enumerate(chunk)}}
            # 简化：只查带 .DC
            rows = conn.execute(
                text(
                    f"""
                    SELECT REPLACE(ts_code, '.DC', '') AS code, COUNT(*) AS n
                    FROM {DAILY}
                    WHERE trade_date BETWEEN :start AND :end
                      AND (ts_code IN ({ph}) OR ts_code IN ({', '.join(f':d{j}' for j in range(len(chunk)))}))
                    GROUP BY REPLACE(ts_code, '.DC', '')
                    """
                ),
                p,
            ).mappings().all()
            have = {r["code"] for r in rows}
            missing_ohlc += sum(1 for c in chunk if c not in have)

    issues: list[str] = []
    if orphan:
        issues.append(f"疑似多余买入未配对 {orphan} 次")
    if int(sig_days or 0) < int(daily_cnt or 0) * 0.8:
        issues.append("信号交易日覆盖明显低于日线交易日")
    if missing_ohlc:
        issues.append(f"{missing_ohlc} 个板块信号区间缺少日线")

    report = {
        "start": str(start),
        "end": str(end),
        "rows": int(len(sig)),
        "buy_count": buys,
        "sell_count": sells,
        "orphan_buys": orphan,
        "boards": int(sig["industry_code"].nunique()),
        "coverage_days_signal": int(sig_days or 0),
        "coverage_days_daily": int(daily_cnt or 0),
        "boards_missing_ohlc": missing_ohlc,
        "ok": len(issues) == 0,
        "issues": issues,
    }
    logger.info("QA %s", report)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="板块择时信号 QA")
    parser.add_argument("trade_date", help="结束日 YYYYMMDD")
    parser.add_argument("--lookback-days", type=int, default=120)
    args = parser.parse_args(argv)
    end = parse_trade_date(args.trade_date)
    rep = run_qa(end, lookback_days=args.lookback_days)
    return 0 if rep.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
