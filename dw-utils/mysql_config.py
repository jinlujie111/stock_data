#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
项目统一配置：MySQL 连接。
环境变量由 utils/func.sh 注入，禁止在代码中写死生产账号密码。
"""
from __future__ import annotations

import os
import urllib.parse

from sqlalchemy import create_engine

MYSQL_HOST = os.getenv("MYSQL_HOST", "localhost")
MYSQL_PORT = int(os.getenv("MYSQL_PORT", "3306"))
MYSQL_USER = os.getenv("MYSQL_USER", "root")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "jinlujie")
MYSQL_DATABASE = os.getenv("MYSQL_DATABASE", "stock_data")

STOCK_FUND_FLOW_TABLE = os.getenv("STOCK_FUND_FLOW_TABLE", "stock_fund_flow_di")

MYSQL_DRIVER = os.getenv("MYSQL_DRIVER", "mysqlconnector")


def get_sqlalchemy_url_pymysql() -> str:
    pwd = urllib.parse.quote_plus(MYSQL_PASSWORD)
    user_q = urllib.parse.quote_plus(MYSQL_USER)
    return (
        f"mysql+pymysql://{user_q}:{pwd}@{MYSQL_HOST}:{MYSQL_PORT}/"
        f"{MYSQL_DATABASE}?charset=utf8mb4"
    )


def db_connect_mysql():
    con_string = (
        f"mysql+mysqlconnector://{MYSQL_USER}:{MYSQL_PASSWORD}@{MYSQL_HOST}:"
        f"{MYSQL_PORT}/{MYSQL_DATABASE}?charset=utf8"
    )
    engine = create_engine(con_string)
    return engine.connect()


def db_clost_mysql(connect):
    connect.close()
