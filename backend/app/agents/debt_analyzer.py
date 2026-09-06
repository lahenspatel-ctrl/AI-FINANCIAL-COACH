"""
Debt Analyzer Agent.
Runs deterministic payoff math, then asks LLM to explain results in plain language.
"""
from __future__ import annotations

import json
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.agents.events import AgentEvent
from backend.app.calculators.debt import DebtAccount, avalanche, snowball, minimum_only
from backend.app.llm.client import chat_complete
from backend.app.services.data_service import get_debts

_SYSTEM = """\
You are a friendly financial advisor. The user's debt payoff analysis has been computed.
Write a 2-3 sentence plain-language explanation of the results.
Focus on practical insights: how much interest they save, and which strategy is better.
Do NOT invent numbers — use only the numbers provided."""


async def run_debt_analyzer(
    db: AsyncSession,
    user_id: str = "demo",
) -> AsyncGenerator[AgentEvent, None]:
    yield AgentEvent("debt_analyzer", "started", "Analyzing debts…")

    debts = await get_debts(db, user_id)
    if not debts:
        yield AgentEvent("debt_analyzer", "complete", "No debts found. Add debts to get payoff analysis.")
        return

    accounts = [
        DebtAccount(
            name=d.name,
            balance=d.balance,
            apr=d.apr,
            minimum_payment=d.minimum_payment,
        )
        for d in debts
    ]

    yield AgentEvent("debt_analyzer", "progress", "Running avalanche & snowball simulations…")

    av = avalanche(accounts)
    sb = snowball(accounts)
    mo = minimum_only(accounts)

    results = {
        "avalanche": {
            "months": av.total_months,
            "total_interest": av.total_interest_paid,
            "total_paid": av.total_paid,
            "payoff_order": av.order,
        },
        "snowball": {
            "months": sb.total_months,
            "total_interest": sb.total_interest_paid,
            "total_paid": sb.total_paid,
            "payoff_order": sb.order,
        },
        "minimum_only": {
            "months": mo.total_months,
            "total_interest": mo.total_interest_paid,
        },
        "total_current_debt": round(sum(d.balance for d in debts), 2),
        "debt_count": len(debts),
    }

    yield AgentEvent("debt_analyzer", "progress", "Generating plain-language explanation…")

    messages = [
        {"role": "system", "content": _SYSTEM},
        {
            "role": "user",
            "content": (
                f"Debt payoff analysis results:\n{json.dumps(results, indent=2)}\n\n"
                "Explain these results to the user in plain English."
            ),
        },
    ]

    try:
        explanation = await chat_complete("analyst", messages, max_tokens=300)
    except Exception:
        explanation = (
            f"Avalanche strategy pays off your debt in {av.total_months} months, "
            f"saving ${mo.total_interest_paid - av.total_interest_paid:,.0f} in interest "
            f"compared to minimums only."
        )

    yield AgentEvent(
        "debt_analyzer",
        "complete",
        explanation,
        data=results,
    )
