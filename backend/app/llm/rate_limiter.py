"""
Token-bucket rate limiter for OpenRouter models.
Shared in-process state — single-user MVP is fine.
"""
from __future__ import annotations

import asyncio
import time
from collections import defaultdict

from backend.app.config import settings


class _TokenBucket:
    def __init__(self, rpm: int) -> None:
        self._rate = rpm / 60.0  # tokens per second
        self._capacity = rpm
        self._tokens: float = float(rpm)
        self._last_refill = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_refill
            self._tokens = min(self._capacity, self._tokens + elapsed * self._rate)
            self._last_refill = now
            if self._tokens < 1:
                wait = (1 - self._tokens) / self._rate
                await asyncio.sleep(wait)
                self._tokens = 0.0
            else:
                self._tokens -= 1.0


_buckets: dict[str, _TokenBucket] = defaultdict(
    lambda: _TokenBucket(settings.rate_limit_rpm)
)


async def acquire(model_id: str) -> None:
    await _buckets[model_id].acquire()
