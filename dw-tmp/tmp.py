import os
import tushare as ts
pro = ts.pro_api('kOxsKJfSHCAsIrePsxWkfUdGIbMhfLWyTEfPSdueqnzMsqGigIeIaprTDglfSstX')
pro._DataApi__http_url = "http://a.sszhixia.cn/"
df = pro.index_basic(limit=5)
print(df)
df = ts.pro_bar(api=pro, ts_code="000001.SZ", limit=3)
print(df)
