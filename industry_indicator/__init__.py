"""行业指标采集模块。"""

from .industry_fund_flow_etl import run
from .industry_valuation_etl import run as run_industry_valuation
from .industry_financial_indicator_etl import run as run_industry_financial
from .industry_financial_data_etl import run as run_industry_financial_data

__all__ = [
    "run",
    "run_industry_valuation",
    "run_industry_financial",
    "run_industry_financial_data",
]
