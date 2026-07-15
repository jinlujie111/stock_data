#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
【已停用 2026-07-15】cyq_chips 区间补数。

ods_cyq_chips_di 现网未用且占盘极大，同步任务已 status=0。
勿再执行本脚本；若确需恢复，先在 data_config.db_sync_task 重新启用 cyq_chips。
"""
from __future__ import annotations

import sys


def main() -> int:
    print(
        "cyq_chips 补数已停用（2026-07-15）。"
        "请勿运行；恢复需启用 db_sync_task.source_table=cyq_chips。",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
