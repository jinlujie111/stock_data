# 需求4：AI 板块成分股识别 — 技术文档

> 版本：v1.0  
> 更新日期：2026-06-16  
> 关联：《需求4-AI板块成分股识别-需求文档》

---

## 1. 系统架构

```mermaid
flowchart TB
    subgraph ingest [数据采集层]
        TS[Tushare / 公告源]
        SYNC[dw-sync / run_data_sync]
    end
    subgraph ods [ODS 明细层]
        O1[ods_stock_company_di 待建]
        O2[ods_fina_mainbz_di 待建]
        O3[ods_fina_indicator 已有]
        O4[ods_report_rc_di 已有]
        O5[ods_stock_detail_di 已有]
        O6[ods_dc_member_di 可选初筛]
    end
    subgraph dim [DIM 维表]
        D1[dim_industry_track]
        D2[dim_industry_track_stock 候选池]
        D3[ai_core_pool_config]
    end
    subgraph etl [AI ETL 层]
        COLLECT[资料聚合 collect_context]
        AI[LLM 分析 ai_analyze]
        RULE[规则引擎 apply_rules]
        POOL[核心池 build_core_pool]
    end
    subgraph dm [结果层]
        S1[dwm_industry_stock_ai_score_di]
        S2[dwm_industry_stock_core_di]
    end
    subgraph app [应用层]
        API[REST API]
        JOB[XXL-JOB run_ai_core_pool_batch]
        WEB[Web 核心池页 待建]
    end
    TS --> SYNC --> ods
    dim --> COLLECT
    ods --> COLLECT
    COLLECT --> AI --> RULE --> POOL
    POOL --> dm
    dm --> API
    dm --> WEB
    JOB --> etl
```

**与需求2 的差异**：需求2 对东财**全板块**做规则因子评分；本需求对 **dim 精选赛道** 调用 **LLM** 做语义归属，候选股可来自人工维护或东财板块弱关联初筛。

---

## 2. 数据分层

| 层级 | 内容 | 本需求用途 |
|------|------|------------|
| DIM | 赛道定义、候选股、AI 配置 | 分析范围与 Prompt 版本 |
| ODS | 公司资料、财报分部、研报 | LLM 输入上下文 |
| DWM | AI 评分、核心池 | 对外查询与组合权重 |
| APP | API / Web | 展示与人工复核 |

---

## 3. 核心表设计

### 3.1 DIM：`dim_industry_track`

```sql
CREATE TABLE IF NOT EXISTS dim_industry_track (
    industry_id       VARCHAR(32)  NOT NULL COMMENT '赛道ID',
    industry_name     VARCHAR(128) NOT NULL COMMENT '赛道名称',
    parent_industry_id VARCHAR(32) NULL COMMENT '上级赛道',
    level             TINYINT      NOT NULL DEFAULT 1 COMMENT '1=一级 2=二级',
    status            TINYINT      NOT NULL DEFAULT 1 COMMENT '1启用 0停用',
    dc_board_code     VARCHAR(32)  NULL COMMENT '关联东财板块BK代码(可选)',
    sort_order        INT          NOT NULL DEFAULT 0,
    remark            VARCHAR(512) NULL,
    created_at        DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at        DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (industry_id),
    UNIQUE KEY uk_track_name (industry_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='AI核心池-赛道维表';
```

### 3.2 DIM：`dim_industry_track_stock`（候选池）

```sql
CREATE TABLE IF NOT EXISTS dim_industry_track_stock (
    id            BIGINT PRIMARY KEY AUTO_INCREMENT,
    industry_id   VARCHAR(32)  NOT NULL,
    ts_code       VARCHAR(16)  NOT NULL,
    stock_name    VARCHAR(64)  NULL,
    source        VARCHAR(32)  NOT NULL DEFAULT 'manual' COMMENT 'manual|dc_member|history_core',
    is_active     TINYINT      NOT NULL DEFAULT 1,
    created_at    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_track_stock (industry_id, ts_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='赛道候选股(分析输入范围)';
```

### 3.3 配置：`ai_core_pool_config`

```sql
CREATE TABLE IF NOT EXISTS ai_core_pool_config (
    id              BIGINT PRIMARY KEY AUTO_INCREMENT,
    config_key      VARCHAR(64)  NOT NULL DEFAULT '__global__',
    model_name      VARCHAR(64)  NOT NULL DEFAULT 'gpt-4o-mini',
    prompt_version  VARCHAR(16)  NOT NULL DEFAULT 'v1',
    temperature     DECIMAL(3,2) NOT NULL DEFAULT 0.20,
    max_tokens      INT          NOT NULL DEFAULT 1024,
    score_threshold INT          NOT NULL DEFAULT 60 COMMENT '入核心池最低分',
    reject_score    INT          NOT NULL DEFAULT 20 COMMENT '概念股剔除线',
    mainbz_min_pct  DECIMAL(5,2) NOT NULL DEFAULT 10.00 COMMENT '主业占比下限%',
    batch_size      INT          NOT NULL DEFAULT 10,
    rate_limit_rpm  INT          NOT NULL DEFAULT 60,
    effective_date  DATE         NOT NULL,
    is_active       TINYINT      NOT NULL DEFAULT 1,
    created_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_ai_core_config (config_key, effective_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='AI核心池全局配置';
```

