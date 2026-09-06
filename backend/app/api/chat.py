"""
Chat endpoints — streaming chatbot powered by the LangGraph ReAct agent + Tavily.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.agents.orchestrator import run_chat
from backend.app.db.database import get_db
from backend.app.schemas.finance import ChatMessageIn, ChatMessageOut
from backend.app.services.data_service import get_recent_chat

router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.get("/history", response_model=list[ChatMessageOut])
async def get_history(user_id: str = "demo", db: AsyncSession = Depends(get_db)):
    msgs = await get_recent_chat(db, user_id=user_id, limit=50)
    return msgs


@router.post("/send")
async def send_message(
    body: ChatMessageIn,
    request: Request,
    user_id: str = "demo",
    db: AsyncSession = Depends(get_db),
):
    """
    SSE stream:
      data: {"type": "token", "content": "..."}
      data: {"type": "tool_start", "tool": "web_search"}
      data: {"type": "tool_end", "tool": "web_search"}
      data: {"type": "done"}
    """
    or_key = request.headers.get("X-OpenRouter-Key") or None
    tv_key = request.headers.get("X-Tavily-Key") or None

    async def _generate():
        async for chunk in run_chat(
            db,
            body.content,
            user_id=user_id,
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
