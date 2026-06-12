-- ============================================================================
-- data_industry 账号授权（须用 MySQL root 执行一次）
--   mysql -u root -p < mysql_tables/data_industry_grants.sql
--
-- localhost / 127.0.0.1 / % 各建一条，避免本机连接报 1045
-- ============================================================================

CREATE DATABASE IF NOT EXISTS data_industry DEFAULT CHARSET utf8mb4;

CREATE USER IF NOT EXISTS 'data_industry'@'localhost' IDENTIFIED BY '1qaz!QAZjinlujie';
CREATE USER IF NOT EXISTS 'data_industry'@'127.0.0.1' IDENTIFIED BY '1qaz!QAZjinlujie';
CREATE USER IF NOT EXISTS 'data_industry'@'%' IDENTIFIED BY '1qaz!QAZjinlujie';

ALTER USER 'data_industry'@'localhost' IDENTIFIED BY '1qaz!QAZjinlujie';
ALTER USER 'data_industry'@'127.0.0.1' IDENTIFIED BY '1qaz!QAZjinlujie';
ALTER USER 'data_industry'@'%' IDENTIFIED BY '1qaz!QAZjinlujie';

GRANT ALL PRIVILEGES ON data_industry.* TO 'data_industry'@'localhost';
GRANT ALL PRIVILEGES ON data_industry.* TO 'data_industry'@'127.0.0.1';
GRANT ALL PRIVILEGES ON data_industry.* TO 'data_industry'@'%';

FLUSH PRIVILEGES;
