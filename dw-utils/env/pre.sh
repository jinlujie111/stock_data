#!/bin/bash
# =============================================================================
# 预发环境 MySQL
# 业务库: mysql -h localhost -P 3306 -u root -pjinlujie -D stock_data
# 配置库: mysql -h localhost -P 3306 -u root -pjinlujie -D stock_data
# （与业务库同实例同库；若预发单独建 data_config 库，可改 CONFIG_MYSQL_DATABASE）
# =============================================================================

CONFIG_MYSQL_HOST="localhost"
CONFIG_MYSQL_PORT="3306"
CONFIG_MYSQL_USER="root"
CONFIG_MYSQL_PASSWORD="jinlujie"
CONFIG_MYSQL_DATABASE="stock_data"

STOCK_MYSQL_HOST="localhost"
STOCK_MYSQL_PORT="3306"
STOCK_MYSQL_USER="root"
STOCK_MYSQL_PASSWORD="jinlujie"
STOCK_MYSQL_DATABASE="stock_data"
