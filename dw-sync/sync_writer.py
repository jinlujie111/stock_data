#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""目标表写入逻辑（按 sync_mode）。"""
from __future__ import annotations

from datetime import date

import pandas as pd
from sqlalchemy import text

from mysql_config import get_target_engine


def write_dataframe(
    *,
    database: str,
    table: str,
    df: pd.DataFrame,
    sync_mode: str,
    trade_date: date | None = None,
    snapshot_delete_column: str | None = None,
) -> int:
    """按 sync_mode 写入目标表，返回写入行数。"""
    if df.empty:
        return 0

    engine = get_target_engine(database)
    mode = (sync_mode or "snapshot").lower()

    with engine.begin() as conn:
        if mode == "full":
            conn.execute(text(f"TRUNCATE TABLE `{table}`"))
        elif mode in ("snapshot", "incremental") and trade_date is not None:
            delete_col = snapshot_delete_column or "trade_date"
            if delete_col in df.columns:
                conn.execute(
                    text(f"DELETE FROM `{table}` WHERE `{delete_col}` = :td"),
                    {"td": trade_date},
                )

    df.to_sql(
        table,
        engine,
        if_exists="append",
        index=False,
        method="multi",
        chunksize=500,
    )
    return len(df)
