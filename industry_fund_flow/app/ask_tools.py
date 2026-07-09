"""问数工具：映射到现有 service，不直接写 SQL。"""
from __future__ import annotations

from typing import Any

from app import dragon_service as dragon_svc
from app import favorite_service as fav_svc
from app import fund_flow_service as ff_svc
from app import hot_stock_service as hot_svc
from app import limit_up_service as lu_svc
from app import mainline_service as ml_svc
from app import market_breadth_service as mb_svc
from app import quant_mainline_service as qm_svc
from app import start_signal_service as ss_svc

TOOL_SOURCES: dict[str, dict[str, str]] = {
    "mainline_rank": {"title": "主线板块", "href": "/dc/mainline"},
    "quant_mainline_top": {"title": "量化主线", "href": "/dc/quant-mainline"},
    "market_breadth": {"title": "市场广度", "href": "/"},
    "fund_flow_rank": {"title": "资金强度", "href": "/dc/fund-flow"},
    "dragon_scores": {"title": "板块龙头", "href": "/dc/dragon"},
    "favorite_boards": {"title": "板块自选", "href": "/favorites/boards"},
    "favorite_stocks": {"title": "股票自选", "href": "/favorites/stocks"},
    "hot_stocks": {"title": "热点股预览", "href": "/dc/hot-stocks"},
    "limit_up_ladder": {"title": "涨停分析", "href": "/dc/limit-up"},
    "start_signal_short": {"title": "VIP-短期板块启动", "href": "/vip/start-short"},
    "start_signal_mid": {"title": "VIP-中期板块启动", "href": "/vip/start-mid"},
}

SUGGESTIONS: list[str] = [
    "今天主线板块 Top10 有哪些？",
    "我的自选板块今天表现怎么样？",
    "今天热点股人气榜前 10？",
    "今天有哪些涨停连板？",
    "短期启动信号板块有哪些？",
    "人工智能板块龙头是谁？",
    "昨天呢？",
]


def _content_types_param(content_type: str | None) -> list[str] | None:
    if content_type in ("行业", "概念"):
        return [content_type]
    return None


def _require_user_id(params: dict[str, Any]) -> int:
    user_id = params.get("user_id")
    if not user_id:
        raise ValueError("需要登录后才能查询自选数据。")
    return int(user_id)


def run_mainline_rank(params: dict[str, Any]) -> dict[str, Any]:
    return ml_svc.get_rank(
        trade_date=params.get("trade_date"),
        content_types=_content_types_param(params.get("content_type")),
        top=int(params.get("top") or 10),
    )


def run_quant_mainline_top(params: dict[str, Any]) -> dict[str, Any]:
    ct = params.get("content_type") or "行业"
    return qm_svc.get_top(
        trade_date=params.get("trade_date"),
        content_types=[ct],
        top=int(params.get("top") or 10),
    )


def run_market_breadth(params: dict[str, Any]) -> dict[str, Any]:
    return mb_svc.get_market_breadth(params.get("trade_date"))


def run_fund_flow_rank(params: dict[str, Any]) -> dict[str, Any]:
    return ff_svc.get_board_flow_top5(
        trade_date=params.get("trade_date"),
        content_types=_content_types_param(params.get("content_type")),
    )


def run_dragon_scores(params: dict[str, Any]) -> dict[str, Any]:
    keyword = (params.get("board_keyword") or "").strip()
    if not keyword:
        raise ValueError("缺少板块名称")
    trade_date = params.get("trade_date")
    boards = dragon_svc.list_boards(trade_date, keyword=keyword)
    if not boards:
        raise ValueError(f"未找到名称含「{keyword}」的板块，请换个名称试试。")
    if len(boards) > 1:
        names = "、".join(b["industry_name"] for b in boards[:5])
        extra = f"等{len(boards)}个" if len(boards) > 5 else ""
        raise ValueError(f"匹配到多个板块：{names}{extra}，请说得更具体一些。")
    board = boards[0]
    scores = dragon_svc.get_board_scores(
        board["industry_code"],
        trade_date=trade_date,
        top=int(params.get("top") or 5),
    )
    return {
        "trade_date": scores["trade_date"],
        "industry_code": scores["industry_code"],
        "industry_name": scores["industry_name"],
        "content_type": scores.get("content_type"),
        "items": scores["items"],
    }


