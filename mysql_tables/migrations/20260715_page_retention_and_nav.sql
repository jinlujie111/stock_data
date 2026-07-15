-- =============================================================================
-- 2026-07-15: 页面裁剪 + 龙头/量价保留期
--
-- 1) 龙头 DWM：仅保留近 31 天（约 1 个月）
-- 2) 量价 DWM：仅保留近 183 天（约半年）
-- 3) detail_json 列若仍存在则删除（应用层已停写）
--
-- 说明：
--   - DELETE 不自动缩 .ibd；满盘时勿对大表 OPTIMIZE，优先保证 Avail 后按需重建
--   - 日常清理已写入日批 etl/sector_dragon/batch.py、etl/volume_price/batch.py
-- =============================================================================

-- 龙头：近 1 个月
DELETE FROM stock_data.dwm_sector_stock_dragon_score_di
WHERE trade_date < DATE_SUB(CURDATE(), INTERVAL 31 DAY);

DELETE FROM stock_data.dwm_sector_dragon_summary_di
WHERE trade_date < DATE_SUB(CURDATE(), INTERVAL 31 DAY);

-- 量价：近半年
DELETE FROM stock_data.dwm_stock_vp_factor_di
WHERE trade_date < DATE_SUB(CURDATE(), INTERVAL 183 DAY);

DELETE FROM stock_data.dwm_industry_vp_agg_di
WHERE trade_date < DATE_SUB(CURDATE(), INTERVAL 183 DAY);

DELETE FROM stock_data.dwm_industry_vp_score_di
WHERE trade_date < DATE_SUB(CURDATE(), INTERVAL 183 DAY);

-- 兼容：若生产仍残留 detail_json 列则删掉（已删则忽略报错）
-- ALTER TABLE stock_data.dwm_sector_stock_dragon_score_di DROP COLUMN detail_json;
