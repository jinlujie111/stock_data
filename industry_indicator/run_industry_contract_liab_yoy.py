#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""行业合同负债同比增速：转发 industry_contract_liab_yoy_etl.py。"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_ETL = Path(__file__).resolve().parent / "industry_contract_liab_yoy_etl.py"


def main() -> int:
    if not _ETL.is_file():
        print("未找到:", _ETL, file=sys.stderr)
        return 1
    return subprocess.call([sys.executable, str(_ETL), *sys.argv[1:]])


if __name__ == "__main__":
    raise SystemExit(main())
