# stock_data — XXL-JOB 调度执行顺序

> 维护日期：2026-06-28  
> 项目路径（服务器）：`/opt/stock_data`  
> 执行前统一：`cd /opt/stock_data && source dw-utils/func.sh`  
> **表结构真相源**：[`mysql_tables/stock_data.sql`](mysql_tables/stock_data.sql)（ETL 脚本内 `CREATE IF NOT EXISTS` 与之对齐）

**XXL-JOB 建议**

- 任务类型：BEAN / GLUE(Shell) 均可；推荐直接调用仓库脚本（见第三节）
- 调度参数：可传 `${n_date}`（`YYYYMMDD`），不传则默认当天
- 建议 Cron：交易日 **22:30**（收盘后 Tushare / 东财热榜数据较全）
- 失败告警：依赖 exit code；`run_ods_completeness_monitor` 返回 1 表示 ODS 有 ALERT
- Web 展示默认端口：**8082**（`industry_fund_flow`，避免与 XXL-JOB 8080 冲突）

**相关文档**

- [需求1-主线板块确认-需求文档.md](需求整理/需求1-主线板块确认-需求文档.md) — 主线榜业务与验收
- [需求4-AI板块成分股识别-技术文档.md](需求整理/需求4-AI板块成分股识别-技术文档.md)

---

## 〇、ODS 同步分层（`run_data_sync`）

| 层级 | 位置 | 职责 |
|------|------|------|
| 任务定义 | `db_sync_task`（配置库） | 数据源、`target_table`、`sync_mode`、`status` |
| 触发 | crontab / XXL-JOB | 每日调用 `run_data_sync` |
| 执行 | `dw-sync/sync_runner.sh` → `sync_data.py` | 读配置 → 拉数 → 写 `stock_data` |

```mermaid
sequenceDiagram
    participant CRON as crontab/XXL-JOB
    participant SH as sync_runner.sh
    participant PY as sync_data.py
    participant CFG as db_sync_task
    participant API as Tushare/AkShare
    participant DB as stock_data

    CRON->>SH: run_data_sync YYYYMMDD
    SH->>PY: source func.sh 后启动
    PY->>CFG: load_sync_tasks(status=1)
    loop 每条任务
        PY->>API: 按 proxy_source 拉数
        PY->>DB: 写入 target_table
    end
```

**依赖安装（服务器首次）**

```bash
cd /opt/stock_data && source dw-utils/func.sh
install_sync_deps
${PYTHON_BIN} -c "import pymysql, pandas, sqlalchemy, akshare; print('ok')"
```

**ODS 手工同步**

```bash
source dw-utils/func.sh
run_data_sync                          # 全部 status=1 任务
run_data_sync 20260616                 # 指定业务日
run_data_sync --source-table daily_basic --force
run_data_sync --dry-run                # 预览不写库
```

**新增 ODS 任务**：在 `db_sync_task` 插入记录，配置 `fetch_config` / `transform_config`（JSON）。占位符：`$trade_date`、`$full_start`、`$full_end`。停用：`UPDATE db_sync_task SET status=0 WHERE id=...`。

**财务指标回补**（景气 DWM 前置，脚本 `dw-sync/sync_ods_fina_indicator.sh`）：

```bash
bash dw-sync/sync_ods_fina_indicator.sh
# 或: bash dw-sync/sync_ods_fina_indicator.sh --start 20250101 --end 20260630
```

**查看同步配置与结果**

```bash
${data_config} -e "SELECT id, proxy_source, source_table, target_table, sync_mode, status FROM db_sync_task;"
${data_mysql} -e "SELECT COUNT(*) FROM ods_trading_day;"
```

---

## 一、任务拆分建议

XXL-JOB 管理台可建多个 Job，也可合并为单个日批（见第三节）。

| Job 名称 | Cron 示例（Linux crontab） | 脚本 | 说明 |
|----------|---------------------------|------|------|
| `stock_ods_daily` | `30 22 * * 1-5` | `xxl_daily_batch.sh` 前半（或拆 Job） | ODS + DWM + DWS |
| `stock_daily_all` | `30 22 * * 1-5` | **`dw-utils/xxl_daily_batch.sh`** | **推荐：日批一键** |
| `stock_ods_monthly` | `0 21 1 * *` | `dw-utils/xxl_monthly_batch.sh` | 每月 1 号 21:00 |
| `stock_dim_etf_weekly` | `0 3 * * 1` | `dw-utils/xxl_weekly_batch.sh` | 每周一：ETF 映射（需求1 机构化前置） |
| `stock_mainline_only` | 手工 / 补跑 | `dw-utils/xxl_mainline_batch.sh` | 仅需求1 主线 DWM+DWS |

