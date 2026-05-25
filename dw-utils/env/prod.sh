#!/bin/bash
# =============================================================================
# 生产环境 MySQL（勿在 Python 中写死，仅由 func.sh source）
# 业务库: mysql -h localhost -P 3306 -u app_user -pjinlujie -D stock_data
# 配置库: mysql -h localhost -P 3306 -u data_config -p'1qaz!QAZjinlujie' -D data_config
# =============================================================================

# data_config（Token、db_sync_task）
CONFIG_MYSQL_HOST="localhost"
CONFIG_MYSQL_PORT="3306"
CONFIG_MYSQL_USER="data_config"
CONFIG_MYSQL_PASSWORD="1qaz!QAZjinlujie"
CONFIG_MYSQL_DATABASE="data_config"

# stock_data（ETL 目标）
STOCK_MYSQL_HOST="localhost"
STOCK_MYSQL_PORT="3306"
STOCK_MYSQL_USER="app_user"
STOCK_MYSQL_PASSWORD="jinlujie"
STOCK_MYSQL_DATABASE="stock_data"
