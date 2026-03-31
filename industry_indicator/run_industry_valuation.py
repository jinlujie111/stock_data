#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""行业估值：转发执行 industry_valuation_etl.py（参数一致）。"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
_ETL = _ROOT / "industry_valuation_etl.py"


def main() -> int:
    if not _ETL.is_file():
        print("未找到脚本:", _ETL, file=sys.stderr)
        return 1
    cmd = [sys.executable, str(_ETL), *sys.argv[1:]]
    return subprocess.call(cmd)


if __name__ == "__main__":
    raise SystemExit(main())
