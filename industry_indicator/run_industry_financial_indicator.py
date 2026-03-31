#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""行业财务衍生指标：转发执行 industry_financial_indicator_etl.py。"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
_ETL = _ROOT / "industry_financial_indicator_etl.py"


def main() -> int:
    if not _ETL.is_file():
        print("未找到脚本:", _ETL, file=sys.stderr)
        return 1
    return subprocess.call([sys.executable, str(_ETL), *sys.argv[1:]])


if __name__ == "__main__":
    raise SystemExit(main())
