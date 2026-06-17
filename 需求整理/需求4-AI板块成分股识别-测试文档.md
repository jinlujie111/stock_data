# 需求4：AI 板块成分股识别 — 测试文档

> 版本：v1.0  
> 更新日期：2026-06-16  
> 适用范围：MVP 阶段  
> 关联文档：《需求4-AI板块成分股识别-需求文档》《需求4-AI板块成分股识别-技术文档》

---

## 1. 测试目的

对**固定测试日**执行 DIM 配置检查、ODS 覆盖、AI 批处理、规则剔除、核心池权重与 API，验证：

1. 赛道维表与候选股配置正确  
2. AI 输出 JSON 可解析且字段完整  
3. 概念股剔除与 S/A/B/C 分级符合需求  
4. 核心池数量与权重计算正确  
5. 任务可重复执行（幂等 UPSERT）

---

## 2. 测试环境与固定参数

### 2.1 环境

| 项 | 说明 |
|----|------|
| 数据库 | `stock_data` |
| 连接 | `source dw-utils/func.sh` 后 `data_mysql` |
| ETL 命令 | `run_ai_core_pool_batch <YYYYMMDD>`（待实现） |
| LLM | 测试环境需配置有效 `model_name` 与 API Key |

### 2.2 固定测试日

```text
@T   = 2026-06-16
@T8  = 20260616
```

### 2.3 固定抽测赛道与股票（MVP 样例）

| 角色 | industry_id | industry_name | ts_code | stock_name | 预期 |
|------|-------------|---------------|---------|------------|------|
| 正向样本 | `TRACK_STORAGE` | 存储芯片 | `301308.SZ` | 江波龙 | match=true, score≥80, level∈{S,A} |
| 正向样本 | `TRACK_STORAGE` | 存储芯片 | `688525.SH` | 佰维存储 | match=true, score≥75 |
| 边缘样本 | `TRACK_STORAGE` | 存储芯片 | 某跨界股 | — | score 60~79 或剔除 |
| 负向样本 | `TRACK_STORAGE` | 存储芯片 | 某纯概念 | — | match=false 或 score≤20，不进核心池 |
| 第二赛道 | `TRACK_ROBOT` | 机器人 | `002472.SZ` | 双环传动 | match=true |

实施前将 `industry_id` 与实库 `dim_industry_track` 对齐后填入定表。

---

## 3. 测试前准备（P0）

| 编号 | 步骤 | 预期 |
|------|------|------|
| P0-1 | 执行 DDL：`dim_industry_track`、`dim_industry_track_stock`、`ai_core_pool_config`、DWM 结果表 | 表存在 |
| P0-2 | 导入首期 ≥2 条赛道、每赛道 ≥5 只候选股 | `dim_industry_track.status=1` |
| P0-3 | `run_data_sync @T8` 成功 | `ods_report_rc_di`、`ods_fina_indicator` 有数据 |
| P0-4 | LLM 配置可用（`ai_core_pool_config.is_active=1`） | 单股试调用返回 JSON |
| P0-5 | `run_ai_core_pool_batch @T8 --mode full`（或等价命令） | 日志无批量失败 |

---

## 4. 维表与配置测试（P1）

### 4.1 赛道与候选股

```sql
SET @T = '2026-06-16';

-- A. 启用赛道数
SELECT COUNT(*) AS track_cnt
FROM dim_industry_track
WHERE status = 1;
-- MVP 预期：≥ 2（测试）；上线 ≥ 50

-- B. 候选股覆盖
SELECT t.industry_name,
       COUNT(*) AS candidate_cnt
FROM dim_industry_track_stock s
JOIN dim_industry_track t ON t.industry_id = s.industry_id
WHERE t.status = 1 AND s.is_active = 1
GROUP BY t.industry_name
ORDER BY candidate_cnt DESC;
-- 预期：每赛道 candidate_cnt ≥ 5；全库合计向 1000~2000 规模扩展

-- C. 代码规范
SELECT ts_code FROM dim_industry_track_stock
WHERE ts_code NOT REGEXP '^[0-9]{6}\\.(SH|SZ|BJ)$';
-- 预期：0 行
```

**通过标准（AC-DIM）**：无非法 `ts_code`；启用赛道与候选股与测试计划一致。

### 4.2 AI 配置

```sql
SELECT model_name, prompt_version, score_threshold, reject_score, mainbz_min_pct, is_active
FROM ai_core_pool_config
WHERE config_key = '__global__' AND is_active = 1
ORDER BY effective_date DESC
LIMIT 1;
-- 预期：score_threshold=60, reject_score=20, mainbz_min_pct=10
```

