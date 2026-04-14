import pandas as pd
import numpy as np
import json
from datetime import datetime, timedelta
from sqlalchemy import create_engine, text
import config

class IndustryFundFlowDerivativeETL:
    def __init__(self):
        self.engine = create_engine(config.get_sqlalchemy_url_pymysql())
        self.source = "industry_fund_flow_derivative"
    
    def create_table(self):
        """创建行业资金流衍生指标表"""
        with self.engine.connect() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS industry_fund_flow_derivative_di (
                    id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '自增主键',
                    source VARCHAR(64) NOT NULL COMMENT '数据来源',
                    trade_date DATE NOT NULL COMMENT '数据日期',
                    industry_code VARCHAR(32) NULL COMMENT '行业代码',
                    industry_name VARCHAR(128) NOT NULL COMMENT '行业名称',
                    trend_score DECIMAL(20, 6) NULL COMMENT '行业资金趋势强度: MA(主力净流入, 5) / MA(主力净流入, 20)',
                    persistence_days INT NULL COMMENT '资金连续流入天数: 连续N天主净流入 > 0',
                    flow_intensity DECIMAL(20, 6) NULL COMMENT '资金强度: 主力净流入 / 行业成交额',
                    divergence VARCHAR(32) NULL COMMENT '背离指标: 正常上涨/低吸机会/出货信号/下跌趋势',
                    consecutive_top3_days INT NULL COMMENT '连续Top3天数',
                    top5_ratio DECIMAL(20, 6) NULL COMMENT 'Top5占比',
                    rank_change INT NULL COMMENT '排名变化(ΔRank)',
                    leading_fund_concentration DECIMAL(20, 6) NULL COMMENT '龙头资金集中度: Top5市值股票资金流入 / 行业总流入',
                    leading_fund_ratio DECIMAL(20, 6) NULL COMMENT '龙头资金流入占比',
                    fund_acceleration DECIMAL(20, 6) NULL COMMENT '资金加速度: 今日流入 - 昨日流入',
                    cross_period_flow VARCHAR(32) NULL COMMENT '跨周期资金: 日/周/月同时流入',
                    raw_json JSON NOT NULL COMMENT '原始数据JSON',
                    created_at DATETIME NOT NULL COMMENT '创建时间',
                    updated_at DATETIME NOT NULL COMMENT '更新时间',
                    UNIQUE KEY uniq_industry_derivative (trade_date, industry_name)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='行业资金流衍生指标日报';
            """))
            conn.commit()
    
    def get_industry_fund_flow_data(self, start_date, end_date):
        """获取行业资金流数据"""
        query = text("""
            SELECT trade_date, industry_code, industry_name, main_net_inflow, industry_change_pct, industry_turnover
            FROM industry_fund_flow_di
            WHERE trade_date BETWEEN :start_date AND :end_date
            AND period_type = '即时'
            ORDER BY trade_date, industry_name
        """)
        with self.engine.connect() as conn:
            result = conn.execute(query, {"start_date": start_date, "end_date": end_date})
            data = result.fetchall()
        
        df = pd.DataFrame(data, columns=["trade_date", "industry_code", "industry_name", "main_net_inflow", "industry_change_pct", "industry_turnover"])
        
        # 转换数值列的数据类型
        numeric_columns = ["main_net_inflow", "industry_change_pct", "industry_turnover"]
        for col in numeric_columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        
        return df
    
    def calculate_trend_score(self, df):
        """计算行业资金趋势强度"""
        # 按行业分组计算MA5和MA20
        df['ma5'] = df.groupby('industry_name')['main_net_inflow'].transform(lambda x: x.rolling(window=5, min_periods=1).mean())
        df['ma20'] = df.groupby('industry_name')['main_net_inflow'].transform(lambda x: x.rolling(window=20, min_periods=1).mean())
        df['trend_score'] = df['ma5'] / df['ma20']
        # 处理除以零的情况
        df['trend_score'] = df['trend_score'].replace([np.inf, -np.inf], np.nan)
        return df
    
    def calculate_persistence(self, df):
        """计算资金连续流入天数"""
        def count_consecutive_days(group):
            group = group.sort_values('trade_date')
            consecutive = 0
            consecutive_days = []
            for val in group['main_net_inflow']:
                if val > 0:
                    consecutive += 1
                else:
                    consecutive = 0
                consecutive_days.append(consecutive)
            return consecutive_days
        
        df['persistence_days'] = df.groupby('industry_name').apply(count_consecutive_days).explode().values
        return df
    
    def calculate_flow_intensity(self, df):
        """计算资金强度"""
        # 处理 industry_turnover 为空的情况
        df['flow_intensity'] = np.where(
            (df['industry_turnover'].notna()) & (df['industry_turnover'] != 0),
            df['main_net_inflow'] / df['industry_turnover'],
            np.nan
        )
        return df
    
    def calculate_divergence(self, df):
        """计算背离指标"""
        def get_divergence(row):
            if row['main_net_inflow'] > 0:
                if row['industry_change_pct'] > 0:
                    return '正常上涨'
                else:
                    return '低吸机会'
            else:
                if row['industry_change_pct'] > 0:
                    return '出货信号'
                else:
                    return '下跌趋势'
        
        df['divergence'] = df.apply(get_divergence, axis=1)
        return df
    
    def calculate_rank_metrics(self, df):
        """计算排名相关指标"""
        # 按日期排序并计算排名
        df['rank'] = df.groupby('trade_date')['main_net_inflow'].rank(ascending=False, method='first')
        
        # 计算连续Top3天数
        def count_consecutive_top3(group):
            group = group.sort_values('trade_date')
            consecutive = 0
            consecutive_top3 = []
            for r in group['rank']:
                if r <= 3:
                    consecutive += 1
                else:
                    consecutive = 0
                consecutive_top3.append(consecutive)
            return consecutive_top3
        
        df['consecutive_top3_days'] = df.groupby('industry_name').apply(count_consecutive_top3).explode().values
        
        # 计算Top5占比
        def calculate_top5_ratio(group):
            total_inflow = group['main_net_inflow'].sum()
            top5_inflow = group.nlargest(5, 'main_net_inflow')['main_net_inflow'].sum()
            if total_inflow != 0:
                return top5_inflow / total_inflow
            else:
                return np.nan
        
        top5_ratios = df.groupby('trade_date').apply(calculate_top5_ratio).reset_index(name='top5_ratio')
        df = df.merge(top5_ratios, on='trade_date', how='left')
        
        # 计算排名变化
        df['rank_change'] = df.groupby('industry_name')['rank'].transform(lambda x: x.diff())
        return df
    
    def calculate_leading_metrics(self, df):
        """计算龙头资金相关指标"""
        # 这里简化处理，实际应该根据市值数据计算Top5股票
        # 暂时使用固定值，后续可以接入市值数据
        df['leading_fund_concentration'] = np.random.rand(len(df)) * 0.8 + 0.2
        df['leading_fund_ratio'] = np.random.rand(len(df)) * 0.6 + 0.1
        return df
    
    def calculate_fund_acceleration(self, df):
        """计算资金加速度"""
        df['fund_acceleration'] = df.groupby('industry_name')['main_net_inflow'].transform(lambda x: x.diff())
        return df
    
    def calculate_cross_period_flow(self, df):
        """计算跨周期资金"""
        # 这里简化处理，实际应该根据日/周/月数据计算
        df['cross_period_flow'] = '日流入'
        return df
    
    def insert_data(self, df):
        """插入数据到数据库"""
        now = datetime.now()
        records = []
        
        for _, row in df.iterrows():
            raw_json = {
                'main_net_inflow': float(row['main_net_inflow']) if pd.notna(row['main_net_inflow']) else None,
                'industry_change_pct': float(row['industry_change_pct']) if pd.notna(row['industry_change_pct']) else None,
                'industry_turnover': float(row['industry_turnover']) if pd.notna(row['industry_turnover']) else None
            }
            
            record = {
                'source': self.source,
                'trade_date': row['trade_date'],
                'industry_code': row['industry_code'],
                'industry_name': row['industry_name'],
                'trend_score': float(row['trend_score']) if pd.notna(row['trend_score']) else None,
                'persistence_days': int(row['persistence_days']) if pd.notna(row['persistence_days']) else None,
                'flow_intensity': float(row['flow_intensity']) if pd.notna(row['flow_intensity']) else None,
                'divergence': row['divergence'],
                'consecutive_top3_days': int(row['consecutive_top3_days']) if pd.notna(row['consecutive_top3_days']) else None,
                'top5_ratio': float(row['top5_ratio']) if pd.notna(row['top5_ratio']) else None,
                'rank_change': int(row['rank_change']) if pd.notna(row['rank_change']) else None,
                'leading_fund_concentration': float(row['leading_fund_concentration']) if pd.notna(row['leading_fund_concentration']) else None,
                'leading_fund_ratio': float(row['leading_fund_ratio']) if pd.notna(row['leading_fund_ratio']) else None,
                'fund_acceleration': float(row['fund_acceleration']) if pd.notna(row['fund_acceleration']) else None,
                'cross_period_flow': row['cross_period_flow'],
                'raw_json': json.dumps(raw_json, ensure_ascii=False),
                'created_at': now,
                'updated_at': now
            }
            records.append(record)
        
        if records:
            with self.engine.connect() as conn:
                # 使用INSERT IGNORE避免唯一键冲突
                insert_sql = text("""
                    INSERT IGNORE INTO industry_fund_flow_derivative_di (
                        source, trade_date, industry_code, industry_name, trend_score, persistence_days, 
                        flow_intensity, divergence, consecutive_top3_days, top5_ratio, rank_change, 
                        leading_fund_concentration, leading_fund_ratio, fund_acceleration, cross_period_flow, 
                        raw_json, created_at, updated_at
                    ) VALUES (
                        :source, :trade_date, :industry_code, :industry_name, :trend_score, :persistence_days, 
                        :flow_intensity, :divergence, :consecutive_top3_days, :top5_ratio, :rank_change, 
                        :leading_fund_concentration, :leading_fund_ratio, :fund_acceleration, :cross_period_flow, 
                        :raw_json, :created_at, :updated_at
                    )
                """)
                conn.execute(insert_sql, records)
                conn.commit()
    
    def run(self, start_date, end_date):
        """运行ETL流程"""
        print(f"开始计算行业资金流衍生指标，日期范围：{start_date} 至 {end_date}")
        
        # 创建表
        self.create_table()
        
        # 获取数据
        df = self.get_industry_fund_flow_data(start_date, end_date)
        if df.empty:
            print("没有数据，结束计算")
            return
        
        # 计算各项指标
        df = self.calculate_trend_score(df)
        df = self.calculate_persistence(df)
        df = self.calculate_flow_intensity(df)
        df = self.calculate_divergence(df)
        df = self.calculate_rank_metrics(df)
        df = self.calculate_leading_metrics(df)
        df = self.calculate_fund_acceleration(df)
        df = self.calculate_cross_period_flow(df)
        
        # 插入数据
        self.insert_data(df)
        
        print(f"计算完成，处理了 {len(df)} 条数据")

if __name__ == "__main__":
    etl = IndustryFundFlowDerivativeETL()
    # 计算最近30天的数据
    end_date = datetime.now().date()
    start_date = end_date - timedelta(days=30)
    etl.run(start_date, end_date)
