"""
Savings Strategy Agent.
Computes savings projections deterministically, then LLM crafts actionable advice.
"""
from __future__ import annotations

import json
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.agents.events import AgentEvent
from backend.app.calculators.savings import compound_savings
from backend.app.llm.client import chat_complete
from backend.app.services.data_service import get_income, get_transactions_df

_SYSTEM = """\
You are a savings coach. Based on the computed savings projections below, give 2-3 bullet points
of specific, actionable advice. Reference the actual numbers provided.
Do NOT invent numbers or percentages not shown in the context."""


async def run_savings_agent(
    db: AsyncSession,
    user_id: str = "demo",
) -> AsyncGenerator[AgentEvent, None]:
    yield AgentEvent("savings_agent", "started", "Building savings strategy…")

    income_rows = await get_income(db, user_id)
    txn_df = await get_transactions_df(db, user_id)

    monthly_income = sum(i.monthly_amount for i in income_rows)

    if txn_df.empty:
        monthly_expenses = 0.0
    else:
        expenses = txn_df[txn_df["amount"] < 0]["amount"].sum()
        months_of_data = max(
            1,
            (txn_df["txn_date"].max() - txn_df["txn_date"].min()).days // 30,
        ) if len(txn_df) > 1 else 1
        monthly_expenses = abs(expenses) / months_of_data

    potential_savings = max(0.0, monthly_income - monthly_expenses)

    projections = {
        "monthly_income": round(monthly_income, 2),
        "monthly_expenses": round(monthly_expenses, 2),
        "potential_monthly_savings": round(potential_savings, 2),
        "projections": {},
    }

    if potential_savings > 0:
        for years, rate in [(1, 0.04), (3, 0.05), (5, 0.06), (10, 0.07)]:
            p = compound_savings(potential_savings, rate, years)
            projections["projections"][f"{years}yr"] = {
                "future_value": p.future_value,
                "interest_earned": p.total_interest_earned,
                "rate": f"{rate:.0%}",
            }

    yield AgentEvent("savings_agent", "progress", "Generating savings recommendations…")

    messages = [
        {"role": "system", "content": _SYSTEM},
        {
            "role": "user",
            "content": f"Savings analysis:\n{json.dumps(projections, indent=2)}",
        },
    ]
    try:
        advice = await chat_complete("analyst", messages, max_tokens=300)
    except Exception:
        advice = (
            f"Based on your income of ${monthly_income:,.0f}/month and expenses of "
            f"${monthly_expenses:,.0f}/month, you could save ${potential_savings:,.0f} monthly."
        )

    yield AgentEvent(
        "savings_agent",
        "complete",
        advice,
        data=projections,
    )
