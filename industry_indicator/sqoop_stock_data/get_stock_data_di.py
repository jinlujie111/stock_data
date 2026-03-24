#!/usr/bin/env python
# -*- coding: utf-8 -*-
import sys
import pandas as pd
import csv
import tushare as ts
import pymysql.cursors
import config
import numpy as np
#from pyspark.sql.types import StructType, StructField, IntegerType, StringType

#汇总每日全量的股票清单数据到mysql中
#对应表：stock_basic

def insert_mysql_stock(table_name='stock_basic',data=''):

    connect = config.db_connect_mysql()

    data.to_sql(table_name,con=connect,if_exists='append')

    connect.close()

def delete_mysql_stock(table_name):

    connect = config.db_connect_mysql()

    print("执行 %s 表 先删除后插入操作" %(table_name) )
    sql="truncate table %s;" %(table_name)
    print(sql)
    connect.execute(sql)
    print('成功删除 %s 表的数据' %(table_name) )
    connect.close()

def main():

    print('汇总每日全量的股票清单数据到mysql中')
    ts.set_token(config.get_token())
    pro = ts.pro_api()

    #查询当前所有正常上市交易的股票列表
    data_l = pro.stock_basic(exchange='', list_status='L', fields='ts_code,symbol,name,area,industry,fullname,enname,cnspell,market,exchange,curr_type,list_status,list_date,delist_date,is_hs')
    data_d = pro.stock_basic(exchange='', list_status='D', fields='ts_code,symbol,name,area,industry,fullname,enname,cnspell,market,exchange,curr_type,list_status,list_date,delist_date,is_hs')

    data = pd.concat([data_d, data_l], axis=0)
    #全量数据
    #data.replace('None','',inplace=True).replace(np.nan,'',inplace=True)
    delete_mysql_stock('stock_basic')
    insert_mysql_stock('stock_basic',data)
    print('汇总获取结束')


if __name__ == '__main__':
    sp_src = ','
    main()
