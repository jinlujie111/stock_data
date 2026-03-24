#!/usr/bin/env python
# -*- coding: utf-8 -*-
import json
import time

import tushare as ts
import config

def delete_mysql_stock(table_name,start_date,end_date):

    connect = config.db_connect_mysql()

    print("执行先删除后插入操作，删除区间段数据：%s 表的 %s 到 %s 之前的数据" %(table_name,start_date,end_date) )
    sql="delete from %s where end_date >= %s and end_date <= %s ;" %(table_name,start_date,end_date)
    print(sql)
    connect.execute(sql)
    print('成功删除%s 表的 %s 到 %s 之前的数据' %(table_name,start_date,end_date) )
    connect.close()

def insert_mysql_stock(table_name='fina_indicator_vip',data=''):

    connect = config.db_connect_mysql()

    data.to_sql(table_name,con=connect,if_exists='append')

    connect.close()

def get_daily(start_date,end_date):

    delete_mysql_stock('fina_indicator_vip', start_date, end_date)
    pro = ts.pro_api()
    data_l = pro.query('fina_indicator_vip', start_date=start_date, end_date=end_date)
    print("插入mysql中：报告期%s~%s" %(start_date,end_date))
    insert_mysql_stock('fina_indicator_vip',data_l)

#获取上次报告周期
def get_data(datestr):

    years = datestr[0:4]

    years_l=str(int(years)-1)

    date = datestr[4:]

    n_date = ''

    if date >= '0101' and date <= '0331':
        n_date = years_l + '1231'
    elif date > '0401' and date <= '0630':
        n_date = years + '0331'
    elif date > '0601' and date <= '0930':
        n_date = years + '0630'
    elif date > '0901' and date <= '1231':
        n_date = years + '0930'

    return n_date

def his_get_daily():

    years = ['2015', '2016','2017','2018','2019','2020','2021','2022']

    month = ['0331', '0630', '0930', '1231']

    for i in years:
        for j in month:
            datestr = i + j
            start_date=datestr
            end_date = datestr
            get_daily(start_date,end_date)


def main():

    today = time.strftime("%Y%m%d%H%M%S", time.localtime())[0:8]

    #获取上次报告周期
    n_date_e = get_data(today)
    n_date_s = get_data(n_date_e)

    #start_date = '20221231'
    #end_date = '20221231'
    print("获取stock财务数据行情，更新时间段为：%s - %s" %(n_date_s,n_date_e))

    #历史数据:已经同步的数据周期 2015-03-31  ~ 2023-03-31
    #his_get_daily()
    #增量数据
    get_daily(n_date_s,n_date_e)
    print("获取结束")


if __name__ == '__main__':
    sp_src = ','
    main()


