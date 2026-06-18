# stock_data — XXL-JOB 调度执行顺序

> 维护日期：2026-06-18  
> 项目路径（服务器）：`/root/stock_data`  
> 执行前统一：`cd /root/stock_data && source dw-utils/func.sh`

**XXL-JOB 建议**

- 任务类型：BEAN / GLUE(Shell) 均可，将下方「日批脚本」整段粘贴为执行体
- 调度参数：可传 `${n_date}`，不传则默认当天 `YYYYMMDD`
- 建议 Cron：交易日 **22:30**（收盘后 Tushare / 东财热榜数据较全）
- 失败告警：依赖 exit code；`run_ods_data_check` 返回 1 表示 ODS 有缺口

**相关文档**：[调度执行流程.md](调度执行流程.md)、[需求4-AI板块成分股识别-技术文档.md](需求整理/需求4-AI板块成分股识别-技术文档.md)

---

## 一、任务拆分建议

XXL-JOB 管理台可建多个 Job，也可合并为单个日批（见第三节）。

| Job 名称 | Cron 示例 | 说明 |
|----------|-----------|------|
| `stock_ods_daily` | `0 30 22 * * 1-5` | ODS 全量同步（见第二节步骤 ①） |
| `stock_dwm_dws_daily` | `0 45 22 * * 1-5` | DWM + DWS（依赖 ODS 完成） |
| `stock_dim_dragon` | `0 0 23 * * 1-5` | 板块龙头 + AI 赛道 DIM（依赖 DWM 热度） |
| `stock_ods_monitor` | `0 30 23 * * 1-5` | ODS 数据监控告警 |
| `stock_ods_monthly` | `0 0 2 1 * *` | 每月 1 号凌晨：公司信息 / mainbz 补全 |
| `stock_dim_etf_weekly` | `0 0 3 * * 1` | 每周一：行业-ETF 映射（可选） |

---

## 二、日批标准顺序

有依赖，请勿乱序。

| 步骤 | 任务 | 依赖 |
|------|------|------|
| ① | `run_data_sync` | `daily` / `daily_basic` / `moneyflow` / `dc_*` / `ths_*` / `report_rc` / `fina_indicator_vip` / `limit_list_d` / `index_daily` / `etf_*` 等；`monthly` 任务（`stock_company`、`fina_mainbz`）非 1 号自动跳过 |
| ② | `run_dwm_market_breadth` | `ods_stock_detail_di`、`ods_limit_list_di` |
| ③ | `run_dwm_dc_industry_fund_flow` / `run_dwm_ths_industry_fund_flow` | `ods_industry_fund_flow_di`、`ods_dc_daily_di`、`ods_stock_fund_flow_di` 等 |
| ④ | `run_dwm_dc_industry_trend_strength` / `run_dwm_ths_industry_trend_strength` | 板块日线 + `ods_index_daily_di`（沪深300） |
| ⑤ | `run_dwm_dc_industry_market_heat` / `run_dwm_ths_industry_market_heat` | `ods_dc_daily_di`、`ods_dc_member_di`、`ods_dc_hot_di`、`ods_stock_detail_di`；**需求4 `dim_industry_track` 前置** |
| ⑥ | `run_dwm_dc_industry_diffusion` / `run_dwm_ths_industry_diffusion` / `run_dwm_sw_industry_diffusion` | `ods_dc_member_di`、`ods_limit_list_di`、市场广度 |
| ⑦ | `run_dwm_dc_industry_prosperity` / `run_dwm_ths_industry_prosperity` / `run_dwm_sw_industry_prosperity` | 成分表 + `ods_fina_indicator` + `ods_report_rc_di` |
| ⑧ | `run_dws_*_mainline_score` + `run_dws_*_mainline_monitor` | 上述全部 DWM |
| ⑨ | `run_dim_industry_track` | ⑤ 市场热度 DWM + `ods_dc_member_di`（需求4） |
| ⑩ | `run_sector_dragon_batch` | `ods_dc_member_di`、`dwm_dc_industry_fund_flow_di`、`daily`、`moneyflow`（需求2）；可与 ⑨ 并行 |
| ⑪ | `run_ods_data_check` | — |

---

## 三、日批一键脚本（推荐）

复制到 XXL-JOB GLUE Shell，或保存为 `dw-utils/xxl_daily_batch.sh` 执行。