> **Quartz（XXL-JOB）对照**：日批 `0 30 22 ? * MON-FRI`；月批 `0 0 21 1 * ?`；周批 `0 0 3 ? * MON`。

---

## 二、日批标准顺序

有依赖，请勿乱序。

| 步骤 | 任务 | 依赖 | 产品 |
|------|------|------|------|
| ① | `run_data_sync` | `daily` / `daily_basic` / `moneyflow` / `dc_*` / `ths_*` / `report_rc` / `fina_indicator_vip` / `limit_list_d` / `index_daily` / `etf_*` 等；`monthly`（`stock_company`、`fina_mainbz_vip`、`fina_mainbz`）非 1 号自动跳过 | 全部 |
| ② | `run_dwm_market_breadth` | `ods_stock_detail_di`、`ods_limit_list_di` | 首页广度 |
| ③ | `run_dwm_dc_industry_fund_flow` / `run_dwm_ths_industry_fund_flow` | 板块资金流 ODS | 需求1 五维 |
| ④ | `run_dwm_dc_industry_trend_strength` / `run_dwm_ths_industry_trend_strength` | 板块日线 + `ods_index_daily_di` | 需求1 五维 |
| ⑤ | `run_dwm_dc_industry_market_heat` / `run_dwm_ths_industry_market_heat` | `ods_dc_*` / 热榜；**需求4 `dim_industry_track` 前置** | 需求1 / 需求4 |
| ⑥ | `run_dwm_dc_industry_diffusion` / `run_dwm_ths_industry_diffusion` / `run_dwm_sw_industry_diffusion` | 成分 + 涨停 + 广度 | 需求1 五维 |
| ⑦ | `run_dwm_dc_industry_prosperity` / `run_dwm_ths_industry_prosperity` / `run_dwm_sw_industry_prosperity` | 成分 + `ods_fina_indicator` + `ods_report_rc_di` | 需求1 五维 |
| ⑧ | `run_dws_*_mainline_score` + `run_dws_*_mainline_monitor` | 上述全部 DWM | **需求1 主线榜** |
| ⑨ | `run_dim_industry_track` | ⑤ 市场热度 DWM | 需求4 DIM |
| ⑨b | `run_ai_core_pool_batch` | ⑨ DIM + ODS 公司/财报/研报 | **需求4 核心池** |
| ⑩ | `run_sector_dragon_batch` | 资金 DWM + `daily` / `moneyflow` | 需求2 |
| ⑪ | `run_dws_dc_industry_quant_mainline` | 全部东财 DWM + 龙头摘要 | **需求3 量化主线（东财行业）** |
| ⑫ | `run_ods_completeness_monitor` | — | ODS 完整度监控告警 |

**需求3 落库表（步骤 ⑪）**

| 表 | 说明 |
|----|------|
| `dws_dc_industry_quant_mainline_di` | FTELP 五主因子、MainScore、**行业/概念分别 Top10**、MA3/5/10 |
| `dws_dc_industry_quant_mainline_signal_di` | 启动 / 退潮 / 观察 + 原因 JSON |
| `dwm_dc_mainline_config` | 权重与信号阈值（默认 `content_types=行业,概念`） |

**需求1 落库表（步骤 ⑧）**

| 表 | 说明 |
|----|------|
| `dws_dc_industry_mainline_score_di` | 东财五维总分、等级、MA3/5/10 |
| `dws_dc_industry_mainline_monitor_di` | 东财监控 Top20、三阶段标签 |
| `dws_ths_*` / `dws_sw_*` | 同花顺 / 申万（Web 暂未接，仅数仓） |

---

## 三、日批一键脚本（推荐）

**仓库脚本**（与下文内容一致，便于版本管理）：

```bash
cd /opt/stock_data
bash dw-utils/xxl_daily_batch.sh          # 今天
bash dw-utils/xxl_daily_batch.sh 20260616 # 指定业务日
```

**XXL-JOB GLUE Shell 执行体**（等价）：

```bash
#!/bin/bash
set -euo pipefail
cd /opt/stock_data
bash dw-utils/xxl_daily_batch.sh "${1:-$(date +%Y%m%d)}"
```

脚本全文见 [`dw-utils/xxl_daily_batch.sh`](dw-utils/xxl_daily_batch.sh)。

