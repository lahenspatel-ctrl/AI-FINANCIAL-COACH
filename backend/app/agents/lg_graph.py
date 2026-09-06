"""
LangGraph graph definitions.

analysis_graph  — linear pipeline triggered on file upload:
                  categorize → debt_analyzer → savings → budget_advisor

chat_graph      — ReAct agent for conversational Q&A:
                  uses Tavily web search + deterministic financial tools
"""
from __future__ import annotations

from functools import lru_cache

from langchain_core.messages import SystemMessage
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import create_react_agent

from backend.app.agents.lg_llm import get_chat_model_with_fallbacks
from backend.app.agents.lg_nodes import (
    budget_advisor_node,
    categorize_node,
    debt_analyzer_node,
    savings_node,
    should_continue,
)
from backend.app.agents.lg_state import ChatState, PipelineState
from backend.app.agents.lg_tools import CHATBOT_TOOLS


# ── Analysis pipeline graph ───────────────────────────────────────────────────

@lru_cache(maxsize=1)
def build_analysis_graph():
    """Compile and cache the upload-triggered analysis pipeline."""
    g = StateGraph(PipelineState)

    g.add_node("categorize", categorize_node)
    g.add_node("debt_analyzer", debt_analyzer_node)
    g.add_node("savings", savings_node)
    g.add_node("budget_advisor", budget_advisor_node)

    g.add_edge(START, "categorize")

    # After categorize: continue unless hard error
    g.add_conditional_edges(
        "categorize",
        should_continue,
        {"continue": "debt_analyzer", "end": END},
    )
    g.add_conditional_edges(
        "debt_analyzer",
        should_continue,
        {"continue": "savings", "end": END},
    )
    g.add_conditional_edges(
        "savings",
        should_continue,
        {"continue": "budget_advisor", "end": END},
    )
    g.add_edge("budget_advisor", END)

    return g.compile()


# ── Chatbot ReAct graph ───────────────────────────────────────────────────────

_CHATBOT_SYSTEM = """You are an expert personal financial advisor chatbot.

You have access to the user's actual financial data (provided as context in the conversation).
You also have access to:
  - web_search: search the web for current financial news, rates, and advice
  - calculate_debt_payoff: run exact debt payoff math (avalanche/snowball)
  - calculate_savings_projection: project compound savings growth
  - analyze_spending_budget: assess a budget and flag problem areas

Rules:
1. NEVER invent financial numbers. If you don't have data, say so and offer to search.
2. Always use calculate_* tools when the user asks for projections or payoff timelines.
3. Use web_search when asked about current rates, market conditions, or external benchmarks.
4. Be concise, warm, and practical. Format currency as $X,XXX.
5. Ground every recommendation in the user's actual data shown in the context."""


@lru_cache(maxsize=1)
def build_chat_graph():
    """Compile and cache the chatbot ReAct agent graph."""
    llm = get_chat_model_with_fallbacks("chat")
    return create_react_agent(
        model=llm,
        tools=CHATBOT_TOOLS,
        state_schema=ChatState,
        prompt=SystemMessage(content=_CHATBOT_SYSTEM),
    )