### 3.4 结果：`dwm_industry_stock_ai_score_di`

```sql
CREATE TABLE IF NOT EXISTS dwm_industry_stock_ai_score_di (
    id              BIGINT PRIMARY KEY AUTO_INCREMENT,
    trade_date      DATE         NOT NULL,
    industry_id     VARCHAR(32)  NOT NULL,
    industry_name   VARCHAR(128) NOT NULL,
    ts_code         VARCHAR(16)  NOT NULL,
    stock_name      VARCHAR(64)  NULL,
    industry_match  TINYINT      NOT NULL DEFAULT 0,
    segment         VARCHAR(64)  NULL,
    core_degree     VARCHAR(16)  NULL,
    score           DECIMAL(5,2) NULL,
    level           CHAR(1)      NULL COMMENT 'S/A/B/C',
    reason          TEXT         NULL,
    model_name      VARCHAR(64)  NULL,
    prompt_version  VARCHAR(16)  NULL,
    raw_json        JSON         NULL,
    created_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_ai_score (trade_date, industry_id, ts_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='AI赛道归属评分(全量留痕)';
```

### 3.5 结果：`dwm_industry_stock_core_di`

```sql
CREATE TABLE IF NOT EXISTS dwm_industry_stock_core_di (
    id            BIGINT PRIMARY KEY AUTO_INCREMENT,
    trade_date    DATE         NOT NULL,
    industry_id   VARCHAR(32)  NOT NULL,
    industry_name VARCHAR(128) NOT NULL,
    ts_code       VARCHAR(16)  NOT NULL,
    stock_name    VARCHAR(64)  NULL,
    score         DECIMAL(5,2) NOT NULL,
    level         CHAR(1)      NOT NULL COMMENT 'S/A/B',
    weight        DECIMAL(10,6) NULL COMMENT '赛道内归一化权重',
    segment       VARCHAR(64)  NULL,
    updated_at    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_core_pool (trade_date, industry_id, ts_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='AI核心池(剔除后)';
```

---

## 4. ODS 依赖与同步任务

### 4.1 已有（可直接用）

| ODS 表 | 用途 |
|--------|------|
| `ods_report_rc_di` | 近 90 日研报标题/评级/预测，拼 `report_summary` |
| `ods_fina_indicator` | 营收、净利、ROE 等财务概览 |
| `ods_stock_detail_di` | 市值、成交额（V1 权重） |
| `ods_dc_member_di` | 可选：由 `dc_board_code` 拉候选股 |

### 4.2 待建（MVP 建议优先）

| ODS 表 | Tushare 接口 | 用途 |
|--------|--------------|------|
| `ods_stock_company_di` | `stock_company` | 公司简介、主营业务 |
| `ods_fina_mainbz_di` | `fina_mainbz` | 分部收入 → 主业占比 R-1 |

在 ODS 未就绪前，MVP 可仅用 **研报 + fina_indicator 字段 + 人工维护的 track 候选股** 跑通链路；`mainbz_min_pct` 规则暂不生效。

### 4.3 db_sync_task 规划

在 `data_config.db_sync_task` 追加（`status=1`）：

```text
stock_company   → ods_stock_company_di   (sync_mode=full, 月更或周更)
fina_mainbz     → ods_fina_mainbz_di     (sync_mode=snapshot, 季报后)
```

---

## 5. AI 分析引擎

### 5.1 模块划分（规划目录）

```text
stock_data/
├── etl/ai_core_pool/
│   ├── __init__.py
│   ├── batch.py              # 批处理入口
│   ├── context.py            # 聚合 ODS → Prompt 上下文
│   ├── llm_client.py         # 模型调用、JSON 解析、重试
│   ├── rules.py              # 概念股剔除、level 映射
│   ├── core_pool.py          # 核心池 + weight
│   └── db_util.py            # DIM/DWM 读写
├── dw-dwm/
│   └── pro_dwm_ai_core_pool_di.sh
└── industry_fund_flow/app/
    ├── routes_ai_core.py     # API 待建
    └── ai_core_service.py
```

### 5.2 单股分析伪代码

```python
def analyze_one(industry: Track, stock: Stock, trade_date: date, cfg: Config) -> AiScore:
    ctx = collect_context(stock.ts_code, trade_date)  # ODS
    prompt = render_prompt(industry, stock, ctx, version=cfg.prompt_version)
    raw = llm_client.chat_json(prompt, model=cfg.model_name, temperature=cfg.temperature)
    score_row = parse_and_validate(raw)  # pydantic / jsonschema
    score_row = apply_rules(score_row, ctx, cfg)  # mainbz、reject_score
    score_row.level = score_to_level(score_row.score)
    return score_row
```

### 5.3 JSON Schema（校验）

```json
{
  "type": "object",
  "required": ["industry_match", "segment", "score", "reason"],
  "properties": {
    "industry_match": { "type": "boolean" },
    "segment": { "type": "string", "maxLength": 64 },
    "core_degree": { "type": "string" },
    "score": { "type": "number", "minimum": 0, "maximum": 100 },
    "reason": { "type": "string", "maxLength": 500 }
  }
}
```

