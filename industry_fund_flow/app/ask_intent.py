"""自然语言问数：意图解析与参数抽取（规则优先，支持多轮继承）。"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ParsedIntent:
    tool: str
    params: dict[str, Any] = field(default_factory=dict)
    confidence: float = 1.0
    clarify: str | None = None
    follow_up: bool = False


_INTENT_RULES: list[tuple[str, list[str], float]] = [
    ("favorite_boards", ["自选板块", "我的板块", "关注板块", "板块自选", "自选板块表现"], 0.96),
    ("favorite_stocks", ["自选股票", "我的股票", "股票自选", "关注股票", "自选股表现"], 0.96),
    ("start_signal_short", ["短期启动", "短期板块启动", "短线启动", "短期信号"], 0.94),
    ("start_signal_mid", ["中期启动", "中期板块启动", "中期信号", "中线启动"], 0.94),
    ("limit_up_ladder", ["涨停分析", "涨停天梯", "连板", "几板", "封板", "涨停股"], 0.93),
    ("hot_stocks", ["热点股", "热榜", "人气榜", "飙升榜", "东财热榜"], 0.92),
    ("dragon_scores", ["龙头", "龙头股", "龙头是谁", "龙头股票"], 0.95),
    ("quant_mainline_top", ["量化主线"], 0.95),
    ("mainline_rank", ["主线板块", "主线榜", "主线排名", "超级主线"], 0.9),
    ("mainline_rank", ["主线", "top主线"], 0.75),
    ("market_breadth", ["市场广度", "涨跌家数", "跌停家数", "市场怎么样", "大盘情绪", "市场情绪"], 0.9),
    ("market_breadth", ["涨停家数"], 0.85),
    ("fund_flow_rank", ["资金流入", "资金流出", "资金强度", "主力资金", "资金流", "净流入"], 0.9),
]

_FOLLOW_UP_RE = re.compile(
    r"^(那|再|还有|顺便|换成|改|看看|昨天|昨日|今天|今日|最新|top\s*\d+|前\d+).*$|.*呢$|.*吗$",
    re.I,
)

_NOISE_WORDS = re.compile(
    r"(今天|昨日|昨天|最新|请问|帮我|查一下|查询|看看|有哪些|是什么|怎么样|如何|的|了|吗|呢|？|\?)"
)


def _is_follow_up(question: str) -> bool:
    q = question.strip()
    if len(q) <= 14 and _FOLLOW_UP_RE.match(q):
        return True
    if q in ("昨天", "昨日", "今天", "今日", "最新"):
        return True
    return bool(re.match(r"^(top\s*)?\d+$|^\d+\s*个$|^前\s*\d+$", q, re.I))


def _match_tool(question: str) -> tuple[str, float]:
    best_tool = "unknown"
    best_score = 0.0
    for tool, keywords, weight in _INTENT_RULES:
        hits = sum(1 for kw in keywords if kw in question)
        if hits:
            score = weight * hits
            if score > best_score:
                best_score = score
                best_tool = tool
    return best_tool, best_score


def _extract_top(question: str, default: int = 10) -> int:
    for pat in (
        r"top\s*(\d+)",
        r"前\s*(\d+)",
        r"(\d+)\s*名",
        r"(\d+)\s*个",
    ):
        m = re.search(pat, question, re.I)
        if m:
            n = int(m.group(1))
            return max(1, min(n, 50))
    return default


def _extract_content_type(question: str) -> str | None:
    if "概念" in question and "行业" not in question:
        return "概念"
    if "行业" in question and "概念" not in question:
        return "行业"
    return None


def _extract_signal_status(question: str) -> str | None:
    if "观察" in question:
        return "观察"
    if "放弃" in question:
        return "放弃"
    if "启动" in question:
        return "启动"
    return None


def _extract_hot_type(question: str) -> str:
    return "飙升榜" if "飙升" in question else "人气榜"


def _extract_board_keyword(question: str) -> str | None:
    for pat in (
        r"(.+?)(?:板块)?(?:的)?龙头",
        r"(.+?)板块(?:资金|表现|情况)",
        r"(?:查|看)(.+?)板块",
    ):
        m = re.search(pat, question)
        if m:
            kw = _NOISE_WORDS.sub("", m.group(1)).strip()
            if len(kw) >= 2:
                return kw
    cleaned = _NOISE_WORDS.sub("", question)
    for token in (
        "龙头", "主线", "量化", "资金", "市场", "板块", "今天", "昨天",
        "涨停", "热点", "自选", "启动", "信号",
    ):
        cleaned = cleaned.replace(token, "")
    cleaned = cleaned.strip()
    if len(cleaned) >= 2 and len(cleaned) <= 20:
        return cleaned
    return None


def _resolve_trade_date(question: str, explicit: str | None, inherited: str | None = None) -> str | None:
    if explicit:
        return explicit
    if "今天" in question or "今日" in question or "最新" in question:
        return None
    if "昨天" in question or "昨日" in question:
        from app import market_breadth_service as mb_svc

        dates = mb_svc.list_trade_dates(5)
        if len(dates) >= 2:
            return dates[1]
    return inherited


def _unknown_clarify() -> str:
    return (
        "暂未识别您的问题。可尝试：今天主线板块 Top10、我的自选板块表现、"
        "热点股前几名、涨停分析、短期启动信号板块、某板块龙头是谁。"
    )


def parse_intent(
    question: str,
    trade_date: str | None = None,
    *,
    context: dict[str, Any] | None = None,
) -> ParsedIntent:
    q = (question or "").strip()
    if not q:
        return ParsedIntent(tool="unknown", confidence=0.0, clarify="请输入您想查询的问题。")

    follow_up = bool(context) and _is_follow_up(q)
    inherited_params = dict((context or {}).get("params") or {})
    inherited_tool = (context or {}).get("tool") or "unknown"

    matched_tool, matched_score = _match_tool(q)
    if follow_up and matched_score < 0.75:
        best_tool = inherited_tool if inherited_tool != "unknown" else matched_tool
        best_score = 0.8 if inherited_tool != "unknown" else matched_score
    else:
        best_tool = matched_tool
        best_score = matched_score

    if best_tool == "unknown":
        return ParsedIntent(
            tool="unknown",
            confidence=0.0,
            clarify=_unknown_clarify(),
            follow_up=follow_up,
        )

    default_top = int(inherited_params.get("top") or 10)
    if follow_up and re.match(r"^(top\s*)?\d+$|^\d+\s*个$|^前\s*\d+$", q, re.I):
        default_top = _extract_top(q, default_top)

    params: dict[str, Any] = {
        **{k: v for k, v in inherited_params.items() if k != "user_id"},
        "trade_date": _resolve_trade_date(
            q,
            trade_date or inherited_params.get("trade_date"),
            inherited_params.get("trade_date"),
        ),
        "top": _extract_top(q, default_top),
    }
    ct = _extract_content_type(q) or inherited_params.get("content_type")
    if ct:
        params["content_type"] = ct

    if best_tool in ("start_signal_short", "start_signal_mid"):
        status = _extract_signal_status(q) or inherited_params.get("status_filter")
        if status:
            params["status_filter"] = status
        elif follow_up:
            params.setdefault("status_filter", "启动")

    if best_tool == "hot_stocks":
        params["hot_type"] = _extract_hot_type(q)

    if best_tool == "dragon_scores":
        board_kw = _extract_board_keyword(q) or inherited_params.get("board_keyword")
        if context and not board_kw:
            board_kw = context.get("board_keyword") or context.get("industry_name")
        if not board_kw:
            return ParsedIntent(
                tool="dragon_scores",
                params=params,
                confidence=0.5,
                clarify="请说明要查询哪个板块的龙头股，例如：人工智能板块龙头是谁？",
                follow_up=follow_up,
            )
        params["board_keyword"] = board_kw

    confidence = min(1.0, best_score)
    return ParsedIntent(tool=best_tool, params=params, confidence=confidence, follow_up=follow_up)
