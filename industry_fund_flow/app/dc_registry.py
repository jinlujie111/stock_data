"""东财五维 DWM 维度配置（列表列定义、表名、默认排序）。"""
from __future__ import annotations

from typing import TypedDict


class ColumnDef(TypedDict, total=False):
    key: str
    label: str
    fmt: str
    sortable: bool


class DimensionDef(TypedDict, total=False):
    slug: str
    title: str
    subtitle: str
    table: str
    order_by: str
    columns: list[ColumnDef]
    sort_hint: str
    default_sort_key: str
    default_sort_dir: str


_COMMON: list[ColumnDef] = [
    {"key": "content_type", "label": "板块类型", "fmt": "text"},
    {"key": "industry_code", "label": "板块代码", "fmt": "text"},
    {"key": "industry_name", "label": "板块名称", "fmt": "text"},
]

DC_DIMENSIONS: dict[str, DimensionDef] = {
    "fund-flow": {
        "slug": "fund-flow",
        "title": "资金强度",
        "subtitle": "东方财富 · 板块主力资金与流入强度",
        "table": "dwm_dc_industry_fund_flow_di",
        "order_by": "dc_rank IS NULL, dc_rank ASC",
        "sort_hint": "默认按资金流排名从小到大；点击表头可排序",
        "default_sort_key": "dc_rank",
        "default_sort_dir": "asc",
        "columns": _COMMON
        + [
            {"key": "net_amount_wan", "label": "主力净流入(亿)", "fmt": "yi", "sortable": True},
            {"key": "net_amount_rate", "label": "主力净流入占比", "fmt": "pct2", "sortable": True},
            {"key": "fund_inflow_strength", "label": "资金流入强度", "fmt": "strength4", "sortable": True},
            {"key": "net_inflow_days", "label": "连续净流入天数", "fmt": "days", "sortable": True},
            {"key": "fund_accel", "label": "资金加速度(亿)", "fmt": "yi_accel", "sortable": True},
            {"key": "elg_net_ratio", "label": "超大单占比", "fmt": "pct2", "sortable": True},
            {"key": "pct_change", "label": "涨跌幅", "fmt": "pct2", "sortable": True},
            {"key": "dc_rank", "label": "资金流排名", "fmt": "int", "sortable": True},
        ],
    },
    "trend-strength": {
        "slug": "trend-strength",
        "title": "趋势强度",
        "subtitle": "东方财富 · 相对强弱与均线结构",
        "table": "dwm_dc_industry_trend_strength_di",
        "order_by": "rs_rank IS NULL, rs_rank ASC",
        "columns": _COMMON
        + [
            {"key": "close", "label": "收盘点位", "fmt": "num"},
            {"key": "pct_change", "label": "涨跌幅(%)", "fmt": "pct"},
            {"key": "rs_5d", "label": "5日相对强弱(%)", "fmt": "pct"},
            {"key": "rs_20d", "label": "20日相对强弱(%)", "fmt": "pct"},
            {"key": "ma_bullish", "label": "均线多头", "fmt": "bool"},
            {"key": "is_new_high_60d", "label": "60日新高", "fmt": "bool"},
            {"key": "drawdown_pct", "label": "回撤(%)", "fmt": "pct"},
            {"key": "recovery_days", "label": "恢复天数", "fmt": "int"},
            {"key": "rs_rank", "label": "RS排名", "fmt": "int"},
        ],
    },
    "market-heat": {
        "slug": "market-heat",
        "title": "市场热度",
        "subtitle": "东方财富 · 成交额占比与涨停扩散",
        "table": "dwm_dc_industry_market_heat_di",
        "order_by": "heat_rank IS NULL, heat_rank ASC",
        "columns": _COMMON
        + [
            {"key": "constituent_cnt", "label": "成分股数", "fmt": "int"},
            {"key": "amount_ratio", "label": "成交额占比", "fmt": "pct"},
            {"key": "board_amount", "label": "板块成交额(元)", "fmt": "num"},
            {"key": "limit_up_cnt", "label": "涨停家数", "fmt": "int"},
            {"key": "limit_up_ratio", "label": "涨停扩散率", "fmt": "pct"},
            {"key": "up_ratio", "label": "上涨占比", "fmt": "pct"},
            {"key": "turnover_rate", "label": "换手率(%)", "fmt": "pct"},
            {"key": "pct_change", "label": "涨跌幅(%)", "fmt": "pct"},
            {"key": "dc_hot_rank", "label": "热度排名", "fmt": "int"},
            {"key": "heat_rank", "label": "成交额排名", "fmt": "int"},
        ],
    },
    "prosperity": {
        "slug": "prosperity",
        "title": "产业景气",
        "subtitle": "东方财富 · 业绩增速与卖方预期",
        "table": "dwm_dc_industry_prosperity_di",
        "order_by": "prosperity_rank IS NULL, prosperity_rank ASC",
        "columns": _COMMON
        + [
            {"key": "constituent_cnt", "label": "成分股数", "fmt": "int"},
            {"key": "fina_coverage_cnt", "label": "有财报成分数", "fmt": "int"},
            {"key": "earnings_yoy", "label": "净利同比(%)", "fmt": "pct"},
            {"key": "earnings_q_yoy", "label": "单季净利同比(%)", "fmt": "pct"},
            {"key": "roe_avg", "label": "ROE均值(%)", "fmt": "pct"},
            {"key": "forecast_rev_pct", "label": "预期修正(%)", "fmt": "pct"},
            {"key": "upgrade_ratio", "label": "上调评级占比", "fmt": "pct"},
            {"key": "report_cnt_30d", "label": "近30日研报数", "fmt": "int"},
            {"key": "prosperity_rank", "label": "景气排名", "fmt": "int"},
        ],
    },
    "diffusion": {
        "slug": "diffusion",
        "title": "扩散效应",
        "subtitle": "东方财富 · 涨跌扩散与连板晋级",
        "table": "dwm_dc_industry_diffusion_di",
        "order_by": "diffusion_rank IS NULL, diffusion_rank ASC",
        "columns": _COMMON
        + [
            {"key": "constituent_cnt", "label": "成分股数", "fmt": "int"},
            {"key": "up_ratio", "label": "上涨占比", "fmt": "pct"},
            {"key": "down_ratio", "label": "下跌占比", "fmt": "pct"},
            {"key": "limit_up_cnt", "label": "涨停家数", "fmt": "int"},
            {"key": "limit_up_ratio", "label": "涨停扩散率", "fmt": "pct"},
            {"key": "continue_limit_ratio", "label": "晋级率", "fmt": "pct"},
            {"key": "blast_ratio", "label": "炸板率", "fmt": "pct"},
            {"key": "board_success_ratio", "label": "封板成功率", "fmt": "pct"},
            {"key": "max_limit_times", "label": "最高连板", "fmt": "int"},
            {"key": "up_vs_market", "label": "相对全市场", "fmt": "num"},
            {"key": "diffusion_rank", "label": "扩散排名", "fmt": "int"},
        ],
    },
}

