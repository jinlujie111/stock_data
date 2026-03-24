#!/usr/bin/env python
# -*- coding: utf-8 -*-
import json
import sys
import time
import pandas as pd
import csv
import tushare as ts
import pymysql.cursors
import config
import numpy as np

#对应表：trade_cal


def insert_mysql_stock(table_name='',data=''):

    connect = config.db_connect_mysql()

    data.to_sql(table_name,con=connect,if_exists='append')

    connect.close()

def delete_mysql_stock(table_name,end_date):

    connect = config.db_connect_mysql()

    print("执行先删除后插入操作，%s 表删除区间段数据： %s 到 %s 之前的数据" %(table_name,end_date) )
    sql="delete from %s where cal_date >= %s and cal_date <= %s ;" %(table_name,end_date)
    print(sql)
    connect.execute(sql)
    print('成功删除%s 表的 %s 到 %s 的数据' %(table_name,end_date) )
    connect.close()

def get_daily(end_date):

    ts.set_token(config.get_token())
    pro = ts.pro_api()
    #df = pro.ci_daily(trade_date='20230705', fields='ts_code,trade_date,open,low,high,close,pct_change')
    data_l = pro.ci_daily(trade_date='20230906', fields='ts_code,trade_date,open,low,high,close,pct_change')
    delete_mysql_stock('ci_daily', end_date)
    print("插入mysql中：%s - %s " %(end_date))
    #print(data_l)
    insert_mysql_stock('trade_cal',data_l)

def get_data():

    #today = time.strftime("%Y%m%d%H%M%S", time.localtime())[0:10]
    today = time.strftime("%Y%m%d%H%M%S", time.localtime())[0:8]
    #print("当前日期为：%s" %(today))
    return today

def main():

    start_date = get_data()
    end_date = get_data()

    print('获取报表交易日期：%s - %s '%(start_date,end_date))

    #start_date = '20150101'
    #end_date = '20230428'
    #存量数据：已经同步的数据周期 2015-01-01  ~ 2023-03-31

    #增量数据
    get_daily(end_date)

    print('汇总获取结束')


if __name__ == '__main__':
    sp_src = ','
    main()
