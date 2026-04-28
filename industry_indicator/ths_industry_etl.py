# -*- coding: utf-8 -*-
"""
同花顺行业数据ETL程序
功能：获取同花顺的行业代码、行业名称、成交量、成交额等信息
"""

import hashlib
import json
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any

import pandas as pd
from sqlalchemy import create_engine, text

import akshare as ak

try:
    from industry_indicator.industry_fund_flow_etl import (
        _build_industry_code_map,
        _norm_name,
    )
except ImportError:  # 直接运行本文件时
    from industry_fund_flow_etl import (  # type: ignore[no-redef]
        _build_industry_code_map,
        _norm_name,
    )

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
LOG = logging.getLogger(__name__)


def _normalize_ths_industry_columns(df: pd.DataFrame) -> pd.DataFrame:
    """将不同接口返回的列名统一到 行业名称/成交量/成交额/涨跌幅。"""
    if df is None or df.empty:
        return df
    out = df.copy()
    out.columns = [str(c).strip() for c in out.columns]

    name_col = next(
        (c for c in ("行业名称", "行业", "板块") if c in out.columns),
        None,
    )
    if name_col and name_col != "行业名称":
        out = out.rename(columns={name_col: "行业名称"})

    vol_col = next((c for c in ("成交量", "总成交量") if c in out.columns), None)
    if vol_col and vol_col != "成交量":
        out = out.rename(columns={vol_col: "成交量"})

    amt_col = next((c for c in ("成交额", "总成交额") if c in out.columns), None)
    if amt_col and amt_col != "成交额":
        out = out.rename(columns={amt_col: "成交额"})

    pct_col = next((c for c in ("涨跌幅", "行业-涨跌幅") if c in out.columns), None)
    if pct_col and pct_col != "涨跌幅":
        out = out.rename(columns={pct_col: "涨跌幅"})

    return out


def _normalize_industry_code_cell(val: object) -> str:
    """落地库表 industry_code：统一为不含小数点的字符串（避免 881121.0）。"""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return ""
    if isinstance(val, float) and val == int(val):
        return str(int(val))
    s = str(val).strip()
    if s.endswith(".0") and s[:-2].isdigit():
        return s[:-2]
    return s


def _apply_ths_industry_code_by_name(df: pd.DataFrame) -> pd.DataFrame:
    """用同花顺官方板块列表填充行业代码（优先按名称左连接，其次 _norm_name 字典）。"""
    if df is None or df.empty or "行业名称" not in df.columns:
        return df
    out = df.copy()
    out["行业名称"] = out["行业名称"].map(
        lambda x: "" if x is None or (isinstance(x, float) and pd.isna(x)) else str(x).strip()
    )

    try:
        ref = ak.stock_board_industry_name_ths()
    except Exception as exc:  # noqa: BLE001
        LOG.warning("获取 stock_board_industry_name_ths 失败，退回纯名称映射: %s", exc)
        ref = None

    if ref is not None and not ref.empty and {"name", "code"}.issubset(ref.columns):
        ref = ref[["name", "code"]].copy()
        ref["name"] = ref["name"].astype(str).str.strip()
        ref["code"] = ref["code"].map(_normalize_industry_code_cell)
        merged = out.merge(ref, left_on="行业名称", right_on="name", how="left")
        merged = merged.drop(columns=["name"], errors="ignore")
        merged = merged.rename(columns={"code": "行业代码"})
        miss = merged["行业代码"].isna() | (merged["行业代码"].astype(str).str.strip() == "")
        if miss.any():
            code_map = _build_industry_code_map()

            def _fill_one(n: object) -> str:
                if n is None or (isinstance(n, float) and pd.isna(n)):
                    return ""
                s = str(n).strip()
                if not s:
                    return ""
                c = code_map.get(_norm_name(s))
                return _normalize_industry_code_cell(c) if c else ""

            merged.loc[miss, "行业代码"] = merged.loc[miss, "行业名称"].map(_fill_one)
    else:
        merged = out.copy()
        code_map = _build_industry_code_map()

        def _code_for(name: object) -> str:
            if name is None or (isinstance(name, float) and pd.isna(name)):
                return ""
            s = str(name).strip()
            if not s:
                return ""
            c = code_map.get(_norm_name(s))
            return _normalize_industry_code_cell(c) if c else ""

        merged["行业代码"] = merged["行业名称"].map(_code_for)

    still = merged["行业代码"].isna() | (merged["行业代码"].astype(str).str.strip() == "")
    if still.any():
        for nm in merged.loc[still, "行业名称"].unique():
            LOG.warning("同花顺行业名未匹配到板块代码(请核对名称或更新 akshare): %s", nm)
        merged.loc[still, "行业代码"] = merged.loc[still, "行业名称"].map(
            lambda s: f"UNMAP_{hashlib.md5(str(s).encode('utf-8')).hexdigest()[:10]}"
        )

    merged["行业代码"] = merged["行业代码"].map(_normalize_industry_code_cell)
    return merged