---

## 5. ODS 依赖测试（P1）

```sql
SET @T = '2026-06-16';

-- A. 研报（Prompt 摘要来源）
SELECT COUNT(*) AS rc_cnt
FROM ods_report_rc_di
WHERE report_date BETWEEN DATE_SUB(@T, INTERVAL 90 DAY) AND @T;
-- 预期：> 0

-- B. 财务指标
SELECT COUNT(*) AS fina_cnt FROM ods_fina_indicator;
-- 预期：> 5000

-- C. 公司资料（MVP 可选）
SELECT COUNT(*) AS company_cnt FROM ods_stock_company_di;
-- 未建表则跳过；建表后 > 4000

-- D. 分部收入（R-1 规则，MVP 可选）
SELECT COUNT(*) AS mainbz_cnt FROM ods_fina_mainbz_di;
-- 未建表则 R-1 用例标记 N/A
```

**通过标准（AC-ODS）**：A、B 必有数据；C、D 为增强项，缺失时仅测 R-2/R-3 剔除逻辑。

---

## 6. AI 评分结果测试（P2）

### 6.1 结果表覆盖

```sql
SET @T = '2026-06-16';

SELECT industry_name,
       COUNT(*) AS score_cnt,
       SUM(industry_match = 1) AS match_cnt,
       ROUND(AVG(score), 1) AS avg_score,
       SUM(level = 'S') AS s_cnt,
       SUM(level = 'A') AS a_cnt,
       SUM(level = 'B') AS b_cnt,
       SUM(level = 'C') AS c_cnt
FROM dwm_industry_stock_ai_score_di
WHERE trade_date = @T
GROUP BY industry_name;
-- 预期：score_cnt ≈ 候选股数；match_cnt > 0；level 与 score 区间一致
```

### 6.2 分级区间一致性

```sql
SET @T = '2026-06-16';

SELECT ts_code, industry_name, score, level
FROM dwm_industry_stock_ai_score_di
WHERE trade_date = @T
  AND (
    (level = 'S' AND (score < 90 OR score > 100))
    OR (level = 'A' AND (score < 80 OR score >= 90))
    OR (level = 'B' AND (score < 60 OR score >= 80))
    OR (level = 'C' AND score >= 60)
  );
-- 预期：0 行
```

### 6.3 JSON 字段完整性

```sql
SET @T = '2026-06-16';

SELECT COUNT(*) AS bad_json
FROM dwm_industry_stock_ai_score_di
WHERE trade_date = @T
  AND (
    raw_json IS NULL
    OR JSON_EXTRACT(raw_json, '$.industry_match') IS NULL
    OR JSON_EXTRACT(raw_json, '$.score') IS NULL
    OR reason IS NULL OR TRIM(reason) = ''
  );
-- 预期：0 行（允许少量失败行标记 score IS NULL，需补跑队列）
```

### 6.4 固定样本点检

```sql
SET @T = '2026-06-16';

SELECT industry_name, ts_code, stock_name, industry_match, score, level,
       LEFT(reason, 80) AS reason_preview
FROM dwm_industry_stock_ai_score_di
WHERE trade_date = @T
  AND ts_code IN ('301308.SZ', '688525.SH', '002472.SZ');
-- 人工核对：江波龙/佰维存储/双环传动 reason 与产业逻辑相符
```

**通过标准（AC-SCORE）**：§6.2 为 0 行；固定样本 match 与分数在合理区间。

---

## 7. 核心池与剔除规则测试（P2）

### 7.1 剔除规则

```sql
SET @T = '2026-06-16';

-- 不应出现在核心池：不匹配
SELECT c.*
FROM dwm_industry_stock_core_di c
JOIN dwm_industry_stock_ai_score_di s
  ON c.trade_date = s.trade_date
 AND c.industry_id = s.industry_id
 AND c.ts_code = s.ts_code
WHERE c.trade_date = @T
  AND (s.industry_match = 0 OR s.score <= 20 OR s.score < 60);
-- 预期：0 行

-- 评分表中的 C 级不应进核心池
SELECT c.ts_code
FROM dwm_industry_stock_core_di c
JOIN dwm_industry_stock_ai_score_di s
  ON c.trade_date = s.trade_date AND c.industry_id = s.industry_id AND c.ts_code = s.ts_code
WHERE c.trade_date = @T AND s.level = 'C';
-- 预期：0 行
```

### 7.2 权重归一化（MVP）

