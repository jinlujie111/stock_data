#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import annotations

import argparse
import bisect
import json
import logging
import os
import re
import sys
import time
from pathlib import Path
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Iterable

import akshare as ak
import pandas as pd
import pymysql


LOG = logging.getLogger(__name__)

DEFAULT_TABLE_NAME = "industry_fund_flow_di"


def _load_config():
    """加载同目录下 config.py（MySQL、Tushare 统一配置）。"""
    _here = Path(__file__).resolve().parent
    if str(_here) not in sys.path:
        sys.path.insert(0, str(_here))
    import config as cfg  # noqa: E402

    return cfg


def _mysql_defaults_from_config():
    """命令行未显式传参时的 MySQL / 表名 默认值，来自 config.py。"""
    try:
        cfg = _load_config()
        return (
            cfg.MYSQL_HOST,
            cfg.MYSQL_PORT,
            cfg.MYSQL_USER,
            cfg.MYSQL_PASSWORD,
            cfg.MYSQL_DATABASE,
            cfg.INDUSTRY_FLOW_TABLE,
        )
    except Exception:
        return (
            os.getenv("MYSQL_HOST", "localhost"),
            int(os.getenv("MYSQL_PORT", "3306")),
            os.getenv("MYSQL_USER", "root"),
            os.getenv("MYSQL_PASSWORD", "jinlujie"),
            os.getenv("MYSQL_DATABASE", "stock_data"),
            DEFAULT_TABLE_NAME,
        )
# 东方财富行业日 K 历史资金流（与「同花顺即时/多日排行」数据源与口径不同）
EM_HIST_PERIOD_TYPE = "东财日K"
DEFAULT_PERIODS = [
    "\u5373\u65f6",
    "3\u65e5\u6392\u884c",
    "5\u65e5\u6392\u884c",
    "10\u65e5\u6392\u884c",
    "20\u65e5\u6392\u884c",
]

PERIOD_ALIAS = {
    "now": "\u5373\u65f6",
    "real": "\u5373\u65f6",
    "3d": "3\u65e5\u6392\u884c",
    "5d": "5\u65e5\u6392\u884c",
    "10d": "10\u65e5\u6392\u884c",
    "20d": "20\u65e5\u6392\u884c",
}