class THSIndustryETL:
    """同花顺行业数据ETL类"""

    def __init__(self):
        """初始化"""
        # 数据库连接信息
        self.host = "localhost"
        self.port = 3306
        self.user = "root"
        self.password = "jinlujie"
        self.database = "stock_data"
        
        # 创建数据库引擎
        self.engine = create_engine(
            f"mysql+pymysql://{self.user}:{self.password}@{self.host}:{self.port}/{self.database}"
        )

    def create_table(self):
        """创建同花顺行业数据表"""
        with self.engine.connect() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS ths_industry_di (
                    id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '自增主键',
                    trade_date DATE NOT NULL COMMENT '数据日期',
                    industry_code VARCHAR(32) NOT NULL COMMENT '行业代码',
                    industry_name VARCHAR(128) NOT NULL COMMENT '行业名称',
                    volume DECIMAL(20, 2) NULL COMMENT '成交量（手）',
                    amount DECIMAL(20, 2) NULL COMMENT '成交额（万元）',
                    change_pct DECIMAL(10, 4) NULL COMMENT '涨跌幅（%）',
                    raw_json JSON NOT NULL COMMENT '原始数据JSON',
                    created_at DATETIME NOT NULL COMMENT '创建时间',
                    updated_at DATETIME NOT NULL COMMENT '更新时间',
                    UNIQUE KEY uniq_ths_industry (trade_date, industry_code)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='同花顺行业数据日报';
            """))
            conn.commit()
        LOG.info("同花顺行业数据表创建成功")

    def get_ths_industry_data(self, trade_date: str) -> pd.DataFrame:
        """获取同花顺行业数据
        
        Args:
            trade_date: 交易日期，格式为"YYYY-MM-DD"
            
        Returns:
            包含行业数据的DataFrame
        """
        try:
            LOG.info(f"开始获取同花顺行业数据，日期：{trade_date}")
            
            # 使用akshare获取同花顺行业板块数据
            # 注意：这里需要根据akshare的实际函数来获取数据
            # 由于akshare可能会更新API，这里使用可能的函数名
            
            # 优先板块汇总（含总成交量/总成交额，与 ths_industry_di 字段一致）
            df = None
            try:
                df = ak.stock_board_industry_summary_ths()
                LOG.info(f"成功获取同花顺行业板块汇总，共{len(df)}条")
            except Exception as e:
                LOG.warning(f"获取同花顺行业板块汇总失败：{e}")
            if df is None or df.empty:
                try:
                    df = ak.stock_fund_flow_industry(symbol="即时")
                    LOG.info(f"成功获取同花顺行业资金流(即时)，共{len(df)}条")
                except Exception as e:
                    LOG.warning(f"获取同花顺行业资金流失败：{e}")
            if df is None or df.empty:
                try:
                    df = ak.stock_board_industry_spot_em()
                    LOG.info(f"成功获取东方财富行业数据(备选)，共{len(df)}条")
                except Exception as e2:
                    LOG.warning(f"获取东方财富行业数据失败：{e2}")
                    return pd.DataFrame()

            # 处理数据
            if df is not None and not df.empty:
                df = _normalize_ths_industry_columns(df)
                
                # 确保必要的列存在
                if "行业名称" not in df.columns:
                    LOG.warning("数据中缺少必要列：行业名称（及可映射的 行业/板块）")
                    return pd.DataFrame()
                
                # 添加交易日期
                df["trade_date"] = trade_date
                
                # 行业代码：与同花顺资金流一致，来自 stock_board_industry_name_ths 的 code 列
                df = _apply_ths_industry_code_by_name(df)
                
                # 处理成交量和成交额
                for col in ["成交量", "成交额", "涨跌幅"]:
                    if col in df.columns:
                        df[col] = pd.to_numeric(df[col], errors="coerce")
                
                return df
            else:
                LOG.warning("获取到的行业数据为空")
                return pd.DataFrame()
                
        except Exception as e:
            LOG.error(f"获取同花顺行业数据失败：{e}")
            return pd.DataFrame()

    def process_data(self, df: pd.DataFrame, trade_date: str) -> List[Dict[str, Any]]:
        """处理数据
        
        Args:
            df: 原始数据
            trade_date: 交易日期
            
        Returns:
            处理后的数据列表
        """
        records = []
        
        if df is not None and not df.empty:
            for _, row in df.iterrows():
                record = {
                    "trade_date": trade_date,
                    "industry_code": _normalize_industry_code_cell(row.get("行业代码", "")),
                    "industry_name": row.get("行业名称", ""),
                    "volume": row.get("成交量", None),
                    "amount": row.get("成交额", None),
                    "change_pct": row.get("涨跌幅", None),
                    "raw_json": json.dumps(row.to_dict(), ensure_ascii=False),
                    "created_at": datetime.now(),
                    "updated_at": datetime.now()
                }
                records.append(record)
        
        return records

    def save_data(self, records: List[Dict[str, Any]], trade_date: str):
        """保存数据到数据库
        
        Args:
            records: 处理后的数据列表
            trade_date: 本批快照业务日；先删同日旧数据，避免历史错误 industry_code（如 THS_ 前缀）残留。
        """
        if not records:
            LOG.info("没有数据需要保存")
            return
        
        try:
            # 转换为DataFrame
            df = pd.DataFrame(records)
            
            # 保存到数据库
            with self.engine.connect() as conn:
                conn.execute(
                    text("DELETE FROM ths_industry_di WHERE trade_date = :d"),
                    {"d": trade_date},
                )
                conn.commit()
                # 使用replace策略，确保唯一键的记录会被更新
                df.to_sql(
                    "ths_industry_di",
                    conn,
                    if_exists="append",
                    index=False,
                    method="multi"
                )
                conn.commit()
            
            LOG.info(f"成功保存{len(records)}条同花顺行业数据")
            
        except Exception as e:
            LOG.error(f"保存数据失败：{e}")

    def run(self, trade_date: str = None):
        """运行ETL流程
        
        Args:
            trade_date: 交易日期，格式为"YYYY-MM-DD"，默认使用前一个交易日
        """
        # 如果没有指定日期，使用前一个交易日
        if not trade_date:
            today = datetime.now()
            trade_date = (today - timedelta(days=1)).strftime("%Y-%m-%d")
        
        LOG.info(f"开始运行同花顺行业数据ETL，日期：{trade_date}")
        
        # 创建表
        self.create_table()
        
        # 获取数据
        df = self.get_ths_industry_data(trade_date)
        
        # 处理数据
        records = self.process_data(df, trade_date)
        
        # 保存数据
        self.save_data(records, trade_date)
        
        LOG.info(f"同花顺行业数据ETL运行完成，日期：{trade_date}")


if __name__ == "__main__":
    etl = THSIndustryETL()
    etl.run()
