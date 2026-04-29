"""用途：手动执行行业评分并写入 industry_score_di（与 scheduler 内 compute_and_persist 一致）。

用法（在 backend 目录下）::
    python scripts/run_score.py
    python scripts/run_score.py 2026-04-25

依赖：`.env` 或环境变量中的 MySQL 配置；当日 industry_fund_flow_di 须有数据。
"""
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.database import SessionLocal  # noqa: E402
from app.services import industry_query  # noqa: E402
from app.services.score_engine import compute_and_persist  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="对指定交易日跑分并写入 industry_score_di")
    parser.add_argument(
        "trade_date",
        nargs="?",
        help="交易日 YYYY-MM-DD；省略则使用库内 industry_fund_flow_di 最新交易日",
    )
    args = parser.parse_args()

    db = SessionLocal()
    try:
        if args.trade_date:
            td = date.fromisoformat(args.trade_date.strip())
        else:
            td = industry_query.latest_trade_date(db)
            if not td:
                print("ERROR: industry_fund_flow_di 无数据，无法确定交易日", file=sys.stderr)
                sys.exit(1)

        n = compute_and_persist(db, td)
        print(f"OK trade_date={td} inserted_rows={n}")
        sys.exit(0 if n > 0 else 2)
    finally:
        db.close()


if __name__ == "__main__":
    main()