```sql
SET @T = '2026-06-16';
SET @IND = 'TRACK_STORAGE';  -- 替换为实库 industry_id

SELECT industry_name,
       COUNT(*) AS core_cnt,
       ROUND(SUM(weight), 4) AS weight_sum,
       MIN(weight) AS min_w,
       MAX(weight) AS max_w
FROM dwm_industry_stock_core_di
WHERE trade_date = @T AND industry_id = @IND
GROUP BY industry_name;
-- 预期：weight_sum ≈ 1.0000（±0.0001）；core_cnt ≥ 1

-- 权重与分数单调性：score 越高 weight 不应系统性更低（抽样）
SELECT ts_code, score, weight
FROM dwm_industry_stock_core_di
WHERE trade_date = @T AND industry_id = @IND
ORDER BY score DESC
LIMIT 5;
-- 预期：weight 大致与 score 同序
```

### 7.3 全库规模

```sql
SET @T = '2026-06-16';

SELECT COUNT(DISTINCT industry_id) AS track_cnt,
       COUNT(*) AS core_stock_rows,
       COUNT(DISTINCT ts_code) AS distinct_stocks
FROM dwm_industry_stock_core_di
WHERE trade_date = @T;
-- MVP 测试：track_cnt≥2；上线目标 distinct_stocks 约 1000~2000
```

**通过标准（AC-POOL）**：§7.1 均为 0 行；§7.2 `weight_sum≈1`。

---

## 8. 幂等与重跑测试（P3）

| 编号 | 步骤 | 预期 |
|------|------|------|
| P3-1 | 连续执行 2 次 `run_ai_core_pool_batch @T8` | 行数不变，无重复主键 |
| P3-2 | 对比两次 `score`/`level` | 同模型同 Prompt 下差异率 <5%（LLM 有随机性时可放宽并记录） |
| P3-3 | 故意删除某赛道 1 条 core 行后重跑 | 该条被恢复 |

```sql
-- 重复行检查
SELECT trade_date, industry_id, ts_code, COUNT(*) AS cnt
FROM dwm_industry_stock_ai_score_di
WHERE trade_date = @T
GROUP BY 1,2,3 HAVING cnt > 1;
-- 预期：0 行
```

---

## 9. API 测试（P3，待接口实现）

### 9.1 POST `/api/v1/ai-core/analyze`

```bash
curl -s -X POST "http://<host>:8082/api/v1/ai-core/analyze" \
  -H "Content-Type: application/json" \
  -d '{"industry_id":"TRACK_STORAGE","ts_code":"301308.SZ","trade_date":"2026-06-16"}'
```

**预期**：HTTP 200；body 含 `industry_match`、`score`、`level`、`reason`。

### 9.2 GET `/api/v1/ai-core/pool`

```bash
curl -s "http://<host>:8082/api/v1/ai-core/pool?trade_date=2026-06-16&industry_id=TRACK_STORAGE&level=S"
```

**预期**：仅返回 S 级；字段与库表一致。

---

## 10. 手工用例（MVP）

| 用例 ID | 输入 | 操作 | 预期 |
|---------|------|------|------|
| M-01 | 存储芯片 + 江波龙 | 单股分析 | match=true, segment 含「模组/存储」, score≥80 |
| M-02 | 存储芯片 + 明显无关股 | 单股分析 | match=false 或 score≤20 |
| M-03 | 机器人赛道全量批 | full 批处理 | 核心池≥3 只，含双环传动/绿的谐波等 |
| M-04 | 修改 `reject_score=30` 后重跑 | 配置生效 | 20~30 分股票从核心池剔除 |
| M-05 | ODS 无研报股票 | 分析 | 仍返回 JSON，reason 注明资料不足 |

---

## 11. 缺陷分级与通过门槛

| 级别 | 定义 | MVP 是否阻断上线 |
|------|------|------------------|
| P0 | 批处理失败、核心池全空、分级规则错误 | 是 |
| P1 | 单赛道缺候选、ODS 缺研报 | 否（可缩小范围） |
| P2 | reason 文案质量差、分数偏差 | 否（迭代 Prompt） |
| P3 | API 字段命名与文档不一致 | 视产品而定 |

**MVP 通过门槛**：P0 全通过；P1 中 ODS 研报/财务必过；§6.2、§7.1、§7.2  SQL 全绿；固定样本 M-01/M-03 人工通过。

---

## 12. 文档修订记录

| 版本 | 日期 | 说明 |
|------|------|------|
| v1.0 | 2026-06-16 | 初版：维表、ODS、评分、核心池、API、幂等测试用例 |
