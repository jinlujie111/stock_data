#!/usr/bin/env python
# -*- coding: utf-8 -*-
import sys, os
import json
import time
import datetime
import io
import csv
import tushare as ts
import pymysql
from sqlalchemy import create_engine

#返回tushare的token
def get_token():

    token="0ced3a73b7055fc7e38a2a7665db0fa371b51518e838dfce9fba5ae5"
    token='2bf9245f9292c46cdeba3a4a2a108b05e4ae40720ec8795e2610f666'
    return token

#链接mysql库
def db_connect_mysql():

    con_string = "mysql+mysqlconnector://root:jinlujie@localhost:3306/stock_data?charset=utf8"
    engine = create_engine(con_string)
    connect = engine.connect()
    return connect

#关闭mysql库链接
def db_clost_mysql(connect):

    connect.close()