```bash
#!/bin/bash
set -euo pipefail

cd /root/stock_data
source dw-utils/func.sh

# XXL-JOB 可传入业务日；无参则用今天
n_date="${1:-$(date +%Y%m%d)}"

# 非交易日跳过（与 sync_data.py 一致）
if [[ "$(trade_day_flag "${n_date}")" != "1" ]]; then
  echo "SKIP: ${n_date} 非交易日 (ods_trading_day)"
  exit 0
fi

echo "======== stock_data 日批开始 ${n_date} $(date '+%F %T') ========"

# --- 1) ODS ---
run_data_sync "${n_date}"

# --- 2) DWM：广度 ---
run_dwm_market_breadth "${n_date}"

# --- 3) DWM：资金强度 ---
run_dwm_dc_industry_fund_flow "${n_date}"
run_dwm_ths_industry_fund_flow "${n_date}"

# --- 4) DWM：趋势强度 ---
run_dwm_dc_industry_trend_strength "${n_date}"
run_dwm_ths_industry_trend_strength "${n_date}"

# --- 5) DWM：市场热度（需求4 DIM 前置）---
run_dwm_dc_industry_market_heat "${n_date}"
run_dwm_ths_industry_market_heat "${n_date}"

# --- 6) DWM：扩散效应 ---
run_dwm_dc_industry_diffusion "${n_date}"
run_dwm_ths_industry_diffusion "${n_date}"
run_dwm_sw_industry_diffusion "${n_date}"

# --- 7) DWM：产业景气 ---
run_dwm_dc_industry_prosperity "${n_date}"
run_dwm_ths_industry_prosperity "${n_date}"
run_dwm_sw_industry_prosperity "${n_date}"

# --- 8) DWS：主线评分 + 监控 ---
run_dws_dc_industry_mainline_score "${n_date}"
run_dws_ths_industry_mainline_score "${n_date}"
run_dws_sw_industry_mainline_score "${n_date}"
run_dws_dc_industry_mainline_monitor "${n_date}"
run_dws_ths_industry_mainline_monitor "${n_date}"
run_dws_sw_industry_mainline_monitor "${n_date}"

# --- 9) DIM：东财热度赛道 + 成分（需求4）---
# 环境变量可选：AI_CORE_TRACK_TOP_N=50  AI_CORE_TRACK_CONTENT_TYPES=概念,行业
run_dim_industry_track "${n_date}"

# --- 10) 板块龙头 MVP（需求2，默认 行业+概念）---
run_sector_dragon_batch "${n_date}"

# --- 11) ODS 监控（有缺口 exit 1，便于 XXL-JOB 告警）---
run_ods_data_check "${n_date}"

echo "======== stock_data 日批完成 ${n_date} $(date '+%F %T') ========"
```

---

## 四、月批脚本

`stock_company`、`fina_mainbz` 在 `db_sync_task` 中为 `schedule_type=monthly`。日批 `run_data_sync` 在非 1 号会跳过；本 Job 用 `--force` 显式执行。

```bash
#!/bin/bash
set -euo pipefail
cd /root/stock_data
source dw-utils/func.sh

n_date="${1:-$(date +%Y%m%d)}"

echo "======== stock_data 月批 ${n_date} ========"

run_data_sync "${n_date}" --source-table stock_company --force
run_data_sync "${n_date}" --source-table fina_mainbz_vip --force
# fina_mainbz 按股补 VIP 截断缺失，耗时长，建议单独夜间跑
run_data_sync "${n_date}" --source-table fina_mainbz --force

echo "======== 月批完成 ========"
```

---

## 五、周批脚本（可选）

```bash
#!/bin/bash
set -euo pipefail
cd /root/stock_data
source dw-utils/func.sh

n_date="${1:-$(date +%Y%m%d)}"
run_dim_industry_etf_map "${n_date}"
```

---

## 六、排障 / 补跑

```bash
# 只同步 ODS 某一表
run_data_sync 20260616 --source-table daily_basic --force

# ODS 区间补数（按 ods_trading_day 逐日）
run_data_sync 20250101 --end-date 20260615 --source-table daily_basic --force
# 或
run_data_sync_range 20250101 20260615 --source-table daily_basic --force

# 只跑板块龙头（ODS 已齐）
run_sector_dragon_batch 20260616

# 只刷新 AI 赛道 DIM（热度 DWM 已跑）
run_dim_industry_track 20260616

# DWM 历史区间（ODS 先补好）
bash dw-dwm/pro_dwm_dc_industry_market_heat_di.sh 20250101 20260615
```

---

## 七、各步骤是否必须？

| 步骤 | 必须？ | 说明 |
|------|--------|------|
| `run_data_sync` | 是* | 下游 DWM 都依赖当日 ODS；*热榜 `dc_hot`/`ths_hot` 建议 22:30 后 |
| DWM / DWS 主线 | 视产品 | 不做主线板块页面可不跑 DWS |
| `run_dim_industry_track` | 需求4要 | 不做 AI 核心池可不跑 |
| `run_sector_dragon_batch` | 需求2要 | 不做板块龙头页可不跑 |
| `run_ods_data_check` | 建议 | 生产环境用于告警 |

需求4 AI ETL（`run_ai_core_pool_batch`）尚未实现，上线后插在 `run_dim_industry_track` 之后、`run_ods_data_check` 之前。

---

## 八、新增 ODS 表备忘（2026-06 起）

| source_table | target_table | 调度 | 用途 |
|--------------|--------------|------|------|
| `daily_basic` | `ods_daily_basic_di` | daily | 市值 / 换手率 / PE，需求4 V1 权重 |
| `stock_company` | `ods_stock_company_di` | monthly | 公司简介 / 主营，需求4 Prompt |
| `fina_mainbz_vip` | `ods_fina_mainbz_di` | daily | 主营业务构成 VIP（单次约 1 万行上限） |
| `fina_mainbz` | `ods_fina_mainbz_di` | monthly | 按股补全 mainbz 缺失 |
