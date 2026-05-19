# 小程序后端 · MySQL 表与指标口径说明

本文档维护：**微信小程序（FastAPI）** 使用的数据库表、各接口依赖字段及**指标计算逻辑**。  
数据主来源为存量数仓表 **`industry_fund_flow_di`**（由主工程 ETL 入库，`period_type` 一般为 **`即时`**）。配置项见后端 **`PERIOD_INSTANT`**（默认「即时」）。

---

## 一、表一览（按是否被小程序后端直接使用）

| 表名 | 读/写 | 用途摘要 |
|------|--------|----------|
| **industry_fund_flow_di** | 读 | 行业资金流日快照：TOP10、榜单、详情曲线、吸筹/出货分析、市场快照聚合的输入源 |
| **market_daily_di** | 读；（定时任务）写 | 市场概览：总成交额近似、涨跌「行业」家数、风险提示文案 |
| **industry_score_di** | 读；（定时任务）写 | 次日潜伏/综合评分、分项得分、风险等级；榜单「潜伏」模块 |
| **stock_pool_di** | 读（可选） | 行业详情「龙头股」列表；无数据时退回 **industry_fund_flow_di.top_stock_name** |
| **users** | 读/写 | 微信登录 `openid` 等（`/auth`、`/user/me`；**无会员/VIP 业务逻辑**） |
| **vip_orders** | — | 表结构可保留；当前后端/小程序不实现会员支付与订单 |
| **user_subscriptions** | — | 订阅消息预留 |
| **system_logs** | 写 | 定时任务与异常日志（APScheduler  pipeline） |

> **`industry_fund_flow_di` 由主仓库 `sync/sync_runner.sh` 配置驱动写入**，小程序仅消费。

---

## 二、核心指标与计算逻辑

### 1. 口径前缀：`period_type = 即时`

所有基于行业资金流的查询均带 **`WHERE period_type = :即时`**（与环境变量一致）。  
同一交易日若有多周期排行（如 3 日/5 日），小程序默认只看 **即时** 当日截面。

---

### 2. 仪表盘 `/dashboard`

| 展示项 | 数据来源 | 计算/说明 |
|--------|----------|-----------|
| **资金主线 TOP10** | `industry_fund_flow_di` | 指定 `trade_date`（缺省用库内最新交易日）下 `period_type=即时`，按 **`main_net_inflow` 降序**取前 10 行 |
| **industry_summary（上涨/下跌行业数）** | `industry_fund_flow_di` | 当日即时 **全部行业行**：按 **`industry_change_pct`** \>0 / \<0 分别计数（平盘不计），字段 **`up_count` / `down_count`**；与下方 **市场概览** 使用的 **`market_daily_di`** 涨跌统计 **独立**（聚合口径可能不一致） |
| **市场概览 · 总成交额** | `market_daily_di.total_turnover_yi` | 由定时任务 **`refresh_market_daily`** 写入：对当日即时行业表 **`industry_turnover` 求和**（亿元口径，与源库字段一致） |
| **上涨/下跌家数** | `market_daily_di.up_count / down_count` | 同上任务：按行业 **`industry_change_pct`** \>0 统计「上涨行业数」、\<0 统计「下跌行业数」（**行业维度**，非全市场个股家数） |
| **风险提示** | `market_daily_di.risk_note` | 规则：`down_count > up_count` →「热点分化…」否则「赚钱效应回升…」 |
| **risk_note（接口兜底）** | 无 `market_daily_di` 时 | 文案固定兜底：「注意仓位与节奏…」 |

---

### 3. 榜单 `/rank/inflow`、`/rank/accumulate`、`/rank/exit`

| 模块 | 数据来源 | 计算逻辑 |
|------|----------|----------|
| **主力净流入榜** | `industry_fund_flow_di` | 当日即时，按 **`main_net_inflow` 降序**；分页参数 **`page` / `page_size`** |
| **连续吸筹** | `industry_fund_flow_di` | **`insight_service.consecutive_positive_days`**：滚动窗口内（默认回看约 30 日），从最新交易日往前数 **连续若干部 `main_net_inflow > 0`**；默认 **`min_days=5`**（接口参数 3/5/10）；排序：**连续天数降序，再按当日净流入降序** |
| **出货预警** | `industry_fund_flow_di` | **`exit_warning`**：**最近 3 个交易日** `main_net_inflow` 均 \<0 **且** 当日 **`industry_change_pct` \< 0** **且** 当日成交额 ≥ **近 5 日均成交额 × 1.1**（放量） |

