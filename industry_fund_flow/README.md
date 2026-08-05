# 行业资金流网站

基于 FastAPI 的 Web 应用：用户登录 + **板块择时（买卖点 + T+1 回测）** + 自选。  
决策链路（资金/主线/量价/行业/K线）与板块龙头 **Web 已下线**；**ODS 同步日批保留**。

**启动方式**：见仓库根目录 [XXL-JOB执行顺序.md §八](../XXL-JOB执行顺序.md)（**不纳入日批 / func.sh 封装**）。

## 数据库

网站用户数据在 **`data_industry`** 库；板块/择时读 **`stock_data`** 库（只读授权）。

```bash
# 1) root 建库并授权（仅首次）
mysql -u root -p < mysql_tables/data_industry_grants.sql
mysql -u root -p < industry_fund_flow/sql/stock_read_grants.sql

# 2) 建表
source dw-utils/func.sh
init_data_industry_schema   # data_industry.app_user
# stock_data 表见 mysql_tables/stock_data.sql，由 ETL 日批写入

export IFF_JWT_SECRET='请改为随机长字符串'   # 生产环境必设
```

连接变量：`IFF_MYSQL_*`（func.sh 从 `INDUSTRY_MYSQL_*` 导出）；`stock_data` 读库用 `STOCK_MYSQL_*`（`source func.sh` 后可用）。

## 页面

浏览器默认：`http://localhost:8082`

| 路径 | 说明 |
|------|------|
| `/login` `/register` | 登录 / 注册 |
| `/` | 登录后首页（市场广度 / 大盘情绪） |
| `/dc/timing-signals` | **买卖信号**（当日 buy/sell + K 线标注） |
| `/dc/timing-rank` | **综合排行**（Score + 回测指标） |
| `/dc/timing-backtest` | **回测分析**（参数 / 净值 / 成交明细） |
| `/dc/board-timing` `/dc/timing-kline` | 兼容旧入口，302 → 买卖信号 |
| `/favorites/boards` | 板块自选 |
| `/favorites/stocks` | **已下线 404** |
| `/dc/fund-flow` `/dc/mainline` `/dc/volume-price` `/dc/dragon` `/dc/sectors` `/dc/kline` | **已下线 404** |
| `POST /logout` | 退出 |

## API（需 Cookie `iff_token`）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/me` | 当前用户 |
| GET | `/api/v1/mainline/rank` | 主线监控榜 |
| GET | `/api/v1/dragon/leaders` | 板块龙头摘要 |
| GET | `/api/dc/{slug}` | 五维 DWM 通用榜单 |

完整 API 与日批依赖见 [XXL-JOB执行顺序.md §八](../XXL-JOB执行顺序.md)。
