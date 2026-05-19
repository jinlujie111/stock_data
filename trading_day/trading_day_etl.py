import re
import urllib.parse

import pandas as pd
from datetime import datetime, timedelta
from sqlalchemy import create_engine, text
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from utils import mysql_config as config


def _safe_table_name(name: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_]+", name):
        raise ValueError(f"非法表名: {name!r}")
    return name


class TradingDayETL:
    def __init__(self, table_name: str = "trading_day_di", database: str | None = None):
        self.table_name = _safe_table_name(table_name)
        db = database or config.MYSQL_DATABASE
        pwd = urllib.parse.quote_plus(config.MYSQL_PASSWORD)
        user_q = urllib.parse.quote_plus(config.MYSQL_USER)
        url = (
            f"mysql+pymysql://{user_q}:{pwd}@{config.MYSQL_HOST}:{config.MYSQL_PORT}/"
            f"{db}?charset=utf8mb4"
        )
        self.engine = create_engine(url)
        self.source = "trading_day"

    def create_table(self):
        """创建交易日维度表"""
        tbl = self.table_name
        with self.engine.connect() as conn:
            conn.execute(text(f"""
                CREATE TABLE IF NOT EXISTS {tbl} (
                    id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '自增主键',
                    trade_date DATE NOT NULL COMMENT '日期',
                    is_trading_day INT NOT NULL COMMENT '是否交易日: 1=是, 0=否',
                    week INT NULL COMMENT '星期: 1=周一, 7=周日',
                    month INT NULL COMMENT '月份',
                    quarter INT NULL COMMENT '季度',
                    year INT NULL COMMENT '年份',
                    created_at DATETIME NOT NULL COMMENT '创建时间',
                    updated_at DATETIME NOT NULL COMMENT '更新时间',
                    UNIQUE KEY uniq_trade_date (trade_date)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='交易日维度表';
            """))
            conn.commit()
    
    def get_existing_dates(self):
        """获取已存在的日期"""
        tbl = self.table_name
        with self.engine.connect() as conn:
            result = conn.execute(text(f"SELECT trade_date FROM {tbl}"))
            return {row[0] for row in result.fetchall()}
    
    def is_trading_day(self, date):
        """判断是否为交易日"""
        # 周末不是交易日
        if date.weekday() in (5, 6):
            return False
        
        # 节假日列表
        holidays = [
            # 2026年节假日
            datetime(2026, 1, 1).date(),  # 元旦
            datetime(2026, 2, 1).date(),  # 春节
            datetime(2026, 2, 2).date(),
            datetime(2026, 2, 3).date(),
            datetime(2026, 2, 4).date(),
            datetime(2026, 2, 5).date(),
            datetime(2026, 4, 6).date(),  # 清明节
            datetime(2026, 5, 1).date(),  # 劳动节
            datetime(2026, 5, 2).date(),
            datetime(2026, 5, 3).date(),
            datetime(2026, 6, 19).date(),  # 端午节
            datetime(2026, 9, 25).date(),  # 中秋节
            datetime(2026, 10, 1).date(),  # 国庆节
            datetime(2026, 10, 2).date(),
            datetime(2026, 10, 3).date(),
            datetime(2026, 10, 4).date(),
            datetime(2026, 10, 5).date(),
        ]
        
        # 检查是否为节假日
        if date in holidays:
            return False
        
        # 其他日期默认为交易日
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
                'trade_date': date_obj,
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
        
        tbl = self.table_name
        with self.engine.connect() as conn:
            insert_sql = text(f"""
                INSERT IGNORE INTO {tbl} (
                    trade_date, is_trading_day, week, month, quarter, year, created_at, updated_at
                ) VALUES (
                    :trade_date, :is_trading_day, :week, :month, :quarter, :year, :created_at, :updated_at
                )
            """)
            conn.execute(insert_sql, records)
            conn.commit()

    def run(self, start_date, end_date) -> int:
        """运行ETL流程，返回新增行数"""
        print(f"开始生成交易日数据，日期范围：{start_date} 至 {end_date} → {self.table_name}")

        self.create_table()
        records = self.generate_trading_days(start_date, end_date)

        if records:
            self.insert_data(records)
            print(f"生成完成，新增 {len(records)} 条交易日数据")
            return len(records)
        print("没有新的交易日数据需要添加")
        return 0

if __name__ == "__main__":
    etl = TradingDayETL()
    # 生成从2020年1月1日至今的交易日数据
    end_date = datetime.now().date()
    start_date = end_date - timedelta(days=365*6)  # 生成6年的数据
    etl.run(start_date, end_date)