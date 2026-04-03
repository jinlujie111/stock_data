"""行业指标采集模块。"""

from .industry_fund_flow_etl import run
from .industry_valuation_etl import run as run_industry_valuation
from .industry_financial_indicator_etl import run as run_industry_financial
from .industry_financial_data_etl import run as run_industry_financial_data
from .industry_order_volume_etl import run as run_industry_order_volume
from .industry_contract_liab_yoy_etl import run as run_industry_contract_liab_yoy
from .industry_association_shipment_etl import run as run_industry_association_shipment
from .industry_sw_universe_etl import run as run_industry_sw_universe

__all__ = [
    "run",
    "run_industry_valuation",
    "run_industry_financial",
    "run_industry_financial_data",
    "run_industry_order_volume",
    "run_industry_contract_liab_yoy",
    "run_industry_association_shipment",
    "run_industry_sw_universe",
]
