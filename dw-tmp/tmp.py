#!/usr/bin/env python
# -*- coding: utf-8 -*-
import akshare as ak

# 获取行业资金流排名（实时）
df = ak.stock_sector_fund_flow_rank(indicator="今日")
print(df.columns)
# 返回字段通常包括：
# ['行业', '净流入', '主力净流入', '超大单', '大单', '中单', '小单', '涨跌幅', '领涨股']