---

## 四、月批脚本

`stock_company`、`fina_mainbz_vip`、`fina_mainbz` 在 `db_sync_task` 中为 `schedule_type=monthly`。日批 `run_data_sync` 在非 1 号会跳过；本 Job 用 `--force` 显式执行。

```bash
cd /opt/stock_data
bash dw-utils/xxl_monthly_batch.sh
# 或指定日期
bash dw-utils/xxl_monthly_batch.sh 20260601
```

脚本见 [`dw-utils/xxl_monthly_batch.sh`](dw-utils/xxl_monthly_batch.sh)。

---

## 五、周批脚本（可选，建议开启）

用于刷新 `dim_industry_etf_map`（自动 `index_match`），支撑需求1 **机构化**阶段判定；**不依赖手工维护**，手工 `manual` 映射仅作补强。

```bash
cd /opt/stock_data
bash dw-utils/xxl_weekly_batch.sh
```

脚本见 [`dw-utils/xxl_weekly_batch.sh`](dw-utils/xxl_weekly_batch.sh)。

---

## 六、排障 / 补跑

```bash
cd /opt/stock_data && source dw-utils/func.sh

# 只同步 ODS 某一表
run_data_sync 20260616 --source-table daily_basic --force

# ODS 区间补数
run_data_sync_range 20250101 20260615 --source-table daily_basic --force

# 只跑需求1 主线（ODS + 五维 DWM 已齐）
bash dw-utils/xxl_mainline_batch.sh 20260616
bash dw-utils/xxl_mainline_batch.sh 20250601 20260616   # 区间补 MA

# DWS 区间（更细粒度）
bash dw-dws/pro_dws_dc_industry_mainline_score_di.sh 20250601 20260616
bash dw-dws/pro_dws_dc_industry_mainline_monitor_di.sh 20250601 20260616

# 只跑板块龙头（需求2）
run_sector_dragon_batch 20260616

# 只刷新 AI 赛道 DIM（需求4）
run_dim_industry_track 20260616

# DWM 历史区间
bash dw-dwm/pro_dwm_dc_industry_market_heat_di.sh 20250101 20260615
```

**日志路径**：`/root/log/stock_log/${n_date}/pro_dws_dc_industry_mainline_*.log`

---

## 七、各步骤是否必须？

| 步骤 | 必须？ | 说明 |
|------|--------|------|
| `run_data_sync` | 是* | 下游 DWM 都依赖当日 ODS；*热榜建议 22:30 后 |
| DWM / DWS 主线（⑧） | **需求1 要** | 不做 `/dc/mainline` 可不跑 |
| `run_dim_industry_track` | 需求4 要 | 不做 AI 核心池可不跑 |
| `run_ai_core_pool_batch` | 需求4 要 | 无 LLM Key 时走规则引擎 |
| `run_sector_dragon_batch` | 需求2 要 | 不做板块龙头页可不跑 |
| `xxl_weekly_batch` | 建议 | 提升「机构化」命中率；无则仍可出榜 |
| `run_ods_completeness_monitor` | 建议 | 生产环境 ODS 完整度告警 |

需求4 AI ETL（`run_ai_core_pool_batch`）已接入日批，位于 `run_dim_industry_track` 之后、`run_sector_dragon_batch` 之前。

---

## 八、启动报表页面（Web）

> **与日批分离**：报表 Web **不写入** `xxl_daily_batch.sh` / `func.sh`，仅在本节文档维护启动命令；日批只负责写 `stock_data` 数仓。

报表由 **`industry_fund_flow`**（FastAPI + uvicorn）提供。默认端口 **8082**（避开 XXL-JOB 8080）。

### 8.1 首次部署（服务器执行一次）

```bash
cd /opt/stock_data

# 1) 用户库 + stock_data 只读授权
mysql -u root -p < mysql_tables/data_industry_grants.sql
mysql -u root -p < industry_fund_flow/sql/stock_read_grants.sql

# 2) 初始化登录用户表（data_industry.app_user）
source dw-utils/func.sh
init_data_industry_schema

# 3) 生产环境必设 JWT 密钥（写入 func.sh 或 export）
export IFF_JWT_SECRET="$(openssl rand -hex 32)"
```

| 库 | 用途 | 连接变量 |
|----|------|----------|
| `data_industry` | 注册 / 登录 | `IFF_MYSQL_*`（func.sh 从 `INDUSTRY_MYSQL_*` 导出） |
| `stock_data` | 板块 / 主线 / 龙头 / AI 核心池 | `STOCK_MYSQL_*` → Web 侧 `IFF_STOCK_MYSQL_*` |

