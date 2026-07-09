"""问数 LLM：凭证解析与文本生成（可选）。"""
from __future__ import annotations

import json
import logging
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

from sqlalchemy import create_engine, text

logger = logging.getLogger(__name__)


@dataclass
class LlmCredentials:
    provider: str
    model_name: str
    api_url: str
    api_key: str


def _config_engine():
    host = os.getenv("CONFIG_MYSQL_HOST", "localhost")
    port = int(os.getenv("CONFIG_MYSQL_PORT", "3306"))
    user = os.getenv("CONFIG_MYSQL_USER", "data_config")
    password = os.getenv("CONFIG_MYSQL_PASSWORD", "")
    database = os.getenv("CONFIG_MYSQL_DATABASE", "data_config")
    pwd = urllib.parse.quote_plus(password)
    user_q = urllib.parse.quote_plus(user)
    url = f"mysql+pymysql://{user_q}:{pwd}@{host}:{port}/{database}?charset=utf8mb4"
    return create_engine(url, pool_pre_ping=True)


def resolve_llm_credentials() -> LlmCredentials | None:
    if os.getenv("ASK_USE_RULES", "0") == "1":
        return None
    try:
        engine = _config_engine()
        sql = """
            SELECT provider, model_name, api_key, api_url
            FROM db_llm_token
            WHERE status = 1
              AND (start_date IS NULL OR start_date <= NOW())
              AND (end_date IS NULL OR end_date >= NOW())
            ORDER BY is_default DESC, priority ASC, id DESC
            LIMIT 1
        """
        with engine.connect() as conn:
            row = conn.execute(text(sql)).mappings().first()
        if row and str(row.get("api_key") or "").strip() not in ("", "REPLACE_WITH_YOUR_KEY"):
            return LlmCredentials(
                provider=str(row["provider"]),
                model_name=str(row["model_name"]),
                api_url=str(row["api_url"]).rstrip("/"),
                api_key=str(row["api_key"]).strip(),
            )
    except Exception as exc:
        logger.warning("读取 db_llm_token 失败: %s", exc)

    api_url = (
        os.getenv("AI_CORE_LLM_API_URL")
        or os.getenv("OPENAI_API_BASE")
        or ""
    ).rstrip("/")
    api_key = (os.getenv("AI_CORE_LLM_API_KEY") or os.getenv("OPENAI_API_KEY") or "").strip()
    model = os.getenv("AI_CORE_LLM_MODEL") or os.getenv("ASK_LLM_MODEL") or "gpt-4o-mini"
    if api_key:
        return LlmCredentials(
            provider=os.getenv("AI_CORE_LLM_PROVIDER") or "env",
            model_name=model,
            api_url=api_url or "https://api.openai.com/v1",
            api_key=api_key,
        )
    return None


def llm_available() -> bool:
    return resolve_llm_credentials() is not None


def chat_text(system_prompt: str, user_prompt: str, *, temperature: float = 0.3, max_tokens: int = 800) -> str:
    cred = resolve_llm_credentials()
    if not cred:
        raise RuntimeError("未配置大模型")
    payload = {
        "model": cred.model_name,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
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
    with urllib.request.urlopen(req, timeout=60) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    content = body["choices"][0]["message"]["content"]
    return re.sub(r"^```(?:markdown)?\s*|\s*```$", "", content.strip())
