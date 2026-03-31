#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
项目统一配置：MySQL、Tushare Token。
其他脚本请从此模块读取，避免在代码里硬编码账号密码。
环境变量可覆盖同名项（便于部署）：MYSQL_HOST、MYSQL_PORT、MYSQL_USER、MYSQL_PASSWORD、
MYSQL_DATABASE、TUSHARE_TOKEN、INDUSTRY_FLOW_TABLE、INDUSTRY_VALUATION_TABLE、
INDUSTRY_FINANCIAL_TABLE、INDUSTRY_FINANCIAL_DATA_TABLE。
"""
import os
import urllib.parse

from sqlalchemy import create_engine

# ---------------------------------------------------------------------------
# MySQL（行业资金流、trade_cal 同步等统一使用）
# ---------------------------------------------------------------------------
MYSQL_HOST = os.getenv("MYSQL_HOST", "localhost")
MYSQL_PORT = int(os.getenv("MYSQL_PORT", "3306"))
MYSQL_USER = os.getenv("MYSQL_USER", "root")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "jinlujie")
MYSQL_DATABASE = os.getenv("MYSQL_DATABASE", "stock_data")

# 行业资金流默认表名（可被环境变量 INDUSTRY_FLOW_TABLE 覆盖）
INDUSTRY_FLOW_TABLE = os.getenv("INDUSTRY_FLOW_TABLE", "industry_fund_flow_di")

# 行业估值表名（可被环境变量 INDUSTRY_VALUATION_TABLE 覆盖）
INDUSTRY_VALUATION_TABLE = os.getenv("INDUSTRY_VALUATION_TABLE", "industry_indicator_valuation")

# 行业财务衍生指标（营收增速/毛利率/合同负债增速）
INDUSTRY_FINANCIAL_TABLE = os.getenv("INDUSTRY_FINANCIAL_TABLE", "industry_financial_indicator_di")

# 行业财务数据快照表（成分聚合，legulegu cons）
INDUSTRY_FINANCIAL_DATA_TABLE = os.getenv(
    "INDUSTRY_FINANCIAL_DATA_TABLE", "industry_financial_data_di"
)

# 与历史脚本一致：默认使用 mysqlconnector 驱动
MYSQL_DRIVER = os.getenv("MYSQL_DRIVER", "mysqlconnector")


def _build_sqlalchemy_url(driver: str | None = None) -> str:
    d = driver or MYSQL_DRIVER
    pwd = MYSQL_PASSWORD
    # 密码中的特殊字符由 URL 编码在调用方处理；此处保持与原先简单拼接一致
    return (
        f"mysql+{d}://{MYSQL_USER}:{pwd}@{MYSQL_HOST}:{MYSQL_PORT}/"
        f"{MYSQL_DATABASE}?charset=utf8"
    )


def db_connect_mysql():
    """链接 MySQL（与原有 sqoop 脚本兼容，使用 mysqlconnector）。"""
    con_string = _build_sqlalchemy_url("mysqlconnector")
    engine = create_engine(con_string)
    connect = engine.connect()
    return connect


def db_clost_mysql(connect):
    connect.close()


def get_sqlalchemy_url_pymysql() -> str:
    """pandas / sqlalchemy 使用 pymysql 时的连接串（如 trade_cal to_sql）。"""
    pwd = urllib.parse.quote_plus(MYSQL_PASSWORD)
    user_q = urllib.parse.quote_plus(MYSQL_USER)
    return (
        f"mysql+pymysql://{user_q}:{pwd}@{MYSQL_HOST}:{MYSQL_PORT}/"
        f"{MYSQL_DATABASE}?charset=utf8mb4"
    )


# ---------------------------------------------------------------------------
# Tushare（默认 Token 写在下方；生产环境建议用环境变量 TUSHARE_TOKEN 覆盖）
# ---------------------------------------------------------------------------
_DEFAULT_TUSHARE_TOKEN = "0ced3a73b7055fc7e38a2a7665db0fa371b51518e838dfce9fba5ae5"


def get_token():
    """优先环境变量 TUSHARE_TOKEN，否则使用 _DEFAULT_TUSHARE_TOKEN。"""
    return os.getenv("TUSHARE_TOKEN", "").strip() or _DEFAULT_TUSHARE_TOKEN
