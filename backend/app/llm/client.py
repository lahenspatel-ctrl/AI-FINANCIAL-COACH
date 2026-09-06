"""
OpenRouter LLM client with per-role model fallback chains,
per-model rate limiting, and tenacity retries.
"""
from __future__ import annotations

import json
from typing import Any

from loguru import logger
from openai import AsyncOpenAI, APIStatusError, APITimeoutError
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from backend.app.config import settings
from backend.app.llm.model_registry import get_model_chain
from backend.app.llm.rate_limiter import acquire

_client: AsyncOpenAI | None = None


def get_openai_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(
            api_key=settings.openrouter_api_key or "no-key-set",
            base_url=settings.openrouter_base_url,
            default_headers={
                "HTTP-Referer": "https://ai-financial-coach.local",
                "X-Title": "AI Financial Coach Agent",
            },
        )
    return _client


_RETRYABLE = (APIStatusError, APITimeoutError)


async def _call_model(
    model: str,
    messages: list[dict],
    temperature: float,
    max_tokens: int,
    response_format: dict | None,
) -> str:
    await acquire(model)
    client = get_openai_client()
    kwargs: dict[str, Any] = dict(
        model=model,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    if response_format:
        kwargs["response_format"] = response_format
    resp = await client.chat.completions.create(**kwargs)
    return resp.choices[0].message.content or ""


async def chat_complete(
    role: str,
    messages: list[dict],
    *,
    temperature: float = 0.2,
    max_tokens: int = 1024,
    json_mode: bool = False,
) -> str:
    """
    Try each model in the role's fallback chain.
    Returns the first successful response content.
    Raises RuntimeError if all models fail.
    """
    chain = get_model_chain(role)
    response_format = {"type": "json_object"} if json_mode else None
    last_exc: Exception | None = None

    for model in chain:
        try:
            logger.debug(f"LLM call | role={role} model={model}")
            result = await _call_with_retry(
                model, messages, temperature, max_tokens, response_format
            )
            logger.debug(f"LLM ok   | role={role} model={model}")
            return result
        except Exception as exc:
            logger.warning(f"LLM fail | role={role} model={model} err={exc}")
            last_exc = exc
            continue

    raise RuntimeError(
        f"All models failed for role={role!r}. Last error: {last_exc}"
    )


@retry(
    retry=retry_if_exception_type(_RETRYABLE),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=2, min=2, max=30),
    reraise=True,
)
async def _call_with_retry(
    model: str,
    messages: list[dict],
    temperature: float,
    max_tokens: int,
    response_format: dict | None,
) -> str:
    return await _call_model(model, messages, temperature, max_tokens, response_format)


async def chat_complete_json(role: str, messages: list[dict], **kwargs) -> dict:
    raw = await chat_complete(role, messages, json_mode=True, **kwargs)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # Some models wrap JSON in markdown fences; strip them
        cleaned = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        return json.loads(cleaned)