解析失败：重试最多 2 次；仍失败写入 `raw_json` + `score=NULL`，标记任务失败供补跑。

### 5.4 Level 映射

```python
def score_to_level(score: float | None) -> str | None:
    if score is None:
        return None
    if score >= 90:
        return "S"
    if score >= 80:
        return "A"
    if score >= 60:
        return "B"
    return "C"
```

### 5.5 核心池生成

```python
def build_core_pool(scores: list[AiScore], cfg: Config) -> list[CoreRow]:
    rows = [
        s for s in scores
        if s.industry_match
        and (s.score or 0) >= cfg.score_threshold
        and (s.score or 0) > cfg.reject_score
    ]
    total = sum(s.score for s in rows)
    for s in rows:
        s.weight = round(s.score / total, 6) if total else None
    return rows
```

V1 权重合成见需求文档 §3.4，在 `core_pool.py` 扩展 `blend_weight()`。

---

## 6. 批处理与调度

### 6.1 Shell 入口

`dw-dwm/pro_dwm_ai_core_pool_di.sh`（规划）：

```bash
#!/bin/bash
# run_ai_core_pool_batch 20260616
# run_ai_core_pool_batch 20260616 --industry-id TRACK_001  # 单赛道
source dw-utils/func.sh
export PYTHONPATH="${DW_ROOT}:${DW_ROOT}/dw-utils:${PYTHONPATH}"
"${PYTHON_BIN}" -m etl.ai_core_pool.batch "${n_date}" "$@"
```

`func.sh` 封装：

```bash
run_ai_core_pool_batch() {
  bash "${DW_ROOT}/dw-dwm/pro_dwm_ai_core_pool_di.sh" "$@"
}
```

### 6.2 推荐 XXL-JOB 顺序

```bash
set -euo pipefail
cd /root/stock_data
source dw-utils/func.sh
n_date=$(date +%Y%m%d)

[[ "$(trade_day_flag "${n_date}")" == "1" ]] || exit 0

run_data_sync "${n_date}"
# … 其他 DWM（可选）…
run_ai_core_pool_batch "${n_date}"    # 本需求：建议在 ODS 同步之后
```

| 模式 | 说明 |
|------|------|
| `full` | 全赛道 × 全候选股（周度） |
| `delta` | 仅 `ann_date`/`report_date` 当日有更新的股票（日度，默认） |

### 6.3 性能与限流

| 参数 | 建议值 |
|------|--------|
| 候选股总量 | 1000~2000 |
| `batch_size` | 10 |
| `rate_limit_rpm` | 60（按模型配额调整） |
| 并发 | 单进程顺序 + 限流（避免 LLM 429） |
| 全量耗时 | 约 30~90 分钟（视模型与候选数） |

---

## 7. API 设计（草案）

### 7.1 POST `/api/v1/ai-core/analyze`

单股实时分析（投研复核用）。

**Request**

```json
{
  "industry_id": "TRACK_001",
  "ts_code": "301308.SZ",
  "trade_date": "2026-06-16"
}
```

**Response**：与 §3.1 JSON 一致，附 `level`、`model_name`。

### 7.2 GET `/api/v1/ai-core/pool`

**Query**：`trade_date`, `industry_id`, `level`（可选 S/A/B）

**Response**

```json
{
  "trade_date": "2026-06-16",
  "industry_id": "TRACK_001",
  "industry_name": "存储芯片",
  "items": [
    {
      "ts_code": "301308.SZ",
      "stock_name": "江波龙",
      "score": 95,
      "level": "S",
      "weight": 0.263,
      "segment": "存储模组",
      "reason": "..."
    }
  ]
}
```

### 7.3 GET `/api/v1/ai-core/tracks`

返回 `dim_industry_track` 树形列表及每赛道核心池数量。

---

## 8. 安全与运维

| 项 | 说明 |
|----|------|
| API Key | 模型 Key 放 `data_config` 或环境变量，禁止入库到业务表 |
| 日志 | 记录 `industry_id`、`ts_code`、`model_name`、token 用量；**不**记录完整 Prompt 中的敏感配置 |
| 幂等 | `uk_ai_score (trade_date, industry_id, ts_code)` UPSERT |
| 人工覆写 | V1：`dim_industry_track_stock` + `core_pool_override` 表（待建） |
| 回滚 | 保留 `prompt_version`；可按版本重跑历史 |

---

## 9. 与现有需求对接（V2）

| 能力 | 接入点 |
|------|--------|
| 板块龙头 | `sector_dragon_summary_di` / `dwm_sector_stock_dragon_score_di` |
| 主线评分 | `dws_dc_industry_mainline_score_di` |
| 赛道–东财映射 | `dim_industry_track.dc_board_code` → `ods_dc_member_di` 候选初筛 |

---

## 10. 文档修订记录

| 版本 | 日期 | 说明 |
|------|------|------|
| v1.0 | 2026-06-16 | 初版：表结构、ETL 模块、调度与 API 草案 |
