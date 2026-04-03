#!/usr/bin/env python
# -*- coding: utf-8 -*-

import akshare as ak
import pandas as pd
import numpy as np


def get_financial(stock):
    try:
        df = ak.stock_financial_abstract_ths(symbol=stock)
        df = df.sort_values('报告期', ascending=False)

        latest = df.iloc[0]

        return {
            "rev": float(latest['营业总收入同比增长率']),
            "profit": float(latest['净利润同比增长率']),
            "roe": float(latest['净资产收益率'])
        }
    except:
        return None


def get_valuation(stock):
    try:
        df = ak.stock_individual_info_em(symbol=stock)

        pe = float(df[df['item'] == '市盈率']['value'].values[0])
        pb = float(df[df['item'] == '市净率']['value'].values[0])

        return {"pe": pe, "pb": pb}
    except:
        return None


def get_pe_percentile(stock):
    try:
        df = ak.stock_zh_a_hist(symbol=stock, period="daily", adjust="qfq")

        # 用收盘价/eps近似PE（简化）
        df['pe'] = df['收盘'] / df['收盘'].rolling(252).mean()

        current_pe = df['pe'].iloc[-1]
        percentile = (df['pe'] < current_pe).mean()

        return percentile
    except:
        return None


def get_industry_proxy_metrics(stocks):
    data = []

    for stock in stocks:
        f = get_financial(stock)
        if f:
            data.append(f)

    df = pd.DataFrame(data)

    return {
        "shipment": df['rev'].mean(),  # 用营收代替出货
        "profit": df['profit'].mean(),
        "roe": df['roe'].mean()
    }


def aggregate_industry(industry_name):
    stocks_df = ak.stock_board_industry_cons_em(symbol=industry_name)
    stocks = stocks_df['代码'].tolist()

    records = []

    for s in stocks:
        f = get_financial(s)
        v = get_valuation(s)
        pe_pct = get_pe_percentile(s)

        if f and v and pe_pct:
            records.append({
                **f,
                **v,
                "pe_pct": pe_pct
            })

    if len(records) == 0:
        return None

    df = pd.DataFrame(records)

    return df.mean()


def zscore(series):
    return (series - series.mean()) / series.std()


def compute_scores(industry_data, manual_data=None):
    df = pd.DataFrame(industry_data).T

    # ===== 标准化 =====
    for col in df.columns:
        df[col + "_z"] = zscore(df[col])

    # ===== 兑现度 =====
    df['realization'] = (
            0.4 * df['rev_z'] +
            0.4 * df['profit_z'] +
            0.2 * df['roe_z']
    )

    # ===== 估值 =====
    df['valuation'] = (
            -0.5 * df['pe_z'] +
            -0.5 * df['pb_z'] +
            -0.3 * df['pe_pct_z']
    )

    # ===== 景气度 =====
    df['prosperity'] = df['rev_z']  # 默认替代

    # 👉 覆盖手动行业
    if manual_data:
        for k, v in manual_data.items():
            if k in df.index:
                df.loc[k, 'prosperity'] = (
                        0.4 * v['shipment'] +
                        0.3 * v['capex'] +
                        0.2 * v['price'] -
                        0.1 * v['inventory']
                )

    # ===== 总分 =====
    df['total_score'] = (
            0.4 * df['prosperity'] +
            0.3 * df['realization'] +
            0.3 * df['valuation']
    )

    return df.sort_values('total_score', ascending=False)


industry_list = ak.stock_board_industry_name_em()['板块名称'].tolist()[:10]

industry_data = {}

for ind in industry_list:
    print("Processing:", ind)
    res = aggregate_industry(ind)

    if res is not None:
        industry_data[ind] = res

result = compute_scores(industry_data, manual_data=industry_manual)

print(result[['prosperity', 'realization', 'valuation', 'total_score']])