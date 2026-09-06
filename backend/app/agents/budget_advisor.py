"""
Budget Advisor Agent.
Uses deterministic pandas aggregations + LLM for plain-language advice.
"""
from __future__ import annotations

import json
from typing import AsyncGenerator

import pandas as pd
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.agents.events import AgentEvent
from backend.app.calculators.savings import analyze_budget
from backend.app.llm.client import chat_complete
from backend.app.services.data_service import get_income, get_transactions_df

_SYSTEM = """\
You are a budget advisor. Based on the user's actual spending data below,
identify their top 2-3 spending problem areas and give specific, actionable advice.
Use the exact dollar figures provided. Keep your response to 3-4 sentences."""


async def run_budget_advisor(
    db: AsyncSession,
    user_id: str = "demo",
) -> AsyncGenerator[AgentEvent, None]:
    yield AgentEvent("budget_advisor", "started", "Analyzing your budget…")

    txn_df = await get_transactions_df(db, user_id)
    income_rows = await get_income(db, user_id)
    monthly_income = sum(i.monthly_amount for i in income_rows)

    if txn_df.empty:
        yield AgentEvent("budget_advisor", "complete", "No transaction data found. Upload a bank statement to get budget advice.")
        return

    # Expenses only (negative amounts)
    expenses_df = txn_df[txn_df["amount"] < 0].copy()
    expenses_df["amount"] = expenses_df["amount"].abs()

    months = max(
        1,
        (txn_df["txn_date"].max() - txn_df["txn_date"].min()).days // 30,
    ) if len(txn_df) > 1 else 1

    cat_totals = (
        expenses_df.groupby("category")["amount"].sum() / months
    ).round(2).sort_values(ascending=False)

    expense_by_cat = cat_totals.to_dict()

    analysis = analyze_budget(monthly_income, expense_by_cat)

    yield AgentEvent("budget_advisor", "progress", "Generating budget recommendations…")

    messages = [
        {"role": "system", "content": _SYSTEM},
        {
            "role": "user",
            "content": json.dumps(
                {
                    "monthly_income": analysis.total_income,
                    "monthly_expenses": analysis.total_expenses,
                    "net_cash_flow": analysis.net_cash_flow,
                    "savings_rate": f"{analysis.savings_rate:.1%}",
                    "expense_by_category": analysis.expense_by_category,
                    "system_recommendations": analysis.recommendations,
                },
                indent=2,
            ),
        },
    ]

    try:
        advice = await chat_complete("analyst", messages, max_tokens=350)
    except Exception:
        advice = " ".join(analysis.recommendations) or "Budget analysis complete."

    top_categories = [
        {"category": k, "amount": v}
        for k, v in list(expense_by_cat.items())[:8]
    ]

    yield AgentEvent(
        "budget_advisor",
        "complete",
        advice,
        data={
            "total_income": analysis.total_income,
            "total_expenses": analysis.total_expenses,
            "net_cash_flow": analysis.net_cash_flow,
            "savings_rate": analysis.savings_rate,
            "top_categories": top_categories,
        },
    )
