"""
Pipeline endpoints — trigger the LangGraph analysis pipeline and stream SSE progress.

Per-user API keys:
  EventSource (SSE) cannot send custom headers, so keys are bridged via an
  in-memory dict: POST /run stores them under run_id, GET /stream retrieves
  and deletes them before invoking the pipeline.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.agents.orchestrator import run_analysis_pipeline
from backend.app.db.database import get_db
from backend.app.db.models import AgentRun
from backend.app.schemas.finance import AgentRunOut

router = APIRouter(prefix="/api/pipeline", tags=["pipeline"])

# run_id → {"openrouter_key": ..., "tavily_key": ...}
_run_keys: dict[str, dict[str, str | None]] = {}


@router.post("/run", response_model=AgentRunOut, status_code=202)
async def trigger_pipeline(
    request: Request,
    user_id: str = "demo",
    db: AsyncSession = Depends(get_db),
):
    """Create an AgentRun record and stash per-user API keys for the stream call."""
    run = AgentRun(user_id=user_id, trigger="manual", status="pending")
    db.add(run)
    await db.commit()
    await db.refresh(run)

    or_key = request.headers.get("X-OpenRouter-Key") or None
    tv_key = request.headers.get("X-Tavily-Key") or None
    if or_key or tv_key:
        _run_keys[str(run.id)] = {"openrouter_key": or_key, "tavily_key": tv_key}

    return run


@router.get("/stream/{run_id}")
async def stream_pipeline(
    run_id: str,
    user_id: str = "demo",
    agents: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """SSE endpoint: streams agent progress events for the given run_id.
    Pass agents=categorizer,debt_analyzer to run only specific agents."""
    selected = [a.strip() for a in agents.split(",") if a.strip()] if agents else None

    # Retrieve and remove keys stored by the POST call
    keys = _run_keys.pop(run_id, {})
    or_key: str | None = keys.get("openrouter_key")
    tv_key: str | None = keys.get("tavily_key")

    async def _generate():
        async for chunk in run_analysis_pipeline(
            db,
            run_id=run_id,
            user_id=user_id,
            selected_agents=selected,
            openrouter_key=or_key,
            tavily_key=tv_key,
        ):
            yield chunk

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