def run_favorite_boards(params: dict[str, Any]) -> dict[str, Any]:
    user_id = _require_user_id(params)
    td = params.get("trade_date")
    items = fav_svc.list_board_favorites(user_id, td)
    if not items:
        return {"trade_date": td, "items": [], "count": 0}
    resolved_td = td or mb_svc.latest_trade_date()
    if not td and items:
        items = fav_svc.list_board_favorites(user_id, resolved_td)
    return {
        "trade_date": resolved_td,
        "count": len(items),
        "items": items[: int(params.get("top") or 50)],
    }


def run_favorite_stocks(params: dict[str, Any]) -> dict[str, Any]:
    user_id = _require_user_id(params)
    td = params.get("trade_date")
    items = fav_svc.list_stock_favorites(user_id, td)
    return {
        "trade_date": td or mb_svc.latest_trade_date(),
        "count": len(items),
        "items": items[: int(params.get("top") or 50)],
    }


def run_hot_stocks(params: dict[str, Any]) -> dict[str, Any]:
    return hot_svc.get_hot_stocks(
        trade_date=params.get("trade_date"),
        hot_type=params.get("hot_type") or "人气榜",
        limit=int(params.get("top") or 10),
    )


def run_limit_up_ladder(params: dict[str, Any]) -> dict[str, Any]:
    data = lu_svc.get_limit_up_ladder(params.get("trade_date"))
    top = int(params.get("top") or 20)
    groups = []
    shown = 0
    for g in data.get("groups") or []:
        if shown >= top:
            break
        items = g.get("items") or []
        take = items[: max(0, top - shown)]
        shown += len(take)
        groups.append({**g, "items": take, "count": len(take)})
    return {
        "trade_date": data.get("trade_date"),
        "total": data.get("total"),
        "groups": groups,
    }


def run_start_signal(params: dict[str, Any], *, mode: str) -> dict[str, Any]:
    ct = params.get("content_type")
    content_types = f"{ct}" if ct else "行业,概念"
    return ss_svc.evaluate(
        params.get("trade_date"),
        mode=mode,
        content_types=content_types,
        status_filter=params.get("status_filter"),
        top=int(params.get("top") or 15),
    )


def run_start_signal_short(params: dict[str, Any]) -> dict[str, Any]:
    return run_start_signal(params, mode=ss_svc.MODE_SHORT)


def run_start_signal_mid(params: dict[str, Any]) -> dict[str, Any]:
    return run_start_signal(params, mode=ss_svc.MODE_MID)


_RUNNERS = {
    "mainline_rank": run_mainline_rank,
    "quant_mainline_top": run_quant_mainline_top,
    "market_breadth": run_market_breadth,
    "fund_flow_rank": run_fund_flow_rank,
    "dragon_scores": run_dragon_scores,
    "favorite_boards": run_favorite_boards,
    "favorite_stocks": run_favorite_stocks,
    "hot_stocks": run_hot_stocks,
    "limit_up_ladder": run_limit_up_ladder,
    "start_signal_short": run_start_signal_short,
    "start_signal_mid": run_start_signal_mid,
}


def execute_tool(tool: str, params: dict[str, Any]) -> dict[str, Any]:
    runner = _RUNNERS.get(tool)
    if not runner:
        raise ValueError(f"未知工具: {tool}")
    return runner(params)


def tool_source(tool: str) -> dict[str, str] | None:
    return TOOL_SOURCES.get(tool)