### 8.2 启动 / 重启

Web **不纳入日批 / XXL-JOB**，需单独手工或 systemd 维护；以下命令复制即用。

**依赖（首次）**

```bash
cd /opt/stock_data
source dw-utils/func.sh
"${PYTHON_BIN}" -m pip install -r industry_fund_flow/requirements.txt
```

**开发 / 调试（前台）**

```bash
cd /opt/stock_data
source dw-utils/func.sh
export IFF_JWT_SECRET="$(openssl rand -hex 32)"   # 生产必设

cd industry_fund_flow
"${PYTHON_BIN}" -m uvicorn app.main:app --host 0.0.0.0 --port 8082 --reload
```

**生产（后台）**

```bash
cd /opt/stock_data
source dw-utils/func.sh
export IFF_JWT_SECRET="$(openssl rand -hex 32)"
mkdir -p /root/log/stock_log/web

pkill -f "uvicorn app.main:app" 2>/dev/null || true

cd industry_fund_flow
nohup "${PYTHON_BIN}" -m uvicorn app.main:app \
  --host 0.0.0.0 --port 8082 \
  >> /root/log/stock_log/web/industry_fund_flow.log 2>&1 &

sleep 1
curl -s -o /dev/null -w "%{http_code}\n" "http://127.0.0.1:8082/login"
# 期望 200
```

| 环境变量 | 默认 | 说明 |
|----------|------|------|
| `IFF_PORT` | `8082` | 启动时 `--port`；与 XXL-JOB 8080 冲突可改 8083 |
| `IFF_JWT_SECRET` | — | **生产必设**，否则重启后登录态失效 |
| `STOCK_MYSQL_*` | func.sh 导出 | 读 `stock_data`；`source func.sh` 后自动可用 |

外网访问需在安全组 / 防火墙放行 `8082`（或实际端口）。登录 Cookie 名：**`iff_token`**。

### 8.3 报表页面与日批依赖

日批完成后访问对应页面；**无数据时先查第二节步骤是否已跑、再查 §8.5 SQL**。

| 页面 | URL | 日批步骤 | 主要读表 |
|------|-----|----------|----------|
| 首页（市场广度） | `/` | ② | `dwm_market_breadth_di` |
| **主线板块**（需求1） | `/dc/mainline` | ⑧ | `dws_dc_industry_mainline_monitor_di` |
| **量化主线**（需求3） | `/dc/quant-mainline` | ⑪ | `dws_dc_industry_quant_mainline_di`、`dws_dc_industry_quant_mainline_signal_di` |
| **板块龙头**（需求2） | `/dc/dragon` | ⑩ | `dwm_sector_stock_dragon_score_di` 等 |
| **AI 核心池**（需求4） | `/dc/ai-core` | ⑨ + ⑨b | `dwm_industry_stock_core_di`、`dwm_industry_stock_ai_score_di` |
| 资金强度 | `/dc/fund-flow` | ③ | `dwm_dc_industry_fund_flow_di` |
| 趋势强度 | `/dc/trend-strength` | ④ | `dwm_dc_industry_trend_strength_di` |
| 市场热度 | `/dc/market-heat` | ⑤ | `dwm_dc_industry_market_heat_di` |
| 产业景气 | `/dc/prosperity` | ⑦ | `dwm_dc_industry_prosperity_di` |
| 扩散效应 | `/dc/diffusion` | ⑥ | `dwm_dc_industry_diffusion_di` |
| 登录 / 注册 | `/login` `/register` | — | `data_industry.app_user` |

导航栏「东财板块」下拉与各 `/dc/{slug}` 维度页共用 [`dc_registry.py`](industry_fund_flow/app/dc_registry.py) 注册。

**推荐访问顺序（收盘后）**

1. 等日批 `xxl_daily_batch.sh` 跑完（或 XXL-JOB `stock_daily_all` 成功）
2. 浏览器打开 `http://<host>:8082/login` 登录
3. 首页看市场广度 → 主线榜 → 量化主线 → 板块龙头 → AI 核心池