CONTENT_TYPES = ["行业", "概念"]

# 已下线 Web 入口（ODS 同步仍保留；相关 DWM 日批已停）
DISABLED_DC_SLUGS = frozenset(
    {
        "fund-flow",
        "trend-strength",
        "market-heat",
        "prosperity",
        "diffusion",
    }
)

# 决策链路整段下线（页面 404）；板块择时保留；timing-kline 302 → board-timing
RETIRED_DC_PAGES = frozenset(
    {
        "mainline",
        "dragon",
        "sectors",
        "kline",
        "volume-price",
    }
)

# 非东财维度页的 /dc/* 路径（由独立 page_router 处理，勿落入 /dc/{slug}）
RESERVED_DC_PAGE_SLUGS = frozenset(
    {
        "mainline",
        "dragon",
        "sectors",
        "kline",
        "volume-price",
        "board-timing",
        "timing-kline",  # 302 → board-timing
    }
)

# 产品主脊：板块择时（买卖点+回测）。决策链路/龙头已下线；ODS 同步不停。
_NAV_RAW: list[dict[str, str]] = [
    {"slug": "board-timing", "label": "板块择时", "href": "/dc/board-timing", "section": "板块择时"},
    {"slug": "board-favorites", "label": "板块自选", "href": "/favorites/boards", "section": "我的自选"},
]


def _build_nav_sections(raw: list[dict[str, str]]) -> list[dict]:
    sections: list[dict] = []
    index: dict[str, int] = {}
    for item in raw:
        title = item["section"]
        if title not in index:
            index[title] = len(sections)
            sections.append({"title": title, "items": []})
        sections[index[title]]["items"].append(
            {k: v for k, v in item.items() if k != "section"}
        )
    return sections


NAV_TOP_ITEMS: list[dict[str, str]] = []
NAV_ITEMS = [{k: v for k, v in item.items() if k != "section"} for item in _NAV_RAW]
NAV_SECTIONS = _build_nav_sections(_NAV_RAW)


def get_dimension(slug: str) -> DimensionDef:
    dim = DC_DIMENSIONS.get(slug)
    if not dim:
        raise KeyError(slug)
    return dim
