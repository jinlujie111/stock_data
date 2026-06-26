# stock_data — XXL-JOB 调度执行顺序

> 维护日期：2026-06-18  
> 项目路径（服务器）：`/root/stock_data`  
> 执行前统一：`cd /root/stock_data && source dw-utils/func.sh`

**XXL-JOB 建议**

- 任务类型：BEAN / GLUE(Shell) 均可；推荐直接调用仓库脚本（见第三节）
- 调度参数：可传 `${n_date}`（`YYYYMMDD`），不传则默认当天
- 建议 Cron：交易日 **22:30**（收盘后 Tushare / 东财热榜数据较全）
- 失败告警：依赖 exit code；`run_ods_data_check` 返回 1 表示 ODS 有缺口
- Web 展示默认端口：**8082**（`industry_fund_flow`，避免与 XXL-JOB 8080 冲突）

**相关文档**

- [调度执行流程.md](调度执行流程.md) — ODS / DWM / DWS 手工命令
- [需求1-主线板块确认-需求文档.md](需求整理/需求1-主线板块确认-需求文档.md) — 主线榜业务与验收
- [需求4-AI板块成分股识别-技术文档.md](需求整理/需求4-AI板块成分股识别-技术文档.md)

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
| ① | `run_data_sync` | `daily` / `daily_basic` / `moneyflow` / `dc_*` / `ths_*` / `report_rc` / `fina_indicator_vip` / `limit_list_d` / `index_daily` / `etf_*` 等；`monthly`（`stock_company`、`fina_mainbz`）非 1 号自动跳过 | 全部 |
| ② | `run_dwm_market_breadth` | `ods_stock_detail_di`、`ods_limit_list_di` | 首页广度 |
| ③ | `run_dwm_dc_industry_fund_flow` / `run_dwm_ths_industry_fund_flow` | 板块资金流 ODS | 需求1 五维 |
| ④ | `run_dwm_dc_industry_trend_strength` / `run_dwm_ths_industry_trend_strength` | 板块日线 + `ods_index_daily_di` | 需求1 五维 |
| ⑤ | `run_dwm_dc_industry_market_heat` / `run_dwm_ths_industry_market_heat` | `ods_dc_*` / 热榜；**需求4 `dim_industry_track` 前置** | 需求1 / 需求4 |
| ⑥ | `run_dwm_dc_industry_diffusion` / `run_dwm_ths_industry_diffusion` / `run_dwm_sw_industry_diffusion` | 成分 + 涨停 + 广度 | 需求1 五维 |
| ⑦ | `run_dwm_dc_industry_prosperity` / `run_dwm_ths_industry_prosperity` / `run_dwm_sw_industry_prosperity` | 成分 + `ods_fina_indicator` + `ods_report_rc_di` | 需求1 五维 |
| ⑧ | `run_dws_*_mainline_score` + `run_dws_*_mainline_monitor` | 上述全部 DWM | **需求1 主线榜** |
| ⑨ | `run_dim_industry_track` | ⑤ 市场热度 DWM | 需求4 |
| ⑩ | `run_sector_dragon_batch` | 资金 DWM + `daily` / `moneyflow` | 需求2 |
| ⑪ | `run_dws_dc_industry_quant_mainline` | 全部东财 DWM + 龙头摘要 | **需求3 量化主线（东财行业）** |
| ⑫ | `run_ods_data_check` | — | 监控告警 |

**需求3 落库表（步骤 ⑪）**