### 8.4 API 速查（需登录 Cookie）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/me` | 当前用户 |
| GET | `/api/v1/mainline/rank?trade_date=YYYYMMDD&top=20` | 需求1 主线榜 |
| GET | `/api/v1/mainline/history?industry_code=BKxxxx.DC&days=60` | 主线历史得分 |
| GET | `/api/v1/quant-mainline/top-groups?trade_date=YYYYMMDD` | 需求3 行业/概念分榜 Top10 |
| GET | `/api/v1/quant-mainline/signals?trade_date=YYYYMMDD` | 启动 / 退潮信号 |
| GET | `/api/v1/dragon/leaders?trade_date=YYYYMMDD` | 需求2 龙头摘要 |
| GET | `/api/v1/ai-core/pool?trade_date=YYYYMMDD` | 需求4 核心池 |
| GET | `/api/v1/ai-core/scores?trade_date=YYYYMMDD&industry_id=...` | 需求4 全量评分 |
| GET | `/api/dc/{slug}?trade_date=YYYYMMDD` | 五维 DWM 通用榜单 |

命令行测 API（先登录拿 Cookie）：

```bash
curl -c cookies.txt -b cookies.txt -X POST "http://127.0.0.1:8082/login" \
  -d "username=你的用户&password=你的密码" -L -s -o /dev/null

curl -b cookies.txt -s "http://127.0.0.1:8082/api/v1/mainline/rank?top=20" | python3 -m json.tool
curl -b cookies.txt -s "http://127.0.0.1:8082/api/v1/ai-core/pool?trade_date=20260626" | python3 -m json.tool
```

### 8.5 页面无数据速查 SQL

将 `@d` 换成实际交易日（`YYYY-MM-DD`）。

```sql
USE stock_data;
SET @d = '2026-06-26';

SELECT 'mainline' AS page, COUNT(*) FROM dws_dc_industry_mainline_monitor_di WHERE trade_date = @d
UNION ALL SELECT 'quant', COUNT(*) FROM dws_dc_industry_quant_mainline_di WHERE trade_date = @d
UNION ALL SELECT 'dragon', COUNT(*) FROM dwm_sector_stock_dragon_score_di WHERE trade_date = @d
UNION ALL SELECT 'ai_core', COUNT(*) FROM dwm_industry_stock_core_di WHERE trade_date = @d
UNION ALL SELECT 'ai_score', COUNT(*) FROM dwm_industry_stock_ai_score_di WHERE trade_date = @d;
```

| 页面空 | 常见原因 |
|--------|----------|
| 主线榜 | 日批 ⑧ 未跑；`stock_read_grants.sql` 未执行 |
| 量化主线 | 日批 ⑪ 未跑 |
| 板块龙头 | 日批 ⑩ 未跑；成分 `<3` 的板块被跳过 |
| AI 核心池 | ⑨b 未跑或失败；核心池分数 `< score_threshold` 时 `core_di` 可能为 0 但 `ai_score_di` 应有全量 |
| 五维维度页 | 对应 DWM 步骤 ③～⑦ 未跑 |

Web 日志：`/root/log/stock_log/web/industry_fund_flow.log`

---

## 九、需求1 数据验收（SQL 速查）

将 `@d` 换成实际交易日（`YYYY-MM-DD`）。

```sql
USE stock_data;
SET @d = '2026-06-13';

-- 五维 DWM 是否有数
SELECT 'fund' AS dim, COUNT(*) FROM dwm_dc_industry_fund_flow_di WHERE trade_date = @d
UNION ALL SELECT 'trend', COUNT(*) FROM dwm_dc_industry_trend_strength_di WHERE trade_date = @d
UNION ALL SELECT 'heat', COUNT(*) FROM dwm_dc_industry_market_heat_di WHERE trade_date = @d
UNION ALL SELECT 'diffusion', COUNT(*) FROM dwm_dc_industry_diffusion_di WHERE trade_date = @d
UNION ALL SELECT 'prosperity', COUNT(*) FROM dwm_dc_industry_prosperity_di WHERE trade_date = @d;

-- 主线 Top10
SELECT rank_no, industry_name, main_score, mainline_level, mainline_stage
FROM dws_dc_industry_mainline_monitor_di
WHERE trade_date = @d AND content_type = '行业' AND is_top20 = 1
ORDER BY rank_no LIMIT 10;

-- 三阶段分布（「机构化」可能为 0，见已知限制）
SELECT mainline_stage, COUNT(*) AS cnt
FROM dws_dc_industry_mainline_monitor_di
WHERE trade_date = @d
GROUP BY mainline_stage;
```

