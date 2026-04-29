# A股主力资金监控系统（微信小程序 + FastAPI）

## 目录说明

| 路径 | 用途 |
|------|------|
| `sql/schema.sql` | MySQL 8 建表：用户、订单、市场快照、股票池、评分、日志及 industry_fund_flow_di |
| `backend/app/main.py` | FastAPI 入口、CORS、定时任务挂载 |
| `backend/app/config.py` | 环境变量配置 |
| `backend/app/database.py` | SQLAlchemy 引擎 / Session |
| `backend/app/api/*.py` | REST：认证、仪表盘、榜单、行业详情、用户 |
| `backend/app/services/*.py` | 查询、评分引擎、吸筹/出货逻辑、市场快照任务 |
| `backend/app/tasks/scheduler.py` | APScheduler 15:10 日终管道 |
| `miniprogram/` | 小程序原生 + Vant Weapp（需 npm 构建） |
| `docs/DEPLOY.md` | 通用部署说明 |
| `docs/DEPLOY_ALIYUN.md` | **阿里云 ECS** 一步步部署（推荐） |
| `deploy/*.example` | Nginx / Supervisor 配置模板 |
| **`tables_metrics/README.md`** | **MySQL 使用表清单 + 各指标计算口径（必读维护）** |

## 本地运行后端

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate  # Windows
pip install -r requirements.txt
copy .env.example .env
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

接口前缀：`/api/v1`，健康检查：`GET /health`。

开发登录：`POST /api/v1/auth/wechat/login` body `{"code":"dev_xxx"}`。

## MVP（7 天）vs Pro（30 天）

**MVP（7 天上线）**
- 仪表盘 + 榜单 + 行业详情（文本序列）+ 评分落库 + 会员字段与前端遮罩
- 定时任务跑评分；微信登录 dev/mock；部署文档

**Pro（30 天升级）**
- 微信支付签约 VIP、订阅消息模板推送
- Redis 缓存全量、行业指数 K 线真实接入（Tushare/AkShare）
- 龙头股自动入库 `stock_pool_di`、交易日历过滤调度
- 图表组件（ec-canvas）、深色模式切换、埋点与风控规则引擎
