"""
SSE event types for streaming agent progress to the frontend.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from typing import Literal


AgentStatus = Literal["started", "progress", "complete", "error"]


@dataclass
class AgentEvent:
    agent: str
    status: AgentStatus
    message: str
    data: dict | None = None

    def to_sse(self) -> str:
        payload = asdict(self)
        return f"data: {json.dumps(payload)}\n\n"
