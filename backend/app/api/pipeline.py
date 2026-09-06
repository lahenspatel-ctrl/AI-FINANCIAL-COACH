"""
Pipeline endpoints — trigger the LangGraph analysis pipeline and stream SSE progress.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.agents.orchestrator import run_analysis_pipeline
from backend.app.db.database import get_db
from backend.app.db.models import AgentRun
from backend.app.schemas.finance import AgentRunOut

router = APIRouter(prefix="/api/pipeline", tags=["pipeline"])


@router.post("/run", response_model=AgentRunOut, status_code=202)
async def trigger_pipeline(user_id: str = "demo", db: AsyncSession = Depends(get_db)):
    """Create an AgentRun record and return its ID. Client then connects to /stream/{run_id}."""
    run = AgentRun(user_id=user_id, trigger="manual", status="pending")
    db.add(run)
    await db.commit()
    await db.refresh(run)
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

    async def _generate():
        async for chunk in run_analysis_pipeline(
            db, run_id=run_id, user_id=user_id, selected_agents=selected
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
