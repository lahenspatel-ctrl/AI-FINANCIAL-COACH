"""
Orchestrator — bridges LangGraph graphs with FastAPI SSE and SQLAlchemy.

run_analysis_pipeline:
    Fetches DB data → builds initial PipelineState → runs analysis_graph →
    streams AgentEvent dicts as they are emitted by each node.

run_chat:
    Builds financial context from DB → invokes chat_graph with user message →
    streams token-by-token response via astream_events.
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import AsyncGenerator

import pandas as pd
from langchain_core.messages import HumanMessage, SystemMessage
from loguru import logger
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.agents.events import AgentEvent
from backend.app.agents.lg_graph import build_analysis_graph, build_chat_graph, build_chat_graph_with_keys
from backend.app.agents.lg_state import PipelineState
from backend.app.db.models import AgentRun, ChatMessage, Transaction
from backend.app.services.data_service import (
    get_debts,
    get_income,
    get_recent_chat,
    get_transactions_df,
)
from backend.app.services.vector_store import query_similar


# ── Analysis Pipeline ─────────────────────────────────────────────────────────

async def run_analysis_pipeline(
    db: AsyncSession,
    run_id: str,
    user_id: str = "demo",
    selected_agents: list[str] | None = None,
    openrouter_key: str | None = None,
    tavily_key: str | None = None,
) -> AsyncGenerator[str, None]:
    """
    Yield raw SSE strings (data: {...}\\n\\n) as the LangGraph pipeline progresses.
    Updates the AgentRun record on completion.
    """

    async def _emit(agent: str, status: str, message: str, data: dict | None = None) -> str:
        payload = {"agent": agent, "status": status, "message": message, "data": data}
        return f"data: {json.dumps(payload)}\n\n"

    yield await _emit("orchestrator", "started", "Fetching your financial data…")

    # ── Pre-fetch all data from DB ────────────────────────────────────────────
    try:
        txn_df = await get_transactions_df(db, user_id)
        debts_orm = await get_debts(db, user_id)
        income_orm = await get_income(db, user_id)
    except Exception as exc:
        yield await _emit("orchestrator", "error", f"Failed to load data: {exc}")
        return

    txn_json = txn_df.to_json(orient="records", date_format="iso") if not txn_df.empty else "[]"

    debts = [
        {
            "name": d.name,
            "balance": d.balance,
            "apr": d.apr,
            "minimum_payment": d.minimum_payment,
            "debt_type": d.debt_type,
        }
        for d in debts_orm
    ]
    income = [
        {"source": i.source, "monthly_amount": i.monthly_amount, "income_type": i.income_type}
        for i in income_orm
    ]

    yield await _emit(
        "orchestrator",
        "progress",
        f"Loaded {len(txn_df)} transactions, {len(debts)} debts, {len(income)} income sources.",
    )

    # ── Build initial state & run graph ───────────────────────────────────────
    initial_state: PipelineState = {
        "user_id": user_id,
        "run_id": run_id,
        "transactions_json": txn_json,
        "debts": debts,
        "income": income,
        "events": [],
        "categorization_result": None,
        "debt_result": None,
        "savings_result": None,
        "budget_result": None,
        "error": None,
        "selected_agents": selected_agents,
        "openrouter_key": openrouter_key,
        "tavily_key": tavily_key,
    }

    graph = build_analysis_graph()
    final_state: PipelineState | None = None

    # Stream events from LangGraph as each node completes
    async for chunk in graph.astream(initial_state, stream_mode="updates"):
        for node_name, node_output in chunk.items():
            new_events: list[dict] = node_output.get("events", [])
            for evt in new_events:
                yield f"data: {json.dumps(evt)}\n\n"
        final_state = {**initial_state, **{k: v for d in chunk.values() for k, v in d.items()}}

    # ── Persist categorization back to DB ─────────────────────────────────────
    if final_state and final_state.get("categorization_result"):
        cat_map: dict = final_state["categorization_result"].get("category_map", {})
        if cat_map and not txn_df.empty:
            for str_idx, cats in cat_map.items():
                orig_idx = int(str_idx)
                if orig_idx < len(txn_df):
                    txn_id = txn_df.iloc[orig_idx]["id"]
                    await db.execute(
                        update(Transaction)
                        .where(Transaction.id == txn_id)
                        .values(
                            category=cats.get("category"),
                            sub_category=cats.get("sub_category"),
                        )
                    )
            await db.commit()

    # ── Update AgentRun record ────────────────────────────────────────────────
    summary = {}
    if final_state:
        summary = {
            "debt_result": final_state.get("debt_result"),
            "savings_result": final_state.get("savings_result"),
            "budget_result": final_state.get("budget_result"),
        }

    await db.execute(
        update(AgentRun)
        .where(AgentRun.id == run_id)
        .values(
            status="completed" if not (final_state or {}).get("error") else "error",
            summary_json=json.dumps(summary),
            finished_at=datetime.utcnow(),
        )
    )
    await db.commit()

    status = "error" if (final_state or {}).get("error") else "complete"
    yield await _emit(
        "orchestrator",
        status,
        "Analysis complete." if status == "complete" else f"Pipeline error: {(final_state or {}).get('error')}",
        data=summary,
    )


# ── Chatbot ───────────────────────────────────────────────────────────────────

async def run_chat(
    db: AsyncSession,
    user_message: str,
    user_id: str = "demo",
    openrouter_key: str | None = None,
    tavily_key: str | None = None,
) -> AsyncGenerator[str, None]:
    """
    Yield SSE strings for the chatbot response.
    Streams token-by-token using LangGraph astream_events.
    Persists the exchange to the chat_messages table.
    """
    # Save user message
    db.add(ChatMessage(user_id=user_id, role="user", content=user_message))
    await db.commit()

    # Build financial context for the system prompt
    txn_df = await get_transactions_df(db, user_id)
    debts = await get_debts(db, user_id)
    income_rows = await get_income(db, user_id)
    history = await get_recent_chat(db, user_id, limit=6)
    semantic_hits = query_similar(user_message, user_id=user_id, n_results=5)

    ctx: dict = {}
    if not txn_df.empty:
        ctx["total_transactions"] = len(txn_df)
        ctx["total_income_in_data"] = round(float(txn_df[txn_df["amount"] > 0]["amount"].sum()), 2)
        ctx["total_expenses_in_data"] = round(float(txn_df[txn_df["amount"] < 0]["amount"].sum()), 2)
        top = (
            txn_df[txn_df["amount"] < 0]
            .assign(amount=lambda df: df["amount"].abs())
            .groupby("category")["amount"]
            .sum()
            .sort_values(ascending=False)
            .head(5)
            .round(2)
            .to_dict()
        )
        ctx["top_expense_categories"] = top
    if debts:
        ctx["debts"] = [{"name": d.name, "balance": d.balance, "apr": f"{d.apr:.1%}"} for d in debts]
        ctx["total_debt"] = round(sum(d.balance for d in debts), 2)
    if income_rows:
        ctx["monthly_income"] = round(sum(i.monthly_amount for i in income_rows), 2)
    if semantic_hits:
        ctx["relevant_transactions"] = [h["document"] for h in semantic_hits[:5]]

    financial_context_json = json.dumps(ctx, indent=2)

    # Build message list for the graph
    graph_messages = [
        SystemMessage(content=f"User's financial data:\n{financial_context_json}"),
    ]
    for msg in history[-6:]:
        from langchain_core.messages import AIMessage
        if msg.role == "user":
            graph_messages.append(HumanMessage(content=msg.content))
        else:
            graph_messages.append(AIMessage(content=msg.content))
    graph_messages.append(HumanMessage(content=user_message))

    if openrouter_key or tavily_key:
        graph = build_chat_graph_with_keys(openrouter_key=openrouter_key, tavily_key=tavily_key)
    else:
        graph = build_chat_graph()

    full_response = ""
    try:
        async for event in graph.astream_events(
            {"messages": graph_messages, "user_id": user_id, "financial_context_json": financial_context_json},
            version="v2",
        ):
            kind = event.get("event", "")
            # Stream LLM tokens
            if kind == "on_chat_model_stream":
                chunk = event.get("data", {}).get("chunk")
                if chunk and hasattr(chunk, "content") and chunk.content:
                    token = chunk.content
                    full_response += token
                    yield f"data: {json.dumps({'type': 'token', 'content': token})}\n\n"
            # Tool usage notification
            elif kind == "on_tool_start":
                tool_name = event.get("name", "tool")
                yield f"data: {json.dumps({'type': 'tool_start', 'tool': tool_name})}\n\n"
            elif kind == "on_tool_end":
                tool_name = event.get("name", "tool")
                yield f"data: {json.dumps({'type': 'tool_end', 'tool': tool_name})}\n\n"

    except Exception as exc:
        logger.error(f"Chat graph error: {exc}")
        full_response = "I encountered an error. Please try again."
        yield f"data: {json.dumps({'type': 'token', 'content': full_response})}\n\n"

    # Save assistant reply
    if full_response:
        db.add(ChatMessage(user_id=user_id, role="assistant", content=full_response))
        await db.commit()

    yield f"data: {json.dumps({'type': 'done'})}\n\n"