| 表 | 说明 |
|----|------|
| `dws_dc_industry_quant_mainline_di` | FTELP 五主因子、MainScore、Top3、MA3/5/10 |
| `dws_dc_industry_quant_mainline_signal_di` | 启动 / 退潮 / 观察 + 原因 JSON |
| `quant_mainline_config` | 权重与信号阈值（默认 `content_types=行业,概念`） |

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
cd /root/stock_data
bash dw-utils/xxl_daily_batch.sh          # 今天
bash dw-utils/xxl_daily_batch.sh 20260616 # 指定业务日
```

**XXL-JOB GLUE Shell 执行体**（等价）：

```bash
#!/bin/bash
set -euo pipefail
cd /root/stock_data
bash dw-utils/xxl_daily_batch.sh "${1:-$(date +%Y%m%d)}"
```

脚本全文见 [`dw-utils/xxl_daily_batch.sh`](dw-utils/xxl_daily_batch.sh)。

---

## 四、月批脚本

`stock_company`、`fina_mainbz` 在 `db_sync_task` 中为 `schedule_type=monthly`。日批 `run_data_sync` 在非 1 号会跳过；本 Job 用 `--force` 显式执行。

```bash
cd /root/stock_data
bash dw-utils/xxl_monthly_batch.sh
# 或指定日期
bash dw-utils/xxl_monthly_batch.sh 20260601
```

脚本见 [`dw-utils/xxl_monthly_batch.sh`](dw-utils/xxl_monthly_batch.sh)。

---

## 五、周批脚本（可选，建议开启）

用于刷新 `dim_industry_etf_map`（自动 `index_match`），支撑需求1 **机构化**阶段判定；**不依赖手工维护**，手工 `manual` 映射仅作补强。

```bash
cd /root/stock_data
bash dw-utils/xxl_weekly_batch.sh
```

脚本见 [`dw-utils/xxl_weekly_batch.sh`](dw-utils/xxl_weekly_batch.sh)。

---

## 六、排障 / 补跑

```bash
cd /root/stock_data && source dw-utils/func.sh

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
| `run_sector_dragon_batch` | 需求2 要 | 不做板块龙头页可不跑 |
| `xxl_weekly_batch` | 建议 | 提升「机构化」命中率；无则仍可出榜 |
| `run_ods_data_check` | 建议 | 生产环境告警 |

需求4 AI ETL（`run_ai_core_pool_batch`）尚未实现，上线后插在 `run_dim_industry_track` 之后、`run_ods_data_check` 之前。

---

## 八、Web / API 上线（需求1）

日批 ⑧ 完成后，Web 读 `dws_dc_industry_mainline_monitor_di`。

```bash
# 1) 授权（root 执行一次）
mysql -u root -p < industry_fund_flow/sql/stock_read_grants.sql

# 2) 启动（默认 8082）
cd industry_fund_flow
source ../dw-utils/func.sh   # 导出 IFF_* / STOCK_* 环境变量
uvicorn app.main:app --host 0.0.0.0 --port 8082
```

| 入口 | 路径 |
|------|------|
| 主线榜页面 | `http://<host>:8082/dc/mainline` |
| 主线榜 API | `GET /api/v1/mainline/rank?trade_date=YYYYMMDD&top=20&ma_window=5` |
| 兼容 API | `GET /api/rank/mainline?trade_date=YYYYMMDD` |
| 历史得分 | `GET /api/v1/mainline/history?industry_code=BKxxxx.DC&days=60` |

登录后 Cookie 名为 **`iff_token`**。浏览器已登录可直接访问 API；命令行见需求文档 §测试或下文 §九。

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

**API 快速测**（先登录拿 Cookie）：

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
| `fina_mainbz_vip` | `ods_fina_mainbz_di` | daily | 主营业务构成 VIP（单次约 1 万行上限） |
| `fina_mainbz` | `ods_fina_mainbz_di` | monthly | 按股补全 mainbz 缺失 |

---

## 十一、仓库脚本索引

| 文件 | 说明 |
|------|------|
| [`dw-utils/xxl_daily_batch.sh`](dw-utils/xxl_daily_batch.sh) | 日批一键 |
| [`dw-utils/xxl_monthly_batch.sh`](dw-utils/xxl_monthly_batch.sh) | 月批 |
| [`dw-utils/xxl_weekly_batch.sh`](dw-utils/xxl_weekly_batch.sh) | 周批 ETF 映射 |
| [`dw-utils/xxl_mainline_batch.sh`](dw-utils/xxl_mainline_batch.sh) | 仅需求1 补跑 |
| [`industry_fund_flow/sql/stock_read_grants.sql`](industry_fund_flow/sql/stock_read_grants.sql) | Web 只读授权 |
