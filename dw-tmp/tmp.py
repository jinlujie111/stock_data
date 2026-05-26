#!/usr/bin/env python
# -*- coding: utf-8 -*-


import os
import tushare as ts
pro = ts.pro_api('kOxsKJfSHCAsIrePsxWkfUdGIbMhfLWyTEfPSdueqnzMsqGigIeIaprTDglfSstX')
pro._DataApi__http_url = "http://a.sszhixia.cn/"
df = pro.index_basic(limit=5)
print(df)
df = ts.pro_bar(api=pro, ts_code="000001.SZ", limit=3)
print(df)
#⭐️如果显示 Token 不对，请检查代码是不是少了这行
#pro._DataApi__http_url = "http://a.sszhixia.cn/"

df = pro.query('trade_cal', start_date='20180101', end_date='20181231')
print(df)