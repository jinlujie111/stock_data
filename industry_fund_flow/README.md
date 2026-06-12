# 行业资金流网站



基于 FastAPI 的 Web 应用，当前仅实现**用户注册、登录、退出**。



## 数据库



网站数据存放在 **`data_industry`** 库，与股票 ETL 的 **`stock_data`** 库分离。



```bash
# 1) root 建库并授权（仅首次）
mysql -u root -p < mysql_tables/data_industry_grants.sql

# 2) 建表并启动
source dw-utils/func.sh
init_data_industry_schema
export IFF_JWT_SECRET='请改为随机长字符串'   # 生产环境必设
```



连接变量：`IFF_MYSQL_*`（由 `func.sh` 从 `INDUSTRY_MYSQL_*` 导出）。



## 启动



```bash

source dw-utils/func.sh

bash industry_fund_flow/run.sh

# 或: run_industry_fund_flow_web

```



浏览器访问：`http://localhost:8082`（默认 8082，避免与 XXL-JOB 的 8080 冲突）



- `/register` — 注册

- `/login` — 登录

- `/` — 登录后首页

- `POST /logout` — 退出



## 手动建表（可选）



```bash

source dw-utils/func.sh

init_data_industry_schema

# 或仅建表（库已存在时）:

data_industry < industry_fund_flow/sql/app_user.sql

```



## API



| 方法 | 路径 | 说明 |

|------|------|------|

| GET | `/api/me` | 当前用户（需 Cookie `iff_token`） |