def _safe_float(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip().replace(",", "")
        if text in {"", "--", "nan", "None"}:
            return None
        value = text
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _safe_int(value: object) -> int | None:
    num = _safe_float(value)
    if num is None:
        return None
    return int(num)


def _create_table_if_not_exists(conn: pymysql.connections.Connection, table_name: str) -> None:
    ddl = f"""
    CREATE TABLE IF NOT EXISTS {table_name} (
        id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '自增主键',
        trade_date DATE NOT NULL COMMENT '数据日期',
        period_type VARCHAR(32) NOT NULL COMMENT '周期类型: 即时/3日排行/5日排行/10日排行/20日排行',
        ranking_no INT NULL COMMENT '行业排名',
        industry_code VARCHAR(32) NULL COMMENT '行业代码',
        industry_name VARCHAR(128) NOT NULL COMMENT '行业名称',
        industry_index_value DECIMAL(20, 6) NULL COMMENT '行业指数值(即时口径可用)',
        industry_change_pct DECIMAL(20, 6) NULL COMMENT '行业涨跌幅(%)',
        main_net_inflow DECIMAL(20, 6) NULL COMMENT '主力净流入(亿元)',
        super_large_net_inflow DECIMAL(20, 6) NULL COMMENT '超大单净流入(亿元)',
        large_net_inflow DECIMAL(20, 6) NULL COMMENT '大单净流入(亿元)',
        company_count INT NULL COMMENT '公司家数(即时口径可用)',
        top_stock_name VARCHAR(128) NULL COMMENT '领涨股名称',
        top_stock_change_pct DECIMAL(20, 6) NULL COMMENT '领涨股涨跌幅(%)',
        current_price DECIMAL(20, 6) NULL COMMENT '当前价(即时口径可用)',
        industry_turnover DECIMAL(20, 6) NULL COMMENT '行业成交额(亿元)：东财板块日K折算；同花顺源无此列时按板块名匹配东财',
        raw_json JSON NOT NULL COMMENT '原始数据JSON',
        created_at DATETIME NOT NULL COMMENT '创建时间',
        updated_at DATETIME NOT NULL COMMENT '更新时间',
        UNIQUE KEY uniq_industry_fund_flow (trade_date, period_type, industry_name)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='行业资金流日报';
    """
    with conn.cursor() as cursor:
        cursor.execute(ddl)
    conn.commit()


def _ensure_table_columns(conn: pymysql.connections.Connection, table_name: str) -> None:
    """新表使用 industry_code；旧表若仍为 board_code 则重命名；补齐 industry_turnover。"""
    with conn.cursor() as cursor:
        cursor.execute(f"SHOW COLUMNS FROM {table_name} LIKE 'industry_code';")
        if not cursor.fetchone():
            cursor.execute(f"SHOW COLUMNS FROM {table_name} LIKE 'board_code';")
            if cursor.fetchone():
                cursor.execute(
                    f"ALTER TABLE {table_name} CHANGE COLUMN board_code industry_code "
                    "VARCHAR(32) NULL COMMENT '行业代码';"
                )
            else:
                cursor.execute(
                    f"ALTER TABLE {table_name} ADD COLUMN industry_code VARCHAR(32) NULL "
                    "COMMENT '行业代码' AFTER ranking_no;"
                )
        cursor.execute(f"SHOW COLUMNS FROM {table_name} LIKE 'industry_turnover';")
        if not cursor.fetchone():
            cursor.execute(
                f"ALTER TABLE {table_name} ADD COLUMN industry_turnover DECIMAL(20, 6) NULL "
                "COMMENT '行业成交额(亿元)：东财板块日K折算；同花顺源无此列时按板块名匹配东财' "
                "AFTER current_price;"
            )
    conn.commit()


def _normalize_row_by_position(row: pd.Series) -> dict:
    vals = list(row.values)
    # AkShare 行业资金流存在 11 列(即时) 和 8 列(多日排行) 两种结构，按位置兼容。
    if len(vals) == 8:
        return {
            "ranking_no": _safe_int(vals[0]),
            "industry_code": None,
            "industry_name": None if pd.isna(vals[1]) else str(vals[1]),
            "industry_change_pct": _safe_float(vals[2]),
            "main_net_inflow": _safe_float(vals[3]),
            "super_large_net_inflow": _safe_float(vals[4]),
            "large_net_inflow": _safe_float(vals[5]),
            "top_stock_name": None if pd.isna(vals[6]) else str(vals[6]),
            "top_stock_change_pct": _safe_float(vals[7]),
            "industry_index_value": None,
            "company_count": None,
            "current_price": None,
            "industry_turnover": None,
        }

    return {
        "ranking_no": _safe_int(vals[0]) if len(vals) > 0 else None,
        "industry_code": None,
        "industry_name": None if len(vals) <= 1 or pd.isna(vals[1]) else str(vals[1]),
        "industry_index_value": _safe_float(vals[2]) if len(vals) > 2 else None,
        "industry_change_pct": _safe_float(vals[3]) if len(vals) > 3 else None,
        "main_net_inflow": _safe_float(vals[4]) if len(vals) > 4 else None,
        "super_large_net_inflow": _safe_float(vals[5]) if len(vals) > 5 else None,
        "large_net_inflow": _safe_float(vals[6]) if len(vals) > 6 else None,
        "company_count": _safe_int(vals[7]) if len(vals) > 7 else None,
        "top_stock_name": None if len(vals) <= 8 or pd.isna(vals[8]) else str(vals[8]),
        "top_stock_change_pct": _safe_float(vals[9]) if len(vals) > 9 else None,
        "current_price": _safe_float(vals[10]) if len(vals) > 10 else None,
        "industry_turnover": None,
    }


def _normalize_period(period: str) -> str:
    key = period.strip().lower()
    return PERIOD_ALIAS.get(key, period.strip())


def _norm_name(text: str) -> str:
    # 对行业名做轻量标准化，提升名称匹配行业代码成功率。
    return re.sub(r"[\s\-_/（）()]+", "", text).lower()


def _turnover_yi_from_df_row(row: pd.Series, colnames: Iterable[str]) -> float | None:
    """若接口返回带「成交额」等列，按亿元口径解析（与同花顺流入资金等单位一致）。"""
    cols = set(colnames)
    for key in ("成交额", "行业成交额", "成交額", "成交金额"):
        if key in cols:
            return _safe_float(row.get(key))
    return None


def _build_em_industry_turnover_yi_map(trade_date: str) -> dict[str, float]:
    """东财行业板块日 K 当日成交额 → 标准化板块名 -> 亿元（源数据为元）。"""
    compact = trade_date.replace("-", "")
    out: dict[str, float] = {}
    try:
        listing = ak.stock_board_industry_name_em()
    except Exception as exc:  # noqa: BLE001
        LOG.warning("东财行业列表拉取失败，跳过成交额填充: %s", exc)
        return out
    if listing is None or listing.empty:
        return out
    if not {"板块名称", "板块代码"}.issubset(listing.columns):
        return out
    for _, brow in listing.iterrows():
        name = str(brow.get("板块名称", "")).strip()
        code = str(brow.get("板块代码", "")).strip()
        if not name or not code:
            continue
        try:
            kdf = ak.stock_board_industry_hist_em(
                symbol=code,
                start_date=compact,
                end_date=compact,
                period="日k",
                adjust="",
            )
        except Exception as exc:  # noqa: BLE001
            LOG.debug("板块 %s 日K成交额拉取失败: %s", name, exc)
            continue
        if kdf is None or kdf.empty or "成交额" not in kdf.columns:
            continue
        amt = _safe_float(kdf.iloc[-1]["成交额"])
        if amt is not None:
            out[_norm_name(name)] = amt / 1e8
    return out


def _build_industry_code_map() -> dict[str, str]:
    code_map: dict[str, str] = {}
    # 同花顺行业板块列表含行业/板块代码，与同花顺资金流行业名对齐。
    try:
        ths_df = ak.stock_board_industry_name_ths()
        if not ths_df.empty and {"name", "code"}.issubset(set(ths_df.columns)):
            for _, row in ths_df.iterrows():
                name = str(row["name"]).strip()
                code = str(row["code"]).strip()
                if name and code:
                    code_map[_norm_name(name)] = code
    except Exception as exc:  # noqa: BLE001
        LOG.warning("获取行业代码映射失败(THS): %s", exc)
    return code_map


def _normalize_records(
    period_type: str,
    trade_date: str,
    df: pd.DataFrame,
    industry_code_map: dict[str, str],
    em_turnover_by_norm_name: dict[str, float] | None = None,
) -> list[tuple]:
    if df is None or df.empty:
        return []

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    records: list[tuple] = []
    code_col = None
    for candidate in ("行业代码", "板块代码", "代码", "code"):
        if candidate in df.columns:
            code_col = candidate
            break

    for _, row in df.iterrows():
        mapped = _normalize_row_by_position(row)
        if code_col is not None:
            code_val = row.get(code_col)
            mapped["industry_code"] = None if pd.isna(code_val) else str(code_val)
        if not mapped["industry_code"] and mapped["industry_name"]:
            mapped["industry_code"] = industry_code_map.get(_norm_name(mapped["industry_name"]))
        if not mapped["industry_name"]:
            continue
        to_yi = _turnover_yi_from_df_row(row, df.columns)
        if to_yi is None and em_turnover_by_norm_name and mapped["industry_name"]:
            to_yi = em_turnover_by_norm_name.get(_norm_name(mapped["industry_name"]))
        mapped["industry_turnover"] = to_yi
        records.append(
            (
                trade_date,
                period_type,
                mapped["ranking_no"],
                mapped["industry_code"],
                mapped["industry_name"],
                mapped["industry_index_value"],
                mapped["industry_change_pct"],
                mapped["main_net_inflow"],
                mapped["super_large_net_inflow"],
                mapped["large_net_inflow"],
                mapped["company_count"],
                mapped["top_stock_name"],
                mapped["top_stock_change_pct"],
                mapped["current_price"],
                mapped["industry_turnover"],
                json.dumps({k: (None if pd.isna(v) else v) for k, v in row.items()}, ensure_ascii=False, default=str),
                now,
                now,
            )
        )
    return records


def _upsert_rows(conn: pymysql.connections.Connection, table_name: str, rows: Iterable[tuple]) -> int:
    rows = list(rows)
    if not rows:
        return 0

    sql = f"""
    INSERT INTO {table_name} (
        trade_date, period_type, ranking_no, industry_code, industry_name, industry_index_value, industry_change_pct,
        main_net_inflow, super_large_net_inflow, large_net_inflow, company_count, top_stock_name,
        top_stock_change_pct, current_price, industry_turnover, raw_json, created_at, updated_at
    )
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, CAST(%s AS JSON), %s, %s)
    ON DUPLICATE KEY UPDATE
        ranking_no = VALUES(ranking_no),
        industry_code = VALUES(industry_code),
        industry_index_value = VALUES(industry_index_value),
        industry_change_pct = VALUES(industry_change_pct),
        main_net_inflow = VALUES(main_net_inflow),
        super_large_net_inflow = VALUES(super_large_net_inflow),
        large_net_inflow = VALUES(large_net_inflow),
        company_count = VALUES(company_count),
        top_stock_name = VALUES(top_stock_name),
        top_stock_change_pct = VALUES(top_stock_change_pct),
        current_price = VALUES(current_price),
        industry_turnover = VALUES(industry_turnover),
        raw_json = VALUES(raw_json),
        updated_at = VALUES(updated_at);
    """
    with conn.cursor() as cursor:
        cursor.executemany(sql, rows)
    conn.commit()
    return len(rows)


def run(
    host: str,
    port: int,
    user: str,
    password: str,
    database: str,
    table_name: str = DEFAULT_TABLE_NAME,
    periods: list[str] | None = None,
    trade_date: str | None = None,
) -> int:
    periods = periods or DEFAULT_PERIODS
    periods = [_normalize_period(item) for item in periods]
    run_date = trade_date or datetime.now().strftime("%Y-%m-%d")

    conn = pymysql.connect(
        host=host,
        port=port,
        user=user,
        password=password,
        database=database,
        charset="utf8mb4",
        autocommit=False,
    )
    _create_table_if_not_exists(conn, table_name)
    _ensure_table_columns(conn, table_name)
    industry_code_map = _build_industry_code_map()
    em_turnover_map = _build_em_industry_turnover_yi_map(run_date)

    total = 0
    for period in periods:
        try:
            df = ak.stock_fund_flow_industry(symbol=period)
            rows = _normalize_records(
                period_type=period,
                trade_date=run_date,
                df=df,
                industry_code_map=industry_code_map,
                em_turnover_by_norm_name=em_turnover_map,
            )
            cnt = _upsert_rows(conn, table_name, rows)
            total += cnt
            LOG.info("period=%s 写入/更新 %s 条", period, cnt)
        except Exception as exc:  # noqa: BLE001
            LOG.warning("period=%s 抓取失败: %s", period, exc)
    conn.close()
    return total


def _yuan_to_yi(value: object) -> float | None:
    """东财日 K 资金流净额一般为元，表字段为亿元。"""
    v = _safe_float(value)
    if v is None:
        return None
    return v / 1e8


def _date_cell_to_iso(val: object) -> str:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return ""
    if hasattr(val, "strftime"):
        return val.strftime("%Y-%m-%d")
    s = str(val).strip()
    return s[:10] if len(s) >= 10 else s


def _em_sector_name_to_code() -> dict[str, str]:
    try:
        from akshare.stock.stock_fund_em import _get_stock_sector_fund_flow_summary_code

        return dict(_get_stock_sector_fund_flow_summary_code())
    except Exception as exc:  # noqa: BLE001
        LOG.warning("获取东财行业名称-代码映射失败: %s", exc)
        return {}


def run_historical_em_range(
    host: str,
    port: int,
    user: str,
    password: str,
    database: str,
    table_name: str,
    start_iso: str,
    end_iso: str,
    sleep_seconds: float,
    allowed_trade_dates: set[str] | None,
) -> int:
    """
    使用东方财富「行业历史日 K 资金流」按真实日期回填（每行业一条时间序列，再按日汇总排名）。
    与 run() 中同花顺 stock_fund_flow_industry 快照不是同一数据源。
    """
    start_d = datetime.strptime(start_iso, "%Y-%m-%d").date()
    end_d = datetime.strptime(end_iso, "%Y-%m-%d").date()
    start_compact = start_d.strftime("%Y%m%d")
    end_compact = end_d.strftime("%Y%m%d")

    conn = pymysql.connect(
        host=host,
        port=port,
        user=user,
        password=password,
        database=database,
        charset="utf8mb4",
        autocommit=False,
    )
    _create_table_if_not_exists(conn, table_name)
    _ensure_table_columns(conn, table_name)

    code_map = _em_sector_name_to_code()
    if not code_map:
        conn.close()
        LOG.error("无法获取东财行业列表，终止历史回填。")
        return 0

    # 行业名 -> 该行业在区间内的行（已过滤日期）
    pending: list[dict] = []
    names = list(code_map.keys())
    for idx, name in enumerate(names):
        if idx > 0 and sleep_seconds > 0:
            time.sleep(sleep_seconds)
        try:
            df = ak.stock_sector_fund_flow_hist(symbol=name)
        except Exception as exc:  # noqa: BLE001
            LOG.warning("行业 %s 历史资金流抓取失败: %s", name, exc)
            continue
        if df is None or df.empty or "日期" not in df.columns:
            continue
        df = df.copy()
        df["_d"] = pd.to_datetime(df["日期"], errors="coerce").dt.date
        mask = (df["_d"] >= start_d) & (df["_d"] <= end_d)
        sub = df.loc[mask]

        turnover_by_date: dict[str, float] = {}
        try:
            kdf = ak.stock_board_industry_hist_em(
                symbol=name,
                start_date=start_compact,
                end_date=end_compact,
                period="日k",
                adjust="",
            )
            if kdf is not None and not kdf.empty and "成交额" in kdf.columns:
                kdf = kdf.copy()
                kdf["_kd"] = pd.to_datetime(kdf["日期"], errors="coerce").dt.date
                for _, kr in kdf.iterrows():
                    kd = kr["_kd"]
                    if not isinstance(kd, date) or kd < start_d or kd > end_d:
                        continue
                    kds = kd.strftime("%Y-%m-%d")
                    v = _safe_float(kr.get("成交额"))
                    if v is not None:
                        turnover_by_date[kds] = v / 1e8
        except Exception as exc:  # noqa: BLE001
            LOG.debug("行业 %s 东财板块日K成交额(区间)失败: %s", name, exc)

        for _, row in sub.iterrows():
            d = row["_d"]
            if not isinstance(d, date):
                continue
            ds = d.strftime("%Y-%m-%d")
            if allowed_trade_dates is not None and ds not in allowed_trade_dates:
                continue
            pending.append(
                {
                    "trade_date": ds,
                    "industry_name": name,
                    "industry_code": code_map.get(name),
                    "row": row,
                    "industry_turnover_yi": turnover_by_date.get(ds),
                }
            )

    by_day: dict[str, list[dict]] = defaultdict(list)
    for item in pending:
        by_day[item["trade_date"]].append(item)

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    all_tuples: list[tuple] = []

    def _sort_key(it: dict) -> tuple:
        row = it["row"]
        m = _yuan_to_yi(row.get("主力净流入-净额"))
        if m is None:
            return (1, 0.0)
        return (0, -m)

    for ds in sorted(by_day.keys()):
        items = sorted(by_day[ds], key=_sort_key)
        for rank, it in enumerate(items, start=1):
            row = it["row"]
            raw = {k: (None if pd.isna(v) else v) for k, v in row.items()}
            all_tuples.append(
                (
                    ds,
                    EM_HIST_PERIOD_TYPE,
                    rank,
                    it["industry_code"],
                    it["industry_name"],
                    None,
                    None,
                    _yuan_to_yi(row.get("主力净流入-净额")),
                    _yuan_to_yi(row.get("超大单净流入-净额")),
                    _yuan_to_yi(row.get("大单净流入-净额")),
                    None,
                    None,
                    None,
                    None,
                    it.get("industry_turnover_yi"),
                    json.dumps(raw, ensure_ascii=False, default=str),
                    now,
                    now,
                )
            )

    n = _upsert_rows(conn, table_name, all_tuples)
    conn.close()
    LOG.info(
        "东财历史日 K 回填完成：区间 %s ~ %s，共 %s 行（period_type=%s）",
        start_iso,
        end_iso,
        n,
        EM_HIST_PERIOD_TYPE,
    )
    return n


def _cal_date_to_iso(cal: object) -> str | None:
    s = str(cal).strip().replace("-", "")[:8]
    if len(s) == 8 and s.isdigit():
        return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
    return None


def _trade_cal_dataframe_akshare(start_compact: str, end_compact: str) -> pd.DataFrame:
    """
    使用 AkShare 新浪财经交易日历 tool_trade_date_hist_sina，生成与 Tushare trade_cal 结构相近的 DataFrame：
    exchange, cal_date, is_open, pretrade_date（均为字符串，cal_date/pretrade 为 YYYYMMDD）。
    区间内按自然日逐日一行；is_open 依新浪交易日列表判定；pretrade_date 为严格早于当日的最近交易日。
    """
    df_all = ak.tool_trade_date_hist_sina()
    if df_all is None or df_all.empty:
        return pd.DataFrame()

    all_trade_dates = sorted(
        set(pd.to_datetime(df_all["trade_date"], errors="coerce").dt.date.dropna().tolist())
    )
    trading_set = set(all_trade_dates)

    start_d = datetime.strptime(start_compact, "%Y%m%d").date()
    end_d = datetime.strptime(end_compact, "%Y%m%d").date()

    rows: list[dict] = []
    d = start_d
    while d <= end_d:
        cal = d.strftime("%Y%m%d")
        is_open = "1" if d in trading_set else "0"
        idx = bisect.bisect_left(all_trade_dates, d)
        pre = all_trade_dates[idx - 1] if idx > 0 else None
        pretrade = pre.strftime("%Y%m%d") if pre else ""
        rows.append(
            {
                "exchange": "SSE",
                "cal_date": cal,
                "is_open": is_open,
                "pretrade_date": pretrade,
            }
        )
        d += timedelta(days=1)

    return pd.DataFrame(rows)


def sync_trade_cal_to_mysql(start_compact: str, end_compact: str) -> int:
    """
    使用 AkShare（新浪财经）交易日历拉取 [start_compact, end_compact] 区间，先删后插写入 `trade_cal`。
    不依赖 Tushare。MySQL 连接使用 industry_indicator/config.py。
    """
    df = _trade_cal_dataframe_akshare(start_compact, end_compact)
    if df is None or df.empty:
        LOG.warning("AkShare 交易日历返回空区间: %s ~ %s", start_compact, end_compact)
        return 0

    try:
        from sqlalchemy import create_engine, text
    except ImportError as exc:
        raise RuntimeError("缺少 sqlalchemy，请先 pip install sqlalchemy") from exc

    cfg = _load_config()
    engine = create_engine(cfg.get_sqlalchemy_url_pymysql())
    with engine.begin() as conn:
        conn.execute(
            text("DELETE FROM trade_cal WHERE cal_date >= :s AND cal_date <= :e"),
            {"s": start_compact, "e": end_compact},
        )
        # pandas 与 SQLAlchemy 2 的 Connection 兼容写入
        df.to_sql("trade_cal", con=conn, if_exists="append", index=False)
    LOG.info("trade_cal 已同步 %s ~ %s，共 %s 行", start_compact, end_compact, len(df))
    return len(df)


def _fetch_trade_dates_from_db(
    host: str,
    port: int,
    user: str,
    password: str,
    database: str,
    start_compact: str,
    end_compact: str,
) -> list[str]:
    """从 trade_cal 读取交易日(YYYY-MM-DD)；失败或空表返回空列表。"""
    try:
        conn = pymysql.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            database=database,
            charset="utf8mb4",
        )
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT cal_date FROM trade_cal
                WHERE is_open = '1' AND cal_date >= %s AND cal_date <= %s
                ORDER BY cal_date
                """,
                (start_compact, end_compact),
            )
            rows = cur.fetchall()
        conn.close()
        out: list[str] = []
        for row in rows:
            iso = _cal_date_to_iso(row[0])
            if iso:
                out.append(iso)
        return out
    except Exception as exc:  # noqa: BLE001
        LOG.warning("无法从 trade_cal 读取交易日: %s", exc)
        return []


def _calendar_days_iso(start_iso: str, end_iso: str) -> list[str]:
    s = datetime.strptime(start_iso, "%Y-%m-%d").date()
    e = datetime.strptime(end_iso, "%Y-%m-%d").date()
    out: list[str] = []
    d = s
    while d <= e:
        out.append(d.strftime("%Y-%m-%d"))
        d += timedelta(days=1)
    return out


def _parse_args() -> argparse.Namespace:
    h, p, u, pw, db, tbl = _mysql_defaults_from_config()
    parser = argparse.ArgumentParser(
        description="抓取 AkShare 行业资金流并写入 MySQL。默认连接来自 industry_indicator/config.py。"
    )
    parser.add_argument("--host", default=h)
    parser.add_argument("--port", type=int, default=p)
    parser.add_argument("--user", default=u)
    parser.add_argument("--password", default=pw)
    parser.add_argument("--database", default=db)
    parser.add_argument("--table-name", default=tbl)
    parser.add_argument(
        "--periods",
        nargs="+",
        default=DEFAULT_PERIODS,
        help="可选: 即时 3日排行 5日排行 10日排行 20日排行",
    )
    parser.add_argument(
        "--trade-date",
        default=None,
        help="单次运行：入库日期 YYYY-MM-DD；默认今天。与 --from-date 互斥。",
    )
    parser.add_argument(
        "--from-date",
        default=None,
        help=(
            "批量：起始日 YYYY-MM-DD；仅东财历史日K（period_type=东财日K），"
            "不更新同花顺即时/多日快照。若要指定某日同花顺快照请勿传本参数，改用 --trade-date。"
        ),
    )
    parser.add_argument(
        "--to-date",
        default=None,
        help="批量：结束日 YYYY-MM-DD；省略则默认为「运行当天」，区间可能被拉长到多日。",
    )
    parser.add_argument(
        "--sleep-seconds",
        type=float,
        default=0.5,
        help="批量(东财历史)模式下，每抓取一个行业后的间隔秒数，减轻源站压力。",
    )
    parser.add_argument(
        "--sync-trade-cal",
        action="store_true",
        help="先同步 AkShare 新浪财经交易日历到 MySQL 表 trade_cal（与下方日期区间一致）。",
    )
    parser.add_argument(
        "--sync-trade-cal-only",
        action="store_true",
        help="仅同步 trade_cal（AkShare），不执行行业资金流；需配合 --from-date（及可选 --to-date）。",
    )
    return parser.parse_args()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = _parse_args()
    today = datetime.now().strftime("%Y-%m-%d")

    if args.sync_trade_cal_only:
        if not args.from_date:
            raise SystemExit("--sync-trade-cal-only 需要指定 --from-date（及可选 --to-date）")
        end_iso = args.to_date or today
        start_compact = args.from_date.replace("-", "")
        end_compact = end_iso.replace("-", "")
        if start_compact > end_compact:
            raise SystemExit("--from-date 不能晚于 --to-date")
        n = sync_trade_cal_to_mysql(start_compact, end_compact)
        LOG.info("仅同步 trade_cal 完成，共 %s 行", n)
        raise SystemExit(0)

    if args.from_date:
        end_iso = args.to_date or today
        if not args.to_date:
            LOG.warning(
                "未指定 --to-date，结束日已默认为今天（%s）。若只想处理单日，请同时写 "
                "--from-date 与 --to-date 为同一日。",
                today,
            )
        LOG.warning(
            "当前为「区间批量」模式：只写入东财历史日K（period_type=%s），"
            "不会更新同花顺「即时/3日/5日/10日/20日」快照；"
            "表中这些周期若仍显示今天日期，来自上次「单日模式」任务。 "
            "若要在指定交易日抓取同花顺快照并写入 trade_date，请改用："
            "python run_industry_fund_flow.py --sync-trade-cal --trade-date YYYY-MM-DD "
            "（不要带 --from-date/--to-date）。",
            EM_HIST_PERIOD_TYPE,
        )
        start_compact = args.from_date.replace("-", "")
        end_compact = end_iso.replace("-", "")
        if start_compact > end_compact:
            raise SystemExit("--from-date 不能晚于 --to-date")
        if args.sync_trade_cal:
            sync_trade_cal_to_mysql(start_compact, end_compact)
        dates_from_db = _fetch_trade_dates_from_db(
            args.host,
            args.port,
            args.user,
            args.password,
            args.database,
            start_compact,
            end_compact,
        )
        if dates_from_db:
            allowed = set(dates_from_db)
        else:
            LOG.warning(
                "trade_cal 无可用交易日，按自然日集合过滤；东财日K仅含交易日，周末无数据。"
            )
            allowed = set(_calendar_days_iso(args.from_date, end_iso))
        total = run_historical_em_range(
            host=args.host,
            port=args.port,
            user=args.user,
            password=args.password,
            database=args.database,
            table_name=args.table_name,
            start_iso=args.from_date,
            end_iso=end_iso,
            sleep_seconds=args.sleep_seconds,
            allowed_trade_dates=allowed,
        )
        LOG.info("任务完成，总写入/更新: %s", total)
    else:
        trade_date = args.trade_date or today
        if args.sync_trade_cal:
            td = trade_date.replace("-", "")
            sync_trade_cal_to_mysql(td, td)
        count = run(
            host=args.host,
            port=args.port,
            user=args.user,
            password=args.password,
            database=args.database,
            table_name=args.table_name,
            periods=args.periods,
            trade_date=trade_date,
        )
        LOG.info("任务完成，总写入/更新: %s", count)
