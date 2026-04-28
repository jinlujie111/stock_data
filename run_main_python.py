#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
主程序：执行所有数据处理任务
功能：替代原来的run_all.bat，执行所有数据处理任务
支持命令行参数：
  python run_main_python.py [trade_date]
  例如：python run_main_python.py 20260417
"""

import argparse
import logging
import os
import sys
from pathlib import Path

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
LOG = logging.getLogger(__name__)

# 添加项目路径
sys.path.insert(0, str(Path(__file__).resolve().parent))


def run_industry_sw_universe(trade_date=None):
    """执行行业申万数据任务"""
    LOG.info("开始执行行业申万数据任务")
    from industry_indicator.industry_sw_universe_etl import run
    
    # 获取配置
    from industry_indicator import config as cfg
    
    # 执行任务
    run(
        host=cfg.MYSQL_HOST,
        port=cfg.MYSQL_PORT,
        user=cfg.MYSQL_USER,
        password=cfg.MYSQL_PASSWORD,
        database=cfg.MYSQL_DATABASE,
        info_table=cfg.SW_INDUSTRY_INFO_TABLE,
        cons_table=cfg.SW_INDUSTRY_CONSTITUENT_TABLE,
        trade_date=trade_date,
        levels={1, 2, 3},
        sleep_seconds=0.15,
        max_industries=None,
        skip_constituents=False,
    )
    LOG.info("行业申万数据任务执行完成")


def run_industry_fund_flow(trade_date=None):
    """执行行业资金流任务"""
    LOG.info("开始执行行业资金流任务")
    from industry_indicator.industry_fund_flow_etl import run
    
    # 获取配置
    from industry_indicator import config as cfg
    
    # 执行任务
    run(
        host=cfg.MYSQL_HOST,
        port=cfg.MYSQL_PORT,
        user=cfg.MYSQL_USER,
        password=cfg.MYSQL_PASSWORD,
        database=cfg.MYSQL_DATABASE,
        table_name=cfg.INDUSTRY_FLOW_TABLE,
        periods=["即时", "3日排行", "5日排行", "10日排行", "20日排行"],
        trade_date=trade_date
    )
    LOG.info("行业资金流任务执行完成")


def run_stock_fund_flow(trade_date=None):
    """执行个股资金流任务"""
    LOG.info("开始执行个股资金流任务")
    from stock_data.stock_fund_flow_etl import run
    
    # 获取配置
    from industry_indicator import config as cfg
    
    # 执行任务
    run(
        host=cfg.MYSQL_HOST,
        port=cfg.MYSQL_PORT,
        user=cfg.MYSQL_USER,
        password=cfg.MYSQL_PASSWORD,
        database=cfg.MYSQL_DATABASE,
        table_name=cfg.STOCK_FLOW_TABLE,
        periods=["即时", "3日排行", "5日排行", "10日排行", "20日排行"],
        trade_date=trade_date
    )
    LOG.info("个股资金流任务执行完成")


def run_industry_valuation(trade_date=None):
    """执行行业估值任务"""
    LOG.info("开始执行行业估值任务")
    from industry_indicator.industry_valuation_etl import run
    
    # 获取配置
    from industry_indicator import config as cfg
    
    # 执行任务
    run(
        host=cfg.MYSQL_HOST,
        port=cfg.MYSQL_PORT,
        user=cfg.MYSQL_USER,
        password=cfg.MYSQL_PASSWORD,
        database=cfg.MYSQL_DATABASE,
        table_name=cfg.INDUSTRY_VALUATION_TABLE,
        levels=[1, 2, 3],
        trade_date=trade_date
    )
    LOG.info("行业估值任务执行完成")


def run_industry_financial_data(trade_date=None):
    """执行行业财务数据任务"""
    LOG.info("开始执行行业财务数据任务")
    from industry_indicator.industry_financial_data_etl import run
    
    # 获取配置
    from industry_indicator import config as cfg
    
    # 执行任务
    run(
        host=cfg.MYSQL_HOST,
        port=cfg.MYSQL_PORT,
        user=cfg.MYSQL_USER,
        password=cfg.MYSQL_PASSWORD,
        database=cfg.MYSQL_DATABASE,
        table_name=cfg.INDUSTRY_FINANCIAL_DATA_TABLE,
        trade_date=trade_date
    )
    LOG.info("行业财务数据任务执行完成")


def run_industry_financial_indicator():
    """执行行业财务指标任务"""
    LOG.info("开始执行行业财务指标任务")
    from industry_indicator.industry_financial_indicator_etl import run
    
    # 获取配置
    from industry_indicator import config as cfg
    
    # 执行任务
    run(
        host=cfg.MYSQL_HOST,
        port=cfg.MYSQL_PORT,
        user=cfg.MYSQL_USER,
        password=cfg.MYSQL_PASSWORD,
        database=cfg.MYSQL_DATABASE,
        table_name=cfg.INDUSTRY_FINANCIAL_INDICATOR_TABLE,
        mode="legu_sw3",
        max_stocks_per_industry=3,
        cons_sleep=0.1
    )
    LOG.info("行业财务指标任务执行完成")


def run_industry_order_volume():
    """执行行业订单量任务"""
    LOG.info("开始执行行业订单量任务")
    from industry_indicator.industry_order_volume_etl import run
    
    # 获取配置
    from industry_indicator import config as cfg
    
    # 执行任务
    run(
        host=cfg.MYSQL_HOST,
        port=cfg.MYSQL_PORT,
        user=cfg.MYSQL_USER,
        password=cfg.MYSQL_PASSWORD,
        database=cfg.MYSQL_DATABASE,
        table_name=cfg.INDUSTRY_ORDER_VOLUME_TABLE,
        max_stocks=60,
        cons_sleep=0.1
    )
    LOG.info("行业订单量任务执行完成")


def run_industry_contract_liab_yoy():
    """执行行业合同负债同比任务"""
    LOG.info("开始执行行业合同负债同比任务")
    from industry_indicator.industry_contract_liab_yoy_etl import run
    
    # 获取配置
    from industry_indicator import config as cfg
    
    # 执行任务
    run(
        host=cfg.MYSQL_HOST,
        port=cfg.MYSQL_PORT,
        user=cfg.MYSQL_USER,
        password=cfg.MYSQL_PASSWORD,
        database=cfg.MYSQL_DATABASE,
        table_name=cfg.INDUSTRY_CONTRACT_LIAB_YOY_TABLE,
        max_stocks=60,
        cons_sleep=0.1
    )
    LOG.info("行业合同负债同比任务执行完成")


def run_industry_association_shipment():
    """执行行业协会出货任务"""
    LOG.info("开始执行行业协会出货任务")
    from industry_indicator.industry_association_shipment_etl import run
    
    # 获取配置
    from industry_indicator import config as cfg
    
    # 执行任务
    run(
        host=cfg.MYSQL_HOST,
        port=cfg.MYSQL_PORT,
        user=cfg.MYSQL_USER,
        password=cfg.MYSQL_PASSWORD,
        database=cfg.MYSQL_DATABASE,
        table_name=cfg.INDUSTRY_ASSOCIATION_SHIPMENT_TABLE
    )
    LOG.info("行业协会出货任务执行完成")


def run_industry_fund_flow_derivative(trade_date=None):
    """执行行业资金流衍生指标任务"""
    LOG.info("开始执行行业资金流衍生指标任务")
    from industry_indicator.industry_fund_flow_derivative_etl import run
    
    # 获取配置
    from industry_indicator import config as cfg
    
    # 执行任务
    run(
        host=cfg.MYSQL_HOST,
        port=cfg.MYSQL_PORT,
        user=cfg.MYSQL_USER,
        password=cfg.MYSQL_PASSWORD,
        database=cfg.MYSQL_DATABASE,
        table_name=cfg.INDUSTRY_FLOW_DERIVATIVE_TABLE,
        trade_date=trade_date
    )
    LOG.info("行业资金流衍生指标任务执行完成")


def run_stock_financial_full():
    """执行个股财务数据任务"""
    LOG.info("开始执行个股财务数据任务")
    from financial_sync.stock_financial_full_etl import run
    
    # 获取配置
    from industry_indicator import config as cfg
    
    # 执行任务
    run(
        host=cfg.MYSQL_HOST,
        port=cfg.MYSQL_PORT,
        user=cfg.MYSQL_USER,
        password=cfg.MYSQL_PASSWORD,
        database=cfg.MYSQL_DATABASE,
        table_name=cfg.STOCK_FINANCIAL_REPORT_TABLE,
        start_date="2020-01-01"
    )
    LOG.info("个股财务数据任务执行完成")


def run_trading_day():
    """执行交易日维度任务"""
    LOG.info("开始执行交易日维度任务")
    from trading_day.trading_day_etl import run
    
    # 获取配置
    from industry_indicator import config as cfg
    
    # 执行任务
    run(
        host=cfg.MYSQL_HOST,
        port=cfg.MYSQL_PORT,
        user=cfg.MYSQL_USER,
        password=cfg.MYSQL_PASSWORD,
        database=cfg.MYSQL_DATABASE,
        table_name=cfg.TRADING_DAY_TABLE,
        start_year=2020,
        end_year=2026
    )
    LOG.info("交易日维度任务执行完成")


def run_ths_industry():
    """执行同花顺行业数据任务"""
    LOG.info("开始执行同花顺行业数据任务")
    from industry_indicator.ths_industry_etl import THSIndustryETL
    
    # 执行任务
    etl = THSIndustryETL()
    etl.run()
    LOG.info("同花顺行业数据任务执行完成")


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="执行所有数据处理任务")
    parser.add_argument("trade_date", nargs="?", default=None, help="交易日期，格式为 YYYYMMDD，例如：20260417")
    args = parser.parse_args()
    
    trade_date = args.trade_date
    if trade_date:
        LOG.info(f"将执行日期为 {trade_date} 的数据处理任务")
    else:
        LOG.info("将执行所有数据处理任务（无指定日期）")
    
    try:
        # 1. 行业申万数据
        run_industry_sw_universe(trade_date)
        
        # 2. 行业资金流
        run_industry_fund_flow(trade_date)
        
        # 3. 个股资金流
        run_stock_fund_flow(trade_date)
        
        # 4. 行业估值
        run_industry_valuation(trade_date)
        
        # 5. 行业财务数据
        run_industry_financial_data(trade_date)
        
        # 6. 行业财务指标
        run_industry_financial_indicator()
        
        # 7. 行业订单量
        run_industry_order_volume()
        
        # 8. 行业合同负债同比
        run_industry_contract_liab_yoy()
        
        # 9. 行业协会出货
        run_industry_association_shipment()
        
        # 10. 行业资金流衍生指标
        run_industry_fund_flow_derivative(trade_date)
        
        # 11. 个股财务数据
        run_stock_financial_full()
        
        # 12. 交易日维度
        run_trading_day()
        
        # 13. 同花顺行业数据
        run_ths_industry()
        
        LOG.info("所有数据处理任务执行完成")
        
    except Exception as e:
        LOG.error(f"执行任务时发生错误: {e}")
        raise


if __name__ == "__main__":
    main()
