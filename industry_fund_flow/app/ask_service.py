"""问数编排：解析 → 取数 → 汇总（支持多轮会话）。"""
from __future__ import annotations

import json
import logging
from typing import Any

from app.ask_intent import ParsedIntent, parse_intent
from app.ask_llm import chat_text, llm_available
from app.ask_session import append_turn, ensure_session, get_last_turn
from app.ask_tools import SUGGESTIONS, execute_tool, tool_source

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "你是 A 股板块数据助手。只能根据用户提供的 JSON 数据回答，禁止编造数字。"
    "用中文写 3-6 句结论，可加 2-4 条要点。必须注明 trade_date。"
    "若数据为空，明确说明暂无数据。若提供了对话上下文，可结合上下文理解追问。"
)


def list_suggestions() -> list[str]:
    return list(SUGGESTIONS)


def _session_context(session_id: str | None, user_id: int) -> dict[str, Any] | None:
    last = get_last_turn(session_id, user_id)
    if not last:
        return None
    ctx: dict[str, Any] = {
        "tool": last.get("tool"),
        "params": dict(last.get("params") or {}),
    }
    data = last.get("data") or {}
    if isinstance(data, dict):
        ctx["trade_date"] = data.get("trade_date")
        ctx["board_keyword"] = data.get("industry_name") or last.get("params", {}).get("board_keyword")
        ctx["industry_name"] = data.get("industry_name")
    return ctx


def _turn_context(intent: ParsedIntent, data: dict[str, Any] | None) -> dict[str, Any]:
    ctx: dict[str, Any] = {
        "tool": intent.tool,
        "params": dict(intent.params),
    }
    if isinstance(data, dict):
        ctx["data"] = {
            "trade_date": data.get("trade_date"),
            "industry_name": data.get("industry_name"),
        }
        if data.get("industry_name"):
            ctx["params"]["board_keyword"] = data["industry_name"]
    return ctx


def _compact_data(tool: str, data: dict[str, Any]) -> dict[str, Any]:
    if tool == "mainline_rank":
        return {
            "trade_date": data.get("trade_date"),
            "items": [
                {
                    "rank": i.get("rank"),
                    "industry_name": i.get("industry_name"),
                    "mainline_level": i.get("mainline_level"),
                    "main_score": i.get("main_score"),
                }
                for i in (data.get("items") or [])[:15]
            ],
        }
    if tool == "quant_mainline_top":
        return {
            "trade_date": data.get("trade_date"),
            "content_type": data.get("content_type"),
            "items": [
                {
                    "rank_no": i.get("rank_no"),
                    "industry_name": i.get("industry_name"),
                    "display_score": i.get("display_score"),
                }
                for i in (data.get("items") or [])[:15]
            ],
        }
    if tool == "market_breadth":
        return {"trade_date": data.get("trade_date"), "data": data.get("data")}
    if tool == "fund_flow_rank":
        return {
            "trade_date": data.get("trade_date"),
            "inflow": (data.get("inflow") or [])[:5],
            "outflow": (data.get("outflow") or [])[:5],
        }
    if tool == "dragon_scores":
        return {
            "trade_date": data.get("trade_date"),
            "industry_name": data.get("industry_name"),
            "items": [
                {
                    "stock_name": i.get("stock_name"),
                    "score_composite": i.get("score_composite"),
                }
                for i in (data.get("items") or [])[:10]
            ],
        }
    if tool == "favorite_boards":
        return {
            "trade_date": data.get("trade_date"),
            "count": data.get("count"),
            "items": [
                {
                    "industry_name": i.get("industry_name"),
                    "pct_change": i.get("pct_change"),
                    "net_amount_yi": i.get("net_amount_yi"),
                }
                for i in (data.get("items") or [])[:20]
            ],
        }
    if tool == "favorite_stocks":
        return {
            "trade_date": data.get("trade_date"),
            "count": data.get("count"),
            "items": [
                {
                    "stock_name": i.get("stock_name"),
                    "ts_code": i.get("ts_code"),
                    "pct_chg": i.get("pct_chg"),
                    "close": i.get("close"),
                }
                for i in (data.get("items") or [])[:20]
            ],
        }
    if tool == "hot_stocks":
        return {
            "trade_date": data.get("trade_date"),
            "hot_type": data.get("hot_type"),
            "items": [
                {
                    "dc_rank": i.get("dc_rank"),
                    "ts_name": i.get("ts_name"),
                    "pct_change": i.get("pct_change"),
                }
                for i in (data.get("items") or [])[:15]
            ],
        }
    if tool == "limit_up_ladder":
        flat = []
        for g in data.get("groups") or []:
            for i in g.get("items") or []:
                flat.append(
                    {
                        "name": i.get("name"),
                        "industry": i.get("industry"),
                        "stat_text": i.get("stat_text"),
                    }
                )
        return {
            "trade_date": data.get("trade_date"),
            "total": data.get("total"),
            "items": flat[:20],
        }
    if tool in ("start_signal_short", "start_signal_mid"):
        return {
            "trade_date": data.get("trade_date"),
            "mode_label": data.get("mode_label"),
            "summary": data.get("summary"),
            "items": [
                {
                    "industry_name": i.get("industry_name"),
                    "signal_status": i.get("signal_status"),
                    "total_score": i.get("total_score"),
                    "leader_name": i.get("leader_name"),
                }
                for i in (data.get("items") or [])[:15]
            ],
        }
    return data


