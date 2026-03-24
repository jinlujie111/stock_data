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

#对应表：daily_basic

def insert_mysql_stock(table_name='daily_basic',data=''):

    connect = config.db_connect_mysql()

    data.to_sql(table_name,con=connect,if_exists='append')

    connect.close()

def delete_mysql_stock(table_name,datestr):

    connect = config.db_connect_mysql()

    print("执行先删除后插入操作，删除区间段数据： %s 到 %s 之前的数据" %(table_name,datestr) )
    sql="delete from %s where trade_date >= %s and trade_date <= %s ;" %(table_name,datestr,datestr)
    print(sql)
    connect.execute(sql)
    print('成功删除%s 表的 %s 的数据' %(table_name,datestr) )
    connect.close()

def get_data_list(list_start,list_end):

    get_stock_list = ''
    sql = "SELECT ts_code from stock_basic where `index` >= %s and `index` <= %s " %(list_start,list_end)
    connect = config.db_connect_mysql()
    data_result = connect.execute(sql)
    get_staock_str = json.dumps([dict(row) for row in data_result.mappings()])
    get_staock_json = eval(get_staock_str)

    for j in get_staock_json:
        get_stock_list = get_stock_list + ',' + j.get('ts_code').upper()


    return  get_stock_list.strip(',')

def get_daily(datestr):

    ts.set_token(config.get_token())
    pro = ts.pro_api()
    data_l = pro.daily_basic(ts_code='', trade_date=datestr,
                             fields='ts_code,trade_date,close,turnover_rate,turnover_rate_f,volume_ratio,pe,pe_ttm,pb,ps,ps_ttm,dv_ratio,dv_ttm,total_share,float_share,free_share,total_mv,circ_mv')

    delete_mysql_stock('daily_basic', datestr)
    print("插入mysql中：%s" %(datestr))
    insert_mysql_stock('daily_basic',data_l)

def get_data_list(start_date, end_date):

    get_stock_list = ''
    sql = "SELECT cal_date from trade_cal where is_open = '1' and cal_date >= %s and cal_date <= %s " %(start_date, end_date)
    connect = config.db_connect_mysql()
    data_result = connect.execute(sql)
    get_staock_str = json.dumps([dict(row) for row in data_result.mappings()])
    get_staock_json = eval(get_staock_str)

    for j in get_staock_json:
        get_stock_list = get_stock_list + ',' + j.get('cal_date').upper()


    return  get_stock_list.strip(',')

def his_get_daily(start_date,end_date):

    get_stock_list = get_data_list(start_date, end_date)

    for i in get_stock_list.split(','):

        get_daily(i)

def get_data():

    #today = time.strftime("%Y%m%d%H%M%S", time.localtime())[0:10]
    today = time.strftime("%Y%m%d%H%M%S", time.localtime())[0:8]

    #print("当前日期为：%s" %(today))
    return today

def main():

    datestr = get_data()

    print('汇总每日股票清单数据到mysql中')
    print('获取全部股票每日重要的基本面指标，可用于选股分析、报表展示等：：%s '%(datestr))

    #历史数据
    start_date='20210101'
    end_date = '20211231'
    his_get_daily(start_date,end_date)

    #增量数据
    #datestr='20221231'
    #get_daily(datestr)
    print('汇总获取结束')


if __name__ == '__main__':
    sp_src = ','
    main()
