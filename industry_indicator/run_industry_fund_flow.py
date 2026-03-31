#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
行业资金流：执行入口（转发到 industry_fund_flow_etl.py）。

用法与 industry_fund_flow_etl.py 完全一致，额外支持：
  python run_industry_fund_flow.py --doc       打印 industry_fund_flow_参数说明.txt
  python run_industry_fund_flow.py --examples  打印下方「常用示例」（不执行抓取）

---------------------------------------------------------------------------
【场景一 · 每日更新】（推荐任务计划每个交易日跑一次）
  抓取同花顺「即时 / 3日 / 5日 / 10日 / 20日」当前快照，入库 trade_date 为当天。

  python run_industry_fund_flow.py
  python run_industry_fund_flow.py --trade-date 2026-03-26

---------------------------------------------------------------------------
【场景二 · 某一时间段批量】（东财历史日 K，period_type=东财日K）
  可先同步 Tushare 交易日历到 trade_cal，再按区间回填；日期请改为实际起止。

  python run_industry_fund_flow.py --sync-trade-cal --from-date 2026-01-01 --to-date 2026-01-31

---------------------------------------------------------------------------
【可选 · 仅同步交易日历】（不写行业资金流；AkShare 新浪日历 → trade_cal；MySQL 见 config.py）

  python run_industry_fund_flow.py --sync-trade-cal-only --from-date 2026-01-01 --to-date 2026-12-31

---------------------------------------------------------------------------
【可选 · 单日 + 先写当日日历】

  python run_industry_fund_flow.py --sync-trade-cal --trade-date 2026-03-26

---------------------------------------------------------------------------
备注：
  - MySQL：统一编辑 industry_indicator/config.py（或环境变量覆盖）；trade_cal 同步不依赖 Tushare
  - 完整参数见同目录 industry_fund_flow_参数说明.txt 或 industry_fund_flow_etl.py --help
  - Windows 批处理示例见 run_industry_fund_flow.bat
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
_ETL = _ROOT / "industry_fund_flow_etl.py"
_DOC = _ROOT / "industry_fund_flow_参数说明.txt"

_EXAMPLES_TEXT = """
========================================================================
行业资金流 — 常用示例（run_industry_fund_flow.py）
========================================================================

【场景一 · 每日更新】任务计划建议每个交易日收盘后执行
  python run_industry_fund_flow.py
  python run_industry_fund_flow.py --trade-date 2026-03-26

【场景二 · 某一时间段】先同步日历(可选) + 东财历史日K 区间回填
  python run_industry_fund_flow.py --sync-trade-cal --from-date 2026-01-01 --to-date 2026-01-31

【可选 · 仅同步 trade_cal】AkShare 日历；MySQL：industry_indicator/config.py
  python run_industry_fund_flow.py --sync-trade-cal-only --from-date 2026-01-01 --to-date 2026-12-31

【可选 · 单日且先同步当日日历】
  python run_industry_fund_flow.py --sync-trade-cal --trade-date 2026-03-26

------------------------------------------------------------------------
说明全文: python run_industry_fund_flow.py --doc
批处理模板: 同目录 run_industry_fund_flow.bat
========================================================================
""".strip()


def main() -> int:
    argv = sys.argv[1:]
    if argv and argv[0] in ("--doc", "--参数说明"):
        if _DOC.is_file():
            print(_DOC.read_text(encoding="utf-8"))
        else:
            print("未找到说明文件:", _DOC, file=sys.stderr)
            return 1
        return 0

    if argv and argv[0] in ("--examples", "--demo", "--示例"):
        print(_EXAMPLES_TEXT)
        return 0

    if not _ETL.is_file():
        print("未找到脚本:", _ETL, file=sys.stderr)
        return 1

    cmd = [sys.executable, str(_ETL), *argv]
    return subprocess.call(cmd)


if __name__ == "__main__":
    raise SystemExit(main())
