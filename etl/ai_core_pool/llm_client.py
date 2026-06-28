"""LLM 调用与规则引擎兜底。"""
from __future__ import annotations

import json
import logging
import os
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from mysql_config import load_llm_token

from etl.ai_core_pool.context import StockContext, render_prompt, text_corpus, _industry_keywords
from etl.ai_core_pool.db_util import AiCoreConfig
from etl.ai_core_pool.rules import AiScoreRow

logger = logging.getLogger(__name__)


@dataclass
class LlmCredentials:
    provider: str
    model_name: str
    api_url: str
    api_key: str
    source: str  # db_llm_token | env


def resolve_llm_credentials(cfg: AiCoreConfig) -> LlmCredentials | None:
    """优先 data_config.db_llm_token，其次环境变量。"""
    row = load_llm_token(
        provider=cfg.llm_provider or None,
        model_name=cfg.model_name or None,
    )
    if row and str(row.get("api_key") or "").strip() not in ("", "REPLACE_WITH_YOUR_KEY"):
        api_url = str(row["api_url"]).rstrip("/")
        return LlmCredentials(
            provider=str(row["provider"]),
            model_name=str(row["model_name"]),
            api_url=api_url,
            api_key=str(row["api_key"]).strip(),
            source="db_llm_token",
        )

    api_url = (
        os.getenv("AI_CORE_LLM_API_URL")
        or os.getenv("OPENAI_API_BASE")
        or ""
    ).rstrip("/")
    api_key = (os.getenv("AI_CORE_LLM_API_KEY") or os.getenv("OPENAI_API_KEY") or "").strip()
    env_model = os.getenv("AI_CORE_LLM_MODEL") or cfg.model_name
    if api_key and api_url:
        return LlmCredentials(
            provider=os.getenv("AI_CORE_LLM_PROVIDER") or "env",
            model_name=env_model,
            api_url=api_url,
            api_key=api_key,
            source="env",
        )
    if api_key:
        return LlmCredentials(
            provider=os.getenv("AI_CORE_LLM_PROVIDER") or "env",
            model_name=env_model,
            api_url=api_url or "https://api.openai.com/v1",
            api_key=api_key,
            source="env",
        )
    return None


def llm_available(cfg: AiCoreConfig | None = None) -> bool:
    if os.getenv("AI_CORE_USE_RULES", "0") == "1":
        return False
    probe = cfg or AiCoreConfig()
    return resolve_llm_credentials(probe) is not None


def _extract_json(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return json.loads(text)


def chat_json(prompt: str, cfg: AiCoreConfig, creds: LlmCredentials | None = None) -> dict[str, Any]:
    cred = creds or resolve_llm_credentials(cfg)
    if not cred:
        raise RuntimeError("未配置大模型：请在 data_config.db_llm_token 启用记录，或设置 AI_CORE_LLM_API_KEY")
    model = cfg.model_name if cfg.model_name else cred.model_name
    if cred.source == "db_llm_token":
        model = cred.model_name
    payload = {
        "model": model,
        "temperature": cfg.temperature,
        "max_tokens": cfg.max_tokens,
        "messages": [{"role": "user", "content": prompt}],
    }
    req = urllib.request.Request(
        f"{cred.api_url}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {cred.api_key}",
        },
        method="POST",
    )
    last_err: Exception | None = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                body = json.loads(resp.read().decode("utf-8"))
            content = body["choices"][0]["message"]["content"]
            return _extract_json(content)
        except (urllib.error.HTTPError, urllib.error.URLError, json.JSONDecodeError, KeyError) as exc:
            last_err = exc
            logger.warning(
                "LLM 调用失败 provider=%s model=%s attempt=%s: %s",
                cred.provider,
                model,
                attempt + 1,
                exc,
            )
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"LLM 调用失败: {last_err}")


def rule_based_analyze(
    industry_id: str,
    industry_name: str,
    ctx: StockContext,
    cfg: AiCoreConfig,
) -> AiScoreRow:
    """无 LLM 时的 MVP 规则评分（关键词 + 主营占比 + 研报覆盖）。"""
    keywords = _industry_keywords(industry_name)
    corpus = text_corpus(ctx)
    hits = sum(corpus.count(kw) for kw in keywords) if keywords else 0
    match = hits > 0

    score = 30.0
    reasons: list[str] = []

    if hits >= 3:
        score += 25
        reasons.append(f"文本命中赛道关键词{hits}次")
    elif hits >= 1:
        score += 12
        reasons.append("文本含赛道关键词")

    if ctx.mainbz_related_pct is not None:
        pct = ctx.mainbz_related_pct
        score += min(40, pct * 0.8)
        reasons.append(f"主营相关占比约{pct}%")
        if pct >= 30:
            match = True

    if ctx.report_summary:
        score += 8
        reasons.append("近90日有卖方研报")

    if ctx.fina_summary:
        score += 5

    if not corpus.strip() and not ctx.mainbz_items:
        score = 15.0
        match = False
        reasons.append("缺少公司资料")

    score = max(0.0, min(100.0, score))
    if score <= cfg.reject_score:
        match = False

    core_degree = "核心" if score >= 85 else "重要" if score >= 70 else "一般" if score >= 50 else "边缘"
    return AiScoreRow(
        industry_id=industry_id,
        industry_name=industry_name,
        ts_code=ctx.ts_code,
        stock_name=ctx.stock_name,
        industry_match=match,
        segment="待细分",
        core_degree=core_degree,
        score=round(score, 2),
        level=None,
        reason="；".join(reasons) or "规则引擎评分",
        model_name="rule_engine",
        prompt_version=cfg.prompt_version,
        raw_json={"engine": "rule", "keyword_hits": hits},
    )


def analyze_one(
    industry_id: str,
    industry_name: str,
    ctx: StockContext,
    cfg: AiCoreConfig,
    *,
    force_rules: bool = False,
    creds: LlmCredentials | None = None,
) -> AiScoreRow:
    cred = None if force_rules else resolve_llm_credentials(cfg)
    if not cred or os.getenv("AI_CORE_USE_RULES", "0") == "1":
        return rule_based_analyze(industry_id, industry_name, ctx, cfg)

    prompt = render_prompt(industry_name, ctx, version=cfg.prompt_version)
    raw: dict[str, Any] | None = None
    used_model = cred.model_name
    try:
        raw = chat_json(prompt, cfg, cred)
        row = AiScoreRow(
            industry_id=industry_id,
            industry_name=industry_name,
            ts_code=ctx.ts_code,
            stock_name=ctx.stock_name,
            industry_match=bool(raw.get("industry_match")),
            segment=str(raw.get("segment") or "")[:64] or None,
            core_degree=str(raw.get("core_degree") or "")[:16] or None,
            score=float(raw["score"]) if raw.get("score") is not None else None,
            level=None,
            reason=str(raw.get("reason") or "")[:500] or None,
            model_name=used_model,
            prompt_version=cfg.prompt_version,
            raw_json={**(raw or {}), "_llm_provider": cred.provider, "_llm_source": cred.source},
        )
        return row
    except Exception as exc:
        logger.warning("LLM 分析失败 ts=%s industry=%s: %s，回退规则引擎", ctx.ts_code, industry_id, exc)
        fallback = rule_based_analyze(industry_id, industry_name, ctx, cfg)
        fallback.raw_json = {"llm_error": str(exc), "partial": raw, "_llm_provider": cred.provider}
        return fallback
