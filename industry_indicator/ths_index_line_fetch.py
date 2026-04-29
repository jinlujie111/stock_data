# -*- coding: utf-8 -*-
"""
同花顺行业指数日 K（d.10jqka.com.cn line js）。

ak.stock_board_industry_index_ths 存在两类问题会导致增量侧拿不到指数线、从而仍落库一览表量级（如 volume≈3332）：
1. 年份循环为 range(begin_year, datetime.now().year + 1)。当 start_date 的年份大于本机当前日历年
   （例如在 2025 年的机器上请求 20260101–20260429）时，range(2026, 2026) 为空，返回空表。
2. 使用 DataFrame[start_date:end_date] 字符串切片筛选日期，改为按「日期」列比较更稳妥。
"""
from __future__ import annotations

from datetime import datetime

import akshare as ak
import pandas as pd
import py_mini_racer
import requests
from akshare.datasets import get_ths_js
from akshare.utils import demjson


def _get_file_content_ths(file: str = "ths.js") -> str:
    path = get_ths_js(file)
    with open(path, encoding="utf-8") as f:
        return f.read()


def fetch_stock_board_industry_index_ths(
    symbol: str,
    start_date: str,
    end_date: str,
) -> pd.DataFrame:
    """
    与 ak.stock_board_industry_index_ths 同源 URL，修正年份范围与日期筛选。

    :param symbol: 行业名称，须与 ak.stock_board_industry_name_ths 的 name 一致
    :param start_date: YYYYMMDD
    :param end_date: YYYYMMDD
    """
    ref = ak.stock_board_industry_name_ths()
    if ref is None or ref.empty:
        return pd.DataFrame()
    sym = str(symbol).strip()
    m = ref[ref["name"].astype(str).str.strip() == sym]
    if m.empty:
        return pd.DataFrame()
    symbol_code = str(m.iloc[0]["code"]).strip()

    begin_year = int(start_date[:4])
    end_year = int(end_date[:4])
    now_year = datetime.now().year
    last_year = max(begin_year, end_year, now_year)

    big_df = pd.DataFrame()
    js_code = py_mini_racer.MiniRacer()
    js_code.eval(_get_file_content_ths("ths.js"))
    v_code = js_code.call("v")
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/89.0.4389.90 Safari/537.36",
        "Referer": "http://q.10jqka.com.cn",
        "Host": "d.10jqka.com.cn",
        "Cookie": f"v={v_code}",
    }

    for year in range(begin_year, last_year + 1):
        url = f"https://d.10jqka.com.cn/v4/line/bk_{symbol_code}/01/{year}.js"
        r = requests.get(url, headers=headers, timeout=30)
        data_text = r.text
        try:
            demjson.decode(data_text[data_text.find("{") : -1])
        except Exception:  # noqa: BLE001
            continue
        temp_df = demjson.decode(data_text[data_text.find("{") : -1])
        temp_df = pd.DataFrame(temp_df["data"].split(";"))
        temp_df = temp_df.iloc[:, 0].str.split(",", expand=True)
        big_df = pd.concat(objs=[big_df, temp_df], ignore_index=True)

    if big_df.empty:
        return pd.DataFrame()

    if len(big_df.columns) == 11:
        big_df.columns = [
            "日期",
            "开盘价",
            "最高价",
            "最低价",
            "收盘价",
            "成交量",
            "成交额",
            "_",
            "_",
            "_",
            "_",
        ]
    else:
        big_df.columns = [
            "日期",
            "开盘价",
            "最高价",
            "最低价",
            "收盘价",
            "成交量",
            "成交额",
            "_",
            "_",
            "_",
            "_",
            "_",
        ]
    big_df = big_df[
        [
            "日期",
            "开盘价",
            "最高价",
            "最低价",
            "收盘价",
            "成交量",
            "成交额",
        ]
    ]
    big_df["日期"] = pd.to_datetime(big_df["日期"], errors="coerce").dt.date
    start_d = datetime.strptime(start_date, "%Y%m%d").date()
    end_d = datetime.strptime(end_date, "%Y%m%d").date()
    big_df = big_df[(big_df["日期"] >= start_d) & (big_df["日期"] <= end_d)].reset_index(drop=True)

    big_df["开盘价"] = pd.to_numeric(big_df["开盘价"], errors="coerce")
    big_df["最高价"] = pd.to_numeric(big_df["最高价"], errors="coerce")
    big_df["最低价"] = pd.to_numeric(big_df["最低价"], errors="coerce")
    big_df["收盘价"] = pd.to_numeric(big_df["收盘价"], errors="coerce")
    big_df["成交量"] = pd.to_numeric(big_df["成交量"], errors="coerce")
    big_df["成交额"] = pd.to_numeric(big_df["成交额"], errors="coerce")
    return big_df
