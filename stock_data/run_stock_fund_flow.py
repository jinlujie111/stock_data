#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
个股资金流向：入口，转发到 stock_fund_flow_etl.py。

  python run_stock_fund_flow.py
  python run_stock_fund_flow.py --trade-date 2026-04-03
  python run_stock_fund_flow.py --max-rows 50   # 调试

MySQL：上级目录 industry_indicator/config.py（表名 STOCK_FUND_FLOW_TABLE，默认 stock_fund_flow_di）
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
_ETL = _ROOT / "stock_fund_flow_etl.py"


def main() -> int:
    if not _ETL.is_file():
        print("未找到脚本:", _ETL, file=sys.stderr)
        return 1
    return subprocess.call([sys.executable, str(_ETL), *sys.argv[1:]])


if __name__ == "__main__":
    raise SystemExit(main())
