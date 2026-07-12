-- =============================================================================
-- VP 六维评分升级（行业+概念合并百分位）
-- 适用：已有需求5表结构的 stock_data 库
-- 执行：mysql -u... -p stock_data < mysql_tables/migrations/20260712_vp_six_dim_upgrade.sql
-- 说明：每条 ALTER 仅需执行一次；若列已存在会报错，可跳过该条继续
-- 执行后请重跑：run_vp_batch YYYYMMDD（建议近期交易日全量回溯）
-- =============================================================================

USE stock_data;

-- -----------------------------------------------------------------------------
-- 1. dwm_vp_config：新增龙头权重 + 更新六维默认权重
-- -----------------------------------------------------------------------------
ALTER TABLE dwm_vp_config
    ADD COLUMN weight_leader DECIMAL(5,4) NOT NULL DEFAULT 0.0500
        COMMENT '龙头强度权重(5%)'
        AFTER weight_breakout;

UPDATE dwm_vp_config
SET weight_vol        = 0.2000,
    weight_trend      = 0.2000,
    weight_continuity = 0.2500,
    weight_breadth    = 0.1500,
    weight_breakout   = 0.1500,
    weight_leader     = 0.0500,
    updated_at        = CURRENT_TIMESTAMP
WHERE config_key = '__global__'
  AND is_active = 1;

-- 若无配置行，插入默认（按需取消注释）
-- INSERT INTO dwm_vp_config (
--     config_key, window_default, weight_vol, weight_trend, weight_continuity,
--     weight_breadth, weight_breakout, weight_leader, effective_date, is_active
-- ) VALUES (
--     '__global__', 20, 0.2000, 0.2000, 0.2500, 0.1500, 0.1500, 0.0500, CURDATE(), 1
-- );

-- -----------------------------------------------------------------------------
-- 2. dwm_stock_vp_factor_di：严格突破标记
-- -----------------------------------------------------------------------------
ALTER TABLE dwm_stock_vp_factor_di
    ADD COLUMN is_breakout_strict TINYINT NOT NULL DEFAULT 0
        COMMENT '严格突破:60日新高+收盘>前60日最高+成交额>5日均×1.5'
        AFTER is_breakout_60;

ALTER TABLE dwm_stock_vp_factor_di
    MODIFY COLUMN is_breakout_60 TINYINT NOT NULL DEFAULT 0
        COMMENT '60日新高且放量(兼容展示/K线页)';

-- -----------------------------------------------------------------------------
-- 3. dwm_industry_vp_agg_di：六维原始指标
-- -----------------------------------------------------------------------------
ALTER TABLE dwm_industry_vp_agg_di
    ADD COLUMN continuity_strength DECIMAL(20,6) NULL
        COMMENT '连续放量强度=Σ(天数×超额×衰减)'
        AFTER amount_streak_days;

ALTER TABLE dwm_industry_vp_agg_di
    ADD COLUMN trend_return_20d DECIMAL(20,6) NULL
        COMMENT '板块指数20日收益率(%)'
        AFTER continuity_strength;

ALTER TABLE dwm_industry_vp_agg_di
    ADD COLUMN leader_strength DECIMAL(20,6) NULL
        COMMENT '龙头强度=(前3市值涨幅均值+量比均值)/2'
        AFTER trend_return_20d;

ALTER TABLE dwm_industry_vp_agg_di
    MODIFY COLUMN rising_ratio DECIMAL(20,6) NULL
        COMMENT '上涨占比(流通市值加权)';

ALTER TABLE dwm_industry_vp_agg_di
    MODIFY COLUMN breakout_ratio DECIMAL(20,6) NULL
        COMMENT '严格突破成交额占比';

ALTER TABLE dwm_industry_vp_agg_di
    MODIFY COLUMN amount_streak_days INT NOT NULL DEFAULT 0
        COMMENT '成交额连续高于MA天数(展示)';

-- -----------------------------------------------------------------------------
-- 4. dwm_industry_vp_score_di：六维子分 + 原始指标快照
-- -----------------------------------------------------------------------------
ALTER TABLE dwm_industry_vp_score_di
    ADD COLUMN score_leader DECIMAL(10,2) NULL
        COMMENT '龙头强度子分(升序百分位)'
        AFTER score_breakout;

ALTER TABLE dwm_industry_vp_score_di
    ADD COLUMN continuity_strength DECIMAL(20,6) NULL
        COMMENT '连续放量强度(原始)'
        AFTER amount_streak_days;

ALTER TABLE dwm_industry_vp_score_di
    ADD COLUMN trend_return_20d DECIMAL(20,6) NULL
        COMMENT '20日收益率(%)，取百分位前max(0,ret)'
        AFTER continuity_strength;

ALTER TABLE dwm_industry_vp_score_di
    ADD COLUMN leader_strength DECIMAL(20,6) NULL
        COMMENT '龙头强度(原始)'
        AFTER trend_return_20d;

ALTER TABLE dwm_industry_vp_score_di
    MODIFY COLUMN score_continuity DECIMAL(10,2) NULL
        COMMENT '连续放量强度子分(升序百分位)';

ALTER TABLE dwm_industry_vp_score_di
    MODIFY COLUMN score_trend DECIMAL(10,2) NULL
        COMMENT '趋势强度子分(20日收益归零后升序百分位)';

ALTER TABLE dwm_industry_vp_score_di
    MODIFY COLUMN rising_ratio DECIMAL(20,6) NULL
        COMMENT '上涨占比(流通市值加权)';

ALTER TABLE dwm_industry_vp_score_di
    MODIFY COLUMN breakout_ratio DECIMAL(20,6) NULL
        COMMENT '严格突破成交额占比';

ALTER TABLE dwm_industry_vp_score_di
    MODIFY COLUMN rank_vp INT NULL
        COMMENT '行业+概念合并池VP排名';

-- -----------------------------------------------------------------------------
-- 5. 验证（可选）
-- -----------------------------------------------------------------------------
SELECT 'dwm_vp_config' AS tbl, config_key, weight_vol, weight_trend,
       weight_continuity, weight_breadth, weight_breakout, weight_leader
FROM dwm_vp_config
WHERE config_key = '__global__' AND is_active = 1
ORDER BY effective_date DESC
LIMIT 1;

SELECT 'dwm_stock_vp_factor_di' AS tbl,
       COUNT(*) AS col_exists
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'dwm_stock_vp_factor_di'
  AND COLUMN_NAME = 'is_breakout_strict';

SELECT 'dwm_industry_vp_agg_di' AS tbl, COLUMN_NAME
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'dwm_industry_vp_agg_di'
  AND COLUMN_NAME IN ('continuity_strength', 'trend_return_20d', 'leader_strength');

SELECT 'dwm_industry_vp_score_di' AS tbl, COLUMN_NAME
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'dwm_industry_vp_score_di'
  AND COLUMN_NAME IN ('score_leader', 'continuity_strength', 'trend_return_20d', 'leader_strength');
