#!/usr/bin/env python
# -*- coding: utf-8 -*-

import config.config as cf
import get_stock_daily_basic_di
import get_stock_data_daily_di
import get_stock_data_di
import get_stock_fina_indicator_di
import get_stock_trade_cal_di
import get_stock_trade_ci_daily_di

def main():

    print("数据开始同步——————————————————————————————————————————")
    print("同步stock交易日期：get_stock_trade_cal_di")
    get_stock_trade_cal_di.main()
    print("同步股票清单明细：get_stock_data_di")
    get_stock_data_di.main()
    print("同步基本面指标：get_stock_daily_basic_di")
    get_stock_daily_basic_di.main()
    print("同步stock日线行情：get_stock_data_daily_di")
    get_stock_data_daily_di.main()
    print("同步财报数据：get_stock_fina_indicator_di")
    get_stock_fina_indicator_di.main()
    print("中信行业指数行情：get_stock_trade_ci_daily_di")
    get_stock_trade_ci_daily_di.main()
    print("数据同步结束——————————————————————————————————————————")

if __name__ == '__main__':
    sp_src = ','
    main()