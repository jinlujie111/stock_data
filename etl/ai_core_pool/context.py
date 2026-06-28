"""聚合 ODS 资料为 Prompt / 规则引擎上下文。"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine

from etl.ai_core_pool.db_util import get_engine_stock


@dataclass
class StockContext:
    ts_code: str
    stock_name: str | None
    company_intro: str = ""
    main_business: str = ""
    business_scope: str = ""
    mainbz_items: list[dict[str, Any]] = field(default_factory=list)
    mainbz_related_pct: float | None = None
    fina_summary: str = ""
    report_summary: str = ""


def _industry_keywords(industry_name: str) -> list[str]:
    name = industry_name.strip()
    if not name:
        return []
    kws = [name]
    for sep in ("概念", "板块", "行业", "指数"):
        if name.endswith(sep) and len(name) > len(sep):
            kws.append(name[: -len(sep)])
    kws = [k for k in kws if len(k) >= 2]
    return list(dict.fromkeys(kws))


def mainbz_related_ratio(items: list[dict[str, Any]], industry_name: str) -> float | None:
    if not items:
        return None
    keywords = _industry_keywords(industry_name)
    if not keywords:
        return None
    total = sum(float(i.get("bz_sales") or 0) for i in items)
    if total <= 0:
        return None
    related = 0.0
    for item in items:
        text_blob = str(item.get("bz_item") or "")
        if any(kw in text_blob for kw in keywords):
            related += float(item.get("bz_sales") or 0)
    return round(related / total * 100, 2)


def _latest_mainbz(conn, ts_code: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        text(
            """
            SELECT end_date, bz_item, bz_sales, bz_profit
            FROM ods_fina_mainbz_di
            WHERE ts_code = :c AND bz_type = 'P'
              AND end_date = (
                  SELECT MAX(end_date) FROM ods_fina_mainbz_di
                  WHERE ts_code = :c AND bz_type = 'P'
              )
            ORDER BY bz_sales DESC
            LIMIT 20
            """
        ),
        {"c": ts_code},
    ).mappings().all()
    return [dict(r) for r in rows]


def _fina_summary(conn, ts_code: str) -> str:
    row = conn.execute(
        text(
            """
            SELECT end_date, tr_yoy, netprofit_yoy, roe, grossprofit_margin
            FROM ods_fina_indicator
            WHERE ts_code = :c
            ORDER BY end_date DESC
            LIMIT 1
            """
        ),
        {"c": ts_code},
    ).mappings().first()
    if not row:
        return ""
    return (
        f"报告期{row['end_date']}: 营收同比{row.get('tr_yoy')}%, "
        f"净利同比{row.get('netprofit_yoy')}%, ROE={row.get('roe')}%"
    )


def _report_summary(conn, ts_code: str, trade_date: date) -> str:
    rows = conn.execute(
        text(
            """
            SELECT report_date, org_name, report_title, rating, quarter
            FROM ods_report_rc_di
            WHERE ts_code = :c
              AND report_date >= DATE_SUB(:td, INTERVAL 90 DAY)
              AND report_date <= :td
            ORDER BY report_date DESC
            LIMIT 5
            """
        ),
        {"c": ts_code, "td": trade_date},
    ).mappings().all()
    parts = []
    for r in rows:
        title = (r.get("report_title") or "")[:80]
        parts.append(f"{r.get('report_date')} {r.get('org_name') or ''} {title}")
    return "；".join(parts)


def collect_context(
    ts_code: str,
    stock_name: str | None,
    industry_name: str,
    trade_date: date,
    engine: Engine | None = None,
) -> StockContext:
    eng = engine or get_engine_stock()
    ctx = StockContext(ts_code=ts_code, stock_name=stock_name)
    with eng.connect() as conn:
        co = conn.execute(
            text(
                """
                SELECT introduction, main_business, business_scope
                FROM ods_stock_company_di WHERE ts_code = :c LIMIT 1
                """
            ),
            {"c": ts_code},
        ).mappings().first()
        if co:
            ctx.company_intro = (co.get("introduction") or "")[:2000]
            ctx.main_business = (co.get("main_business") or "")[:1000]
            ctx.business_scope = (co.get("business_scope") or "")[:1000]
        ctx.mainbz_items = _latest_mainbz(conn, ts_code)
        ctx.fina_summary = _fina_summary(conn, ts_code)
        ctx.report_summary = _report_summary(conn, ts_code, trade_date)
    ctx.mainbz_related_pct = mainbz_related_ratio(ctx.mainbz_items, industry_name)
    return ctx


def mainbz_json_for_prompt(ctx: StockContext) -> str:
    slim = [
        {
            "bz_item": i.get("bz_item"),
            "bz_sales": float(i["bz_sales"]) if i.get("bz_sales") is not None else None,
        }
        for i in ctx.mainbz_items[:10]
    ]
    return json.dumps(slim, ensure_ascii=False)


def render_prompt(industry_name: str, ctx: StockContext, version: str = "v1") -> str:
    stock_label = ctx.stock_name or ctx.ts_code
    mainbz_note = ""
    if ctx.mainbz_related_pct is not None:
        mainbz_note = f"\n【赛道相关主营占比估算】{ctx.mainbz_related_pct}%"
    return f"""你是一名资深产业分析师。
行业/赛道：{industry_name}
公司：{stock_label}（{ctx.ts_code}）

【公司简介】{(ctx.company_intro or '无')[:800]}
【主营业务】{(ctx.main_business or '无')[:500]}
【经营范围】{(ctx.business_scope or '无')[:300]}
【财报业务构成】{mainbz_json_for_prompt(ctx)}
【财务概览】{ctx.fina_summary or '无'}
【近90日研报摘要】{ctx.report_summary or '无'}{mainbz_note}

请仅输出 JSON（不要 markdown 代码块），字段：
{{
  "industry_match": boolean,
  "segment": string,
  "core_degree": string,
  "score": number,
  "reason": string
}}
prompt_version={version}
"""


def text_corpus(ctx: StockContext) -> str:
    return " ".join(
        filter(
            None,
            [
                ctx.company_intro,
                ctx.main_business,
                ctx.business_scope,
                ctx.fina_summary,
                ctx.report_summary,
            ],
        )
    )
