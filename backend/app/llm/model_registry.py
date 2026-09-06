"""
LLM model registry.

Each agent requests a ROLE, not a specific model ID.
The client tries models in order; 429/5xx triggers fallback to the next model.
Override any role via MODEL_OVERRIDES_JSON env var.
"""
from __future__ import annotations

from backend.app.config import settings

# Default fallback chains per role (cheapest/free first)
_DEFAULT_REGISTRY: dict[str, list[str]] = {
    # Fast, cheap — JSON output, categorization, intent routing
    "classifier": [
        "meta-llama/llama-3.2-3b-instruct:free",
        "mistralai/mistral-7b-instruct:free",
        "meta-llama/llama-3.1-8b-instruct",
    ],
    # Moderate reasoning — debt analysis, budget advice, savings strategy
    "analyst": [
        "mistralai/mistral-7b-instruct:free",
        "meta-llama/llama-3.1-8b-instruct:free",
        "meta-llama/llama-3.1-8b-instruct",
    ],
    # Conversational — the advisor chatbot agent
    "chat": [
        "meta-llama/llama-3.1-8b-instruct:free",
        "mistralai/mistral-7b-instruct:free",
        "meta-llama/llama-3.1-8b-instruct",
    ],
    # Summarization — concise plain-language summaries of computed results
    "summarizer": [
        "meta-llama/llama-3.2-3b-instruct:free",
        "mistralai/mistral-7b-instruct:free",
        "meta-llama/llama-3.1-8b-instruct",
    ],
}


def get_model_chain(role: str) -> list[str]:
    overrides = settings.model_overrides()
    registry = {**_DEFAULT_REGISTRY, **overrides}
    chain = registry.get(role)
    if not chain:
        raise ValueError(f"Unknown LLM role: {role!r}. Valid roles: {list(registry)}")
    return chain
