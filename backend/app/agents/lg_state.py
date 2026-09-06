"""
LangGraph shared state definitions.

PipelineState  — for the upload-triggered analysis pipeline (linear graph).
ChatState      — for the conversational ReAct chatbot agent.
"""
from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class AgentEventDict(TypedDict):
    agent: str
    status: str       # started | progress | complete | error
    message: str
    data: dict | None


class PipelineState(TypedDict):
    """State flowing through the upload-triggered analysis pipeline."""
    user_id: str
    run_id: str
    # Pre-fetched data (set by orchestrator before graph invocation)
    transactions_json: str        # pandas DataFrame → JSON records
    debts: list[dict]             # list of debt dicts
    income: list[dict]            # list of income dicts
    # Accumulated SSE events — each node appends; operator.add merges lists
    events: Annotated[list[AgentEventDict], operator.add]
    # Per-agent results (set by each node)
    categorization_result: dict[str, Any] | None
    debt_result: dict[str, Any] | None
    savings_result: dict[str, Any] | None
    budget_result: dict[str, Any] | None
    # Error flag — any node can set this to short-circuit remaining nodes
    error: str | None
    # Optional subset of agent keys to run; None = run all
    selected_agents: list[str] | None


class ChatState(TypedDict):
    """State for the conversational chatbot ReAct agent."""
    messages: Annotated[list[BaseMessage], add_messages]
    user_id: str
    # Context injected before the graph runs
    financial_context_json: str
