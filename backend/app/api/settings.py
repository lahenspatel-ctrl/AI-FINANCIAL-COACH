"""
Settings API — view and update API keys at runtime.
Keys are saved to .env and applied immediately without restart.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter
from loguru import logger
from pydantic import BaseModel

from backend.app.config import settings

router = APIRouter(prefix="/api/settings", tags=["settings"])


def _mask(key: str) -> str:
    if not key:
        return ""
    if len(key) <= 10:
        return "•" * len(key)
    return key[:4] + "•" * (len(key) - 8) + key[-4:]


def _write_env(env_key: str, value: str) -> None:
    env_path = Path(".env")
    if not env_path.exists():
        env_path.write_text("", encoding="utf-8")
    lines = env_path.read_text(encoding="utf-8").splitlines(keepends=True)
    found = False
    new_lines = []
    for line in lines:
        if line.startswith(f"{env_key}="):
            new_lines.append(f"{env_key}={value}\n")
            found = True
        else:
            new_lines.append(line)
    if not found:
        new_lines.append(f"{env_key}={value}\n")
    env_path.write_text("".join(new_lines), encoding="utf-8")


class KeysUpdate(BaseModel):
    openrouter_api_key: str | None = None
    tavily_api_key: str | None = None


@router.get("/keys")
async def get_keys():
    return {
        "openrouter": {
            "masked": _mask(settings.openrouter_api_key),
            "is_set": bool(settings.openrouter_api_key),
        },
        "tavily": {
            "masked": _mask(settings.tavily_api_key),
            "is_set": bool(settings.tavily_api_key),
        },
    }


@router.post("/keys", status_code=204)
async def update_keys(body: KeysUpdate):
    from backend.app.agents.lg_graph import build_analysis_graph, build_chat_graph

    if body.openrouter_api_key and body.openrouter_api_key.strip():
        val = body.openrouter_api_key.strip()
        _write_env("OPENROUTER_API_KEY", val)
        object.__setattr__(settings, "openrouter_api_key", val)
        build_analysis_graph.cache_clear()
        build_chat_graph.cache_clear()
        logger.info("OpenRouter API key updated and caches cleared")

    if body.tavily_api_key and body.tavily_api_key.strip():
        val = body.tavily_api_key.strip()
        _write_env("TAVILY_API_KEY", val)
        object.__setattr__(settings, "tavily_api_key", val)
        build_chat_graph.cache_clear()
        logger.info("Tavily API key updated and chat graph cache cleared")
