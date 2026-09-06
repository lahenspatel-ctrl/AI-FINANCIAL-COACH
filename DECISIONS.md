# Architecture & Design Decisions

## MVP Scope Decisions

| # | Decision | Rationale |
|---|----------|-----------|
| 1 | Single-user, `user_id="demo"` placeholder | Auth is out of scope; placeholder lets us add it later without rearchitecting |
| 2 | SQLite at `data/app.db` | Zero-config, file-based, perfectly adequate for single-user MVP |
| 3 | ChromaDB persistent at `data/chroma/` | Embedded, no separate server, easy to reset |
| 4 | fastembed with `BAAI/bge-small-en-v1.5` | ONNX-based, runs locally, zero cost, no torch dependency |
| 5 | LLMs do NOT compute numbers | All financial math (payoff schedules, interest, projections) is deterministic Python. LLMs receive computed numbers as context for explanation/summarization only |
| 6 | OpenRouter free tier as primary | Cost-zero for demo; fallback chain handles 429/5xx automatically |
| 7 | SSE (Server-Sent Events) for streaming | Simpler than WebSockets for unidirectional server→client progress; no WS library needed |
| 8 | Vanilla JS frontend, no build step | Reduces setup friction; Chart.js + marked.js via CDN |
| 9 | Transactions stored in SQLite, embeddings in ChromaDB | Tabular RAG: SQL for exact filtering + ChromaDB for semantic similarity on transaction descriptions |
| 10 | Makefile as task runner | Cross-platform via `make`; no Poetry/Hatch added to keep setup simple |

## Tech Stack Deviations

| Deviation | Why |
|-----------|-----|
| Added LangGraph + LangChain | User requested multi-agent pipeline be orchestrated with LangGraph. `langchain-openai` wraps OpenRouter; `langgraph.prebuilt.create_react_agent` builds the chatbot ReAct loop. The raw `openai` SDK is still kept for the rate-limiter/model-registry used in categorizer batching. |
| Added Tavily web search | User requested Tavily as a tool available to the chatbot. API key stored in `TAVILY_API_KEY` env var, never logged. Tool returns max 3 results to conserve quota. |

## LangGraph Architecture

### Analysis Pipeline (`build_analysis_graph`)
Linear `StateGraph` — nodes run sequentially after each file upload:
```
START → categorize_node → debt_analyzer_node → savings_node → budget_advisor_node → END
```
- Each node appends `AgentEventDict` items to `state["events"]`; the orchestrator streams these as SSE.
- A `should_continue` conditional edge short-circuits remaining nodes on hard errors.
- Pre-fetched DB data is serialized into `PipelineState` before the graph runs (avoids async DB in nodes).

### Chatbot (`build_chat_graph`)
`create_react_agent` ReAct loop with 4 tools:
- `web_search` — Tavily for current rates/news
- `calculate_debt_payoff` — deterministic avalanche/snowball
- `calculate_savings_projection` — deterministic compound growth
- `analyze_spending_budget` — rule-based budget flags

### Streaming
- Pipeline: `graph.astream(state, stream_mode="updates")` → collect `events` from each node patch.
- Chat: `graph.astream_events(..., version="v2")` → forward `on_chat_model_stream` tokens and `on_tool_start/end` events as SSE.

## LLM Fallback Strategy (LangChain)
`ChatOpenAI.with_fallbacks([...])` chains models in the role's registry order.
LangChain retries on `openai.APIError` before advancing to the next model.

## LLM Rate Limiting Strategy
- In-memory token bucket per model (cachetools TTLCache)
- Exponential backoff via tenacity (max 3 retries, wait 2–30 s)
- If all models in role's fallback chain are exhausted, raise a structured error (not a 500) so the UI can show a user-friendly message

## Financial Calculation Conventions
- All monetary amounts stored as Python `Decimal` internally, serialized as `float` to DB/JSON (SQLite has no Decimal type)
- Interest rate inputs treated as annual percentage rate (APR); monthly rate = APR / 12
- Debt payoff strategies: Avalanche (highest APR first), Snowball (lowest balance first)
- Savings projections assume constant monthly contribution and compound monthly

## File Upload Security (MVP-level only)
- File type validated by extension + magic bytes (not just MIME from browser)
- Files renamed to UUID on disk (original name stored in DB only)
- Max upload size: 25 MB

## Frontend Design System
- Palette: primary #0ea5e9 (sky), success #10b981 (emerald), warning #f59e0b (amber)
- Corner radii: cards 24–32px, buttons 16–20px
- Typography: system sans-serif stack (Inter/Slate)
- Animations: active:scale(0.98), 150ms ease-in-out on all interactive elements