def _template_answer(tool: str, data: dict[str, Any]) -> str:
    td = data.get("trade_date") or "最新交易日"
    if tool == "mainline_rank":
        items = data.get("items") or []
        if not items:
            return f"截至 {td}，暂无主线板块数据。"
        names = "、".join(
            f"{i.get('industry_name')}({i.get('mainline_level') or '-'})" for i in items[:5]
        )
        return f"截至 {td}，主线板块前 {len(items)} 名中，靠前包括：{names}。"
    if tool == "quant_mainline_top":
        items = data.get("items") or []
        if not items:
            return f"截至 {td}，暂无量化主线数据。"
        names = "、".join(i.get("industry_name", "-") for i in items[:5])
        ct = data.get("content_type") or "板块"
        return f"截至 {td}，{ct}量化主线前 {len(items)} 名包括：{names}。"
    if tool == "market_breadth":
        row = data.get("data")
        if not row:
            return f"截至 {td}，暂无市场广度数据。"
        return (
            f"截至 {td}，上涨 {row.get('advance_cnt', '-')} 家、"
            f"下跌 {row.get('decline_cnt', '-')} 家、平盘 {row.get('flat_cnt', '-')} 家；"
            f"涨停 {row.get('limit_up_cnt', '-')} 家、跌停 {row.get('limit_down_cnt', '-')} 家。"
        )
    if tool == "fund_flow_rank":
        inflow = data.get("inflow") or []
        outflow = data.get("outflow") or []
        if not inflow and not outflow:
            return f"截至 {td}，暂无资金流向数据。"
        in_names = "、".join(
            f"{i.get('industry_name')}({i.get('net_amount_yi')}亿)" for i in inflow[:3]
        )
        out_names = "、".join(
            f"{i.get('industry_name')}({i.get('net_amount_yi')}亿)" for i in outflow[:3]
        )
        return f"截至 {td}，主力净流入前三：{in_names or '无'}；净流出前三：{out_names or '无'}。"
    if tool == "dragon_scores":
        items = data.get("items") or []
        board = data.get("industry_name") or "该板块"
        if not items:
            return f"截至 {td}，{board} 暂无龙头评分数据。"
        names = "、".join(
            f"{i.get('stock_name')}({i.get('score_composite', '-')})" for i in items[:3]
        )
        return f"截至 {td}，{board} 综合得分靠前的个股：{names}。"
    if tool == "favorite_boards":
        items = data.get("items") or []
        if not items:
            return "您还没有添加板块自选，可前往「板块自选」页面添加。"
        up = sum(1 for i in items if (i.get("pct_change") or 0) > 0)
        down = sum(1 for i in items if (i.get("pct_change") or 0) < 0)
        best = max(items, key=lambda x: x.get("pct_change") or -999)
        worst = min(items, key=lambda x: x.get("pct_change") or 999)
        return (
            f"截至 {td}，您关注了 {len(items)} 个板块：{up} 涨 {down} 跌。"
            f"涨幅最高 {best.get('industry_name')}({best.get('pct_change', '-')}%)，"
            f"跌幅最大 {worst.get('industry_name')}({worst.get('pct_change', '-')}%)。"
        )
    if tool == "favorite_stocks":
        items = data.get("items") or []
        if not items:
            return "您还没有添加股票自选，可前往「股票自选」页面添加。"
        up = sum(1 for i in items if (i.get("pct_chg") or 0) > 0)
        down = sum(1 for i in items if (i.get("pct_chg") or 0) < 0)
        return f"截至 {td}，您关注了 {len(items)} 只股票：{up} 涨 {down} 跌。"
    if tool == "hot_stocks":
        items = data.get("items") or []
        ht = data.get("hot_type") or "人气榜"
        if not items:
            return f"截至 {td}，暂无{ht}数据。"
        names = "、".join(f"{i.get('ts_name')}({i.get('pct_change', '-')}%)" for i in items[:5])
        return f"截至 {td}，{ht}前 {len(items)} 名包括：{names}。"
    if tool == "limit_up_ladder":
        total = data.get("total") or 0
        if total == 0:
            return f"截至 {td}，暂无涨停数据。"
        parts = []
        for g in (data.get("groups") or [])[:4]:
            if g.get("count"):
                parts.append(f"{g.get('label')}{g.get('count')}只")
        ladder = "、".join(parts) if parts else "详见明细"
        return f"截至 {td}，共 {total} 只涨停股，分布：{ladder}。"
    if tool in ("start_signal_short", "start_signal_mid"):
        items = data.get("items") or []
        label = data.get("mode_label") or "启动"
        summary = data.get("summary") or {}
        if not items:
            return f"截至 {td}，暂无{label}启动信号板块。"
        names = "、".join(
            f"{i.get('industry_name')}({i.get('signal_status')})" for i in items[:5]
        )
        return (
            f"截至 {td}，{label}信号板块共 {len(items)} 个（启动{summary.get('启动', 0)}、"
            f"观察{summary.get('观察', 0)}），靠前：{names}。"
        )
    return "查询完成，请查看下方数据明细。"


