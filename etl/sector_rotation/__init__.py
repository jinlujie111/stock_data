"""申万行业板块轮动：截面动量打分 + 周频等权轮动回测。

数据优先读本地 cache（CSV）；若配置了 MySQL 且表存在，可切到 ODS。
MVP 默认：SW2021 一级行业，mom20+mom60，每周调仓 Top5。
"""
from __future__ import annotations

__all__ = ["__version__"]
__version__ = "0.1.0"
