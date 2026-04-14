#!/usr/bin/env python3
"""
运行行业资金流衍生指标计算
"""
import argparse
from datetime import datetime, timedelta
from industry_fund_flow_derivative_etl import IndustryFundFlowDerivativeETL

def parse_args():
    parser = argparse.ArgumentParser(description='运行行业资金流衍生指标计算')
    parser.add_argument('--start-date', type=str, help='开始日期，格式：YYYY-MM-DD')
    parser.add_argument('--end-date', type=str, help='结束日期，格式：YYYY-MM-DD')
    return parser.parse_args()

def main():
    args = parse_args()
    
    # 确定日期范围
    if args.end_date:
        end_date = datetime.strptime(args.end_date, '%Y-%m-%d').date()
    else:
        end_date = datetime.now().date()
    
    if args.start_date:
        start_date = datetime.strptime(args.start_date, '%Y-%m-%d').date()
    else:
        # 默认计算最近30天的数据
        start_date = end_date - timedelta(days=30)
    
    print(f"开始运行行业资金流衍生指标计算")
    print(f"日期范围：{start_date} 至 {end_date}")
    
    etl = IndustryFundFlowDerivativeETL()
    etl.run(start_date, end_date)
    
    print("运行完成！")

if __name__ == '__main__':
    main()
