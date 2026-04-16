import pandas as pd
from datetime import datetime, timedelta
from sqlalchemy import create_engine, text
import sys
from pathlib import Path

# 添加项目根目录到路径
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT / "industry_indicator") not in sys.path:
    sys.path.insert(0, str(_ROOT / "industry_indicator"))

import config

class TradingDayETL:
    def __init__(self):
        self.engine = create_engine(config.get_sqlalchemy_url_pymysql())
        self.source = "trading_day"
    
    def create_table(self):
        """创建交易日维度表"""
        with self.engine.connect() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS trading_day_di (
                    id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '自增主键',
                    date DATE NOT NULL COMMENT '日期',
                    is_trading_day INT NOT NULL COMMENT '是否交易日: 1=是, 0=否',
                    week INT NULL COMMENT '星期: 1=周一, 7=周日',
                    month INT NULL COMMENT '月份',
                    quarter INT NULL COMMENT '季度',
                    year INT NULL COMMENT '年份',
                    created_at DATETIME NOT NULL COMMENT '创建时间',
                    updated_at DATETIME NOT NULL COMMENT '更新时间',
                    UNIQUE KEY uniq_date (date)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='交易日维度表';
            """))
            conn.commit()
    
    def get_existing_dates(self):
        """获取已存在的日期"""
        with self.engine.connect() as conn:
            result = conn.execute(text("SELECT date FROM trading_day_di"))
            return {row[0] for row in result.fetchall()}
    
    def is_trading_day(self, date):
        """判断是否为交易日"""
        # 这里简化处理，实际应该从数据源获取
        # 周末不是交易日
        if date.weekday() in (5, 6):
            return False
        # 这里可以添加节假日判断
        # 暂时返回True，后续可以接入节假日数据
        return True
    
    def generate_trading_days(self, start_date, end_date):
        """生成交易日数据"""
        existing_dates = self.get_existing_dates()
        
        dates = pd.date_range(start=start_date, end=end_date)
        records = []
        now = datetime.now()
        
        for date in dates:
            date_obj = date.date()
            if date_obj in existing_dates:
                continue
            
            is_trading = 1 if self.is_trading_day(date_obj) else 0
            week = date_obj.isoweekday()
            month = date_obj.month
            quarter = (month - 1) // 3 + 1
            year = date_obj.year
            
            record = {
                'date': date_obj,
                'is_trading_day': is_trading,
                'week': week,
                'month': month,
                'quarter': quarter,
                'year': year,
                'created_at': now,
                'updated_at': now
            }
            records.append(record)
        
        return records
    
    def insert_data(self, records):
        """插入数据到数据库"""
        if not records:
            return
        
        with self.engine.connect() as conn:
            insert_sql = text("""
                INSERT IGNORE INTO trading_day_di (
                    date, is_trading_day, week, month, quarter, year, created_at, updated_at
                ) VALUES (
                    :date, :is_trading_day, :week, :month, :quarter, :year, :created_at, :updated_at
                )
            """)
            conn.execute(insert_sql, records)
            conn.commit()
    
    def run(self, start_date, end_date):
        """运行ETL流程"""
        print(f"开始生成交易日数据，日期范围：{start_date} 至 {end_date}")
        
        # 创建表
        self.create_table()
        
        # 生成数据
        records = self.generate_trading_days(start_date, end_date)
        
        if records:
            # 插入数据
            self.insert_data(records)
            print(f"生成完成，新增 {len(records)} 条交易日数据")
        else:
            print("没有新的交易日数据需要添加")

if __name__ == "__main__":
    etl = TradingDayETL()
    # 生成从2020年1月1日至今的交易日数据
    end_date = datetime.now().date()
    start_date = end_date - timedelta(days=365*6)  # 生成6年的数据
    etl.run(start_date, end_date)