---

### 4. 次日潜伏 `/rank/latent`

固定返回当日综合分 **TOP5** 行业行；**无登录/会员判断**，响应中 **无 `vip` 字段**。  
**若无数据**：列表为空且 `hint` 说明原因——潜伏榜依赖 **`industry_score_di`**，须先由 **`score_engine.compute_and_persist`** 写入（定时任务见 **`scheduler.job_daily_pipeline`**，默认每日 **15:10**）。仅有 **`industry_fund_flow_di`** 而未跑评分时，本接口 **`items` 为空**。

| 字段 | 来源表 | 计算逻辑 |
|------|--------|----------|
| **total_score** 等 | **industry_score_di** | 由 **`score_engine.compute_and_persist`** 每日写入（覆盖当日） |
| **综合分权重** | — | **40%** `score_rank_today`（当日净流入在全行业的 **百分位排名×100**）+ **30%** `score_sum5`（约 **近 7 自然日内**行业 **`main_net_inflow` 之和**的百分位）+ **20%** `score_turnover_amp`（当日成交额相对 **近窗均值** 的比值再百分位）+ **10%** `score_chg_strength`（当日 **`industry_change_pct` 百分位**） |
| **latent_rank** | **industry_score_di** | 按 **`total_score` 降序**的名次 |
| **risk_level** | **industry_score_di** | 规则：`chg<-2` 且 `inflow<0` → high；否则若 `chg<0` 或 `inflow<0` → medium；否则 low |

> **sum5 窗口**：当前实现为「结束日前约 7 天内」行业净流入之和，**非严格 5 个交易日**；注释中保留升级为「滚动 5 交易日」的空间。

---

### 5. 行业名称列表 `GET /industry/list-names`

| 字段 | 来源 | 说明 |
|------|------|------|
| **names** | `industry_fund_flow_di` | 指定 `trade_date`（缺省库内最新）下 **`period_type=即时`** 全表行业名，顺序与 **`main_net_inflow` 降序** 一致（与净流入榜同源）；可供扩展筛选。**板块资金流**页左侧已不设「行业详情」，当前小程序行业详情为独立页 **`pages/detail/detail`**（调用 **`/industry/{name}/detail`**） |

---

### 6. 行业详情 `/industry/{name}/detail`

| 模块 | 来源 | 说明 |
|------|------|------|
| **近 20 日资金序列** | `industry_fund_flow_di` | 同名行业、`trade_date ≤ 所选日`、`即时`，按日期倒序取 20 条再正序返回 |
| **评分卡片** | `industry_score_di` | `trade_date + industry_name` 唯一一行 |
| **龙头股** | **`stock_pool_di`** 优先 | 无则 **`top_stock_name`** 单行占位 |

---

### 7. 定时任务（写入衍生表）

| 任务 | 写入表 | 逻辑 |
|------|--------|------|
| **market_snapshot_job** | **market_daily_di** | 见上文「市场概览」聚合规则；先 `DELETE` 当日再 `INSERT` |
| **score_engine** | **industry_score_di** | 见上文「次日潜伏」权重与风险等级 |
| **system_logs** | **system_logs** | 记录任务成功/失败 |

---

## 三、用户相关表

| 表 | 用途 |
|----|------|
| **users** | `openid` 登录；JWT `sub` 为用户 id（库内若有 `is_vip` 等字段**未被接口使用**） |
| **vip_orders** | 仅占位表；当前无支付/会员流程 |

---

## 四、代码索引（便于对照维护）

| 逻辑 | 文件 |
|------|------|
| SQL 查询封装 | `backend/app/services/industry_query.py` |
| 吸筹/出货 | `backend/app/services/insight_service.py` |
| 评分入库 | `backend/app/services/score_engine.py` |
| 市场日快照入库 | `backend/app/services/market_snapshot_job.py` |
| 定时调度 | `backend/app/tasks/scheduler.py` |
| 行业详情 SQL | `backend/app/api/industry.py` |

---

## 五、变更约定

- 修改指标口径时：**同步更新本文档** + 对应 `services/*.py` 注释。  
- 新增消费表时：在 **第一节表一览** 登记，并在 **第二节** 增加小节说明字段与公式。