def _summarize(
    question: str,
    tool: str,
    data: dict[str, Any],
    *,
    history: list[dict[str, str]] | None = None,
) -> tuple[str, bool]:
    compact = _compact_data(tool, data)
    if llm_available():
        try:
            hist_text = ""
            if history:
                hist_text = "对话上下文：\n" + json.dumps(history, ensure_ascii=False) + "\n\n"
            answer = chat_text(
                _SYSTEM_PROMPT,
                f"{hist_text}用户问题：{question}\n\n数据（JSON）：\n{json.dumps(compact, ensure_ascii=False)}",
            )
            if answer.strip():
                return answer.strip(), True
        except Exception as exc:
            logger.warning("LLM 汇总失败，回退模板: %s", exc)
    return _template_answer(tool, data), False


def _history_for_llm(session_id: str | None, user_id: int) -> list[dict[str, str]]:
    last = get_last_turn(session_id, user_id)
    if not last:
        return []
    return [
        {
            "question": last.get("question", ""),
            "intent": last.get("tool", ""),
            "answer_preview": (last.get("answer") or "")[:200],
        }
    ]


def ask(
    question: str,
    trade_date: str | None = None,
    *,
    session_id: str | None = None,
    user_id: int | None = None,
) -> dict[str, Any]:
    uid = int(user_id or 0)
    sid = ensure_session(session_id, uid) if uid else (session_id or "")
    context = _session_context(sid, uid) if sid and uid else None

    intent: ParsedIntent = parse_intent(question, trade_date, context=context)
    params = dict(intent.params)
    if uid:
        params["user_id"] = uid

    if intent.clarify and intent.confidence < 0.6:
        return {
            "answer": intent.clarify,
            "intent": intent.tool,
            "params": params,
            "data": None,
            "sources": [],
            "trade_date": params.get("trade_date"),
            "llm_used": False,
            "needs_clarify": True,
            "follow_up": intent.follow_up,
            "session_id": sid or None,
        }

    try:
        data = execute_tool(intent.tool, params)
    except ValueError as exc:
        return {
            "answer": str(exc),
            "intent": intent.tool,
            "params": params,
            "data": None,
            "sources": [tool_source(intent.tool)] if tool_source(intent.tool) else [],
            "trade_date": params.get("trade_date"),
            "llm_used": False,
            "needs_clarify": True,
            "follow_up": intent.follow_up,
            "session_id": sid or None,
        }

    resolved_td = data.get("trade_date") if isinstance(data, dict) else None
    history = _history_for_llm(sid, uid) if intent.follow_up else None
    answer, llm_used = _summarize(question, intent.tool, data, history=history)
    source = tool_source(intent.tool)

    if sid and uid:
        append_turn(
            sid,
            uid,
            {
                "question": question.strip(),
                "tool": intent.tool,
                "params": params,
                "data": data if isinstance(data, dict) else None,
                "answer": answer,
            },
        )

    return {
        "answer": answer,
        "intent": intent.tool,
        "params": params,
        "data": data,
        "sources": [source] if source else [],
        "trade_date": resolved_td,
        "llm_used": llm_used,
        "needs_clarify": False,
        "follow_up": intent.follow_up,
        "session_id": sid or None,
    }
