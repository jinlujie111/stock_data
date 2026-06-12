"""应用配置：连接 data_industry 库（IFF_MYSQL_*，由 func.sh 导出）。"""
from __future__ import annotations

import os

MYSQL_HOST = os.getenv("IFF_MYSQL_HOST", "localhost")
MYSQL_PORT = int(os.getenv("IFF_MYSQL_PORT", "3306"))
MYSQL_USER = os.getenv("IFF_MYSQL_USER", "data_industry")
MYSQL_PASSWORD = os.getenv("IFF_MYSQL_PASSWORD", "")
MYSQL_DATABASE = os.getenv("IFF_MYSQL_DATABASE", "data_industry")

JWT_SECRET = os.getenv("IFF_JWT_SECRET", "iff-dev-secret-change-in-prod")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_HOURS = int(os.getenv("IFF_JWT_EXPIRE_HOURS", "168"))
COOKIE_NAME = "iff_token"

APP_TITLE = "行业资金流"
APP_HOST = os.getenv("IFF_HOST", "0.0.0.0")
# 默认 8082，避免与 XXL-JOB 等占用 8080 的服务冲突
APP_PORT = int(os.getenv("IFF_PORT", "8082"))
