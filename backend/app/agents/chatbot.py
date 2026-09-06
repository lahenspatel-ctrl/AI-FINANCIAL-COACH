"""
Advisor Chatbot Agent.
Retrieves relevant transactions via tabular SQL + semantic search,
then generates a grounded LLM response. LLM never invents numbers.
"""
from __future__ import annotations

import json

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.llm.client import chat_complete
from backend.app.services.data_service import (
    get_debts,
    get_income,
    get_recent_chat,
    get_transactions_df,
)
from backend.app.services.vector_store import query_similar

_SYSTEM = """\
You are a personal financial advisor chatbot. You have access to the user's actual
financial data (shown below). Answer questions using ONLY the data provided.
If numbers aren't in the context, say "I don't have that data."
Never estimate, hallucinate, or make up financial figures.
Be concise, friendly, and practical. Format currency as $X,XXX."""


async def chat_respond(
    db: AsyncSession,
    user_message: str,
    user_id: str = "demo",
) -> str:
    # Tabular context
    txn_df = await get_transactions_df(db, user_id)
    debts = await get_debts(db, user_id)
    income_rows = await get_income(db, user_id)
    history = await get_recent_chat(db, user_id, limit=6)

    # Semantic retrieval for relevant transactions
    semantic_hits = query_similar(user_message, user_id=user_id, n_results=5)

    # Build compact financial context
    financial_context: dict = {}

    if not txn_df.empty:
        financial_context["total_transactions"] = len(txn_df)
        financial_context["total_income"] = round(
            float(txn_df[txn_df["amount"] > 0]["amount"].sum()), 2
        )
        financial_context["total_expenses"] = round(
            float(txn_df[txn_df["amount"] < 0]["amount"].sum()), 2
        )
        top_cats = (
            txn_df[txn_df["amount"] < 0]
            .assign(amount=lambda df: df["amount"].abs())
            .groupby("category")["amount"]
            .sum()
            .sort_values(ascending=False)
            .head(5)
            .round(2)
            .to_dict()
        )
        financial_context["top_expense_categories"] = top_cats

    if debts:
        financial_context["debts"] = [
            {"name": d.name, "balance": d.balance, "apr": f"{d.apr:.1%}"}
            for d in debts
        ]
        financial_context["total_debt"] = round(sum(d.balance for d in debts), 2)

    if income_rows:
        financial_context["monthly_income"] = round(
            sum(i.monthly_amount for i in income_rows), 2
        )

    if semantic_hits:
        financial_context["relevant_transactions"] = [
            h["document"] for h in semantic_hits[:5]
        ]

    # Build message list
    messages = [{"role": "system", "content": _SYSTEM}]
    messages.append(
        {
            "role": "system",
            "content": f"User's financial data:\n{json.dumps(financial_context, indent=2)}",
        }
    )
    for msg in history:
        messages.append({"role": msg.role, "content": msg.content})
    messages.append({"role": "user", "content": user_message})

    return await chat_complete("chat", messages, temperature=0.4, max_tokens=512)
