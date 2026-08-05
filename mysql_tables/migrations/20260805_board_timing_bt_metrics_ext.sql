-- =============================================================================
-- 择时回测指标扩展：夏普 / Calmar / 连亏 / 买入持有基准（2026-08-05）
-- =============================================================================

USE stock_data;

ALTER TABLE dwm_board_timing_bt_run
    ADD COLUMN sharpe DECIMAL(12, 6) NULL COMMENT '交易夏普=均值/标准差' AFTER profit_factor,
    ADD COLUMN calmar DECIMAL(12, 6) NULL COMMENT 'Calmar=总收益/最大回撤' AFTER sharpe,
    ADD COLUMN max_loss_streak INT NULL COMMENT '最大连续亏损笔数' AFTER calmar,
    ADD COLUMN bench_return DECIMAL(12, 6) NULL COMMENT '等权买入持有近似' AFTER max_loss_streak;

ALTER TABLE dwm_board_timing_bt_metrics
    ADD COLUMN sharpe DECIMAL(12, 6) NULL COMMENT '交易夏普' AFTER profit_factor,
    ADD COLUMN calmar DECIMAL(12, 6) NULL COMMENT 'Calmar' AFTER sharpe,
    ADD COLUMN max_loss_streak INT NULL COMMENT '最大连续亏损笔数' AFTER calmar,
    ADD COLUMN bench_return DECIMAL(12, 6) NULL COMMENT '区间买入持有收益' AFTER max_loss_streak,
    ADD COLUMN excess_return DECIMAL(12, 6) NULL COMMENT '超额=total_return-bench_return' AFTER bench_return;

SELECT 'board_timing_bt_metrics_ext_ok' AS step;
