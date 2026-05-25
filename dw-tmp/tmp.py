import akshare as ak
df = ak.stock_zh_a_hist(symbol="000001", period="daily", start_date="20200101")

print(df)