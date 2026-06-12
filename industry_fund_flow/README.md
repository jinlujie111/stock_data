# 行业资金流网站

基于 FastAPI 的 Web 应用，当前仅实现**用户注册、登录、退出**。

## 环境

复用项目 `dw-utils/func.sh` 中的 `MYSQL_*` 连接 `stock_data` 库；启动时自动建表 `app_user`。

```bash
source dw-utils/func.sh
export IFF_JWT_SECRET='请改为随机长字符串'   # 生产环境必设
```

## 启动

```bash
bash industry_fund_flow/run.sh
```

浏览器访问：`http://localhost:8081`（默认 8081，避免与 XXL-JOB 的 8080 冲突）

- `/register` — 注册
- `/login` — 登录
- `/` — 登录后首页
- `POST /logout` — 退出

## 手动建表（可选）

```bash
source dw-utils/func.sh
mysql -h "$MYSQL_HOST" -u "$MYSQL_USER" -p"$MYSQL_PASSWORD" "$MYSQL_DATABASE" \
  < industry_fund_flow/sql/app_user.sql
```

## API

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/me` | 当前用户（需 Cookie `iff_token`） |
