"""应用配置：环境变量与 func.sh 中的 MYSQL_* 对齐。"""
from __future__ import annotations

import os

MYSQL_HOST = os.getenv("MYSQL_HOST", "localhost")
MYSQL_PORT = int(os.getenv("MYSQL_PORT", "3306"))
MYSQL_USER = os.getenv("MYSQL_USER", "app_user")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "")
MYSQL_DATABASE = os.getenv("MYSQL_DATABASE", "stock_data")

JWT_SECRET = os.getenv("IFF_JWT_SECRET", "iff-dev-secret-change-in-prod")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_HOURS = int(os.getenv("IFF_JWT_EXPIRE_HOURS", "168"))
COOKIE_NAME = "iff_token"

APP_TITLE = "行业资金流"
APP_HOST = os.getenv("IFF_HOST", "0.0.0.0")
# 默认 8081，避免与 XXL-JOB 等占用 8080 的服务冲突
APP_PORT = int(os.getenv("IFF_PORT", "8081"))
