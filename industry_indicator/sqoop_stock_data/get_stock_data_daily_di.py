#!/usr/bin/env python
# -*- coding: utf-8 -*-
import json
import time

import tushare as ts
import config

def delete_mysql_stock(table_name,start_date,end_date):

    connect = config.db_connect_mysql()

    print("执行先删除后插入操作，删除区间段数据：%s 表的 %s 到 %s 之前的数据" %(table_name,start_date,end_date) )
    sql="delete from %s where trade_date >= %s and trade_date <= %s ;" %(table_name,start_date,end_date)
    print(sql)
    connect.execute(sql)
    print('成功删除%s 表的 %s 到 %s 之前的数据' %(table_name,start_date,end_date) )
    connect.close()

def insert_mysql_stock(table_name='stock_daily',data=''):

    connect = config.db_connect_mysql()

    data.to_sql(table_name,con=connect,if_exists='append')

    connect.close()

#提取mysql中的所有列表
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

def get_daily(start_date,end_date):

    delete_mysql_stock('stock_daily', start_date, end_date)

    stock_list = ['1-500', '501-1000', '1001-1500', '1501-2000', '2001-2500', '2501-3000', '3001-3500', '3501-4000',
                  '4001-4500', '4501-5000', '5001-5500', '5501-6000']

    for i in stock_list:
        list_start = i.split('-')[0]
        list_end = i.split('-')[1]
        ts_code = get_data_list(list_start,list_end)
        ts.set_token(config.get_token())
        pro = ts.pro_api()
        data_l = pro.daily(ts_code=ts_code, start_date=start_date, end_date=end_date)

        print("插入mysql中：%s-%s-%s" %(list_start,list_end,ts_code))
        insert_mysql_stock('stock_daily',data_l)

def get_data():

    #today = time.strftime("%Y%m%d%H%M%S", time.localtime())[0:10]
    today = time.strftime("%Y%m%d%H%M%S", time.localtime())[0:8]

    #print("当前日期为：%s" %(today))
    return today

def his_get_daily():

    years = ['2015']

    month = ['01', '02', '03', '04', '05', '06', '07', '08', '09', '10', '11', '12']

    date = ['01-15', '16-31']

    for i in years:
        for j in month:
            datestr = i + j
            start_date = datestr + date[0].split('-')[0]
            end_date = datestr + date[0].split('-')[1]

            get_daily(start_date, end_date)

            start_date = datestr + date[1].split('-')[0]
            end_date = datestr + date[1].split('-')[1]

            get_daily(start_date, end_date)


def main():

    start_date = get_data()
    end_date = get_data()

    print("获取stock日线行情，更新时间段为：%s - %s" %(start_date,end_date))

    #start_date = '20230415'
    #end_date = '20230428'
    #历史数据
    #his_get_daily()
    #增量数据
    get_daily(start_date, end_date)
    print("获取结束")


if __name__ == '__main__':
    sp_src = ','
    main()