**已知限制**：「机构化」依赖 `dim_industry_etf_map`（周批自动）+ `ods_etf_share_size_di` + 东财板块名与申万行业名模糊匹配；概念板块常无样本，**无手工维护可接受**，不影响主线榜主体验收。

**API 快速测**（先登录拿 Cookie，详见 §八.4）：

```bash
curl -c cookies.txt -b cookies.txt -X POST "http://127.0.0.1:8082/login" \
  -d "username=你的用户&password=你的密码" -L -s -o /dev/null

curl -b cookies.txt -s "http://127.0.0.1:8082/api/v1/mainline/rank?top=20" | python3 -m json.tool
curl -b cookies.txt -s "http://127.0.0.1:8082/api/me"
```

---

## 十、新增 ODS 表备忘（2026-06 起）

| source_table | target_table | 调度 | 用途 |
|--------------|--------------|------|------|
| `daily_basic` | `ods_daily_basic_di` | daily | 市值 / 换手率 / PE，需求4 V1 权重 |
| `stock_company` | `ods_stock_company_di` | monthly | 公司简介 / 主营，需求4 Prompt |
| `fina_mainbz_vip` | `ods_fina_mainbz_di` | monthly | 主营业务构成 VIP（近 2 季全市场，月批 `--force`） |
| `fina_mainbz` | `ods_fina_mainbz_di` | monthly | 按股补全 mainbz 缺失 |

---

## 十一、仓库脚本索引

| 文件 | 说明 |
|------|------|
| [`mysql_tables/stock_data.sql`](mysql_tables/stock_data.sql) | **数仓 DDL 真相源** |
| [`dw-utils/func.sh`](dw-utils/func.sh) | MySQL 环境、`run_data_sync`、DWM/DWS 封装 |
| [`dw-sync/sync_runner.sh`](dw-sync/sync_runner.sh) | ODS 同步入口 |
| [`dw-sync/sync_data.py`](dw-sync/sync_data.py) | 配置驱动同步 |
| [`dw-utils/xxl_daily_batch.sh`](dw-utils/xxl_daily_batch.sh) | 日批一键 |
| [`dw-utils/xxl_monthly_batch.sh`](dw-utils/xxl_monthly_batch.sh) | 月批 |
| [`dw-utils/xxl_weekly_batch.sh`](dw-utils/xxl_weekly_batch.sh) | 周批 ETF 映射 |
| [`dw-utils/xxl_mainline_batch.sh`](dw-utils/xxl_mainline_batch.sh) | 仅需求1 补跑 |
| [`dw-monitor/pro_ods_completeness.sh`](dw-monitor/pro_ods_completeness.sh) | ODS 完整度监控（配置见 `ods_checks.json`） |
| [`dw-dwm/pro_dwm_ai_core_pool_di.sh`](dw-dwm/pro_dwm_ai_core_pool_di.sh) | 需求4 AI 核心池批处理 |
| [`dw-dwm/pro_dwm_*`](dw-dwm/) | DWM ETL（东财/THS/SW 板块因子，**全部保留**） |
| [`dw-dws/pro_dws_*`](dw-dws/) | DWS ETL（主线评分/监控/量化主线，**THS/SW 保留**） |
| [`industry_fund_flow/README.md`](industry_fund_flow/README.md) | 报表 Web 说明（启动见 §八，不进批处理） |
| [`industry_fund_flow/sql/stock_read_grants.sql`](industry_fund_flow/sql/stock_read_grants.sql) | Web 只读授权 |

---

## 十二、常见问题

| 现象 | 排查 |
|------|------|
| 任务成功但表无数据 | AkShare/Tushare 是否返回空；`run_data_sync --dry-run` 看行数 |
| `Access denied` | 检查 `dw-utils/func.sh` 中 MySQL 账号 |
| 1045 / 变量未加载 | 先 `source dw-utils/func.sh` 或走 `sync_runner.sh` |
| Web 主线榜空 | 确认日批 ⑧ 已跑、`stock_read_grants.sql` 已执行（§八.5） |
| 量化主线 Top 为空 | 确认 ⑪ `run_dws_dc_industry_quant_mainline`；配置 `content_types=行业,概念` |
| AI 核心池页空 | 确认 ⑨b 已跑；`ai_score_di` 有数但 `core_di` 为 0 属正常（未达入池分） |
| Web 无法访问 | 检查 uvicorn 进程、端口 8082、安全组（启动见 §八.2） |
| uvicorn 端口占用 | 换 `--port 8083` 或 `pkill -f "uvicorn app.main:app"` 后重启 |
