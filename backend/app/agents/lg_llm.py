"""
LangChain ChatOpenAI factory pointed at OpenRouter.
Returns a model for a given role using the fallback-chain registry.
The first model in the chain is used as the primary; tenacity handles retries.
"""
from __future__ import annotations

from functools import lru_cache

from langchain_openai import ChatOpenAI

from backend.app.config import settings
from backend.app.llm.model_registry import get_model_chain

_ROLE_TEMPERATURE: dict[str, float] = {
    "classifier": 0.0,
    "analyst": 0.2,
    "chat": 0.4,
    "summarizer": 0.2,
}

_ROLE_MAX_TOKENS: dict[str, int] = {
    "classifier": 512,
    "analyst": 512,
    "chat": 768,
    "summarizer": 300,
}


def get_chat_model(role: str = "chat") -> ChatOpenAI:
    """Return a ChatOpenAI instance for the given role (primary model in chain)."""
    chain = get_model_chain(role)
    primary_model = chain[0]
    return ChatOpenAI(
        model=primary_model,
        openai_api_key=settings.openrouter_api_key or "no-key",
        openai_api_base=settings.openrouter_base_url,
        temperature=_ROLE_TEMPERATURE.get(role, 0.2),
        max_tokens=_ROLE_MAX_TOKENS.get(role, 512),
        default_headers={
            "HTTP-Referer": "https://ai-financial-coach.local",
            "X-Title": "AI Financial Coach Agent",
        },
    )


def get_chat_model_with_fallbacks(role: str = "chat") -> ChatOpenAI:
    """Return a ChatOpenAI with LangChain fallback chain for reliability."""
    chain = get_model_chain(role)
    primary = get_chat_model(role)
    if len(chain) <= 1:
        return primary

    fallbacks = [
        ChatOpenAI(
            model=m,
            openai_api_key=settings.openrouter_api_key or "no-key",
            openai_api_base=settings.openrouter_base_url,
            temperature=_ROLE_TEMPERATURE.get(role, 0.2),
            max_tokens=_ROLE_MAX_TOKENS.get(role, 512),
            default_headers={
                "HTTP-Referer": "https://ai-financial-coach.local",
                "X-Title": "AI Financial Coach Agent",
            },
        )
        for m in chain[1:]
    ]
    return primary.with_fallbacks(fallbacks)
