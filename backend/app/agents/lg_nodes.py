"""
LangGraph node functions for the financial analysis pipeline.

Each node:
  1. Reads data from PipelineState
  2. Runs deterministic Python math (never LLM for numbers)
  3. Calls LLM with computed numbers as context for plain-language explanation
  4. Appends SSE events to state["events"]
  5. Returns a state patch dict
"""
from __future__ import annotations

import json
from typing import Any

import pandas as pd
from langchain_core.messages import HumanMessage, SystemMessage
from loguru import logger

from backend.app.agents.lg_llm import get_chat_model_with_fallbacks
from backend.app.agents.lg_state import PipelineState
from backend.app.calculators.debt import DebtAccount, avalanche, minimum_only, snowball
from backend.app.calculators.savings import analyze_budget, compound_savings
from backend.app.llm.client import chat_complete_json  # used only for categorization batching


def _evt(agent: str, status: str, message: str, data: dict | None = None) -> dict:
    return {"agent": agent, "status": status, "message": message, "data": data}


# ── Node 1: Data Categorizer ──────────────────────────────────────────────────

async def categorize_node(state: PipelineState) -> dict:
    selected = state.get("selected_agents")
    if selected is not None and "categorizer" not in selected:
        return {"events": [], "categorization_result": {}}

    events: list[dict] = [_evt("categorizer", "started", "Categorizing transactions…")]

    try:
        if not state["transactions_json"] or state["transactions_json"] == "[]":
            events.append(_evt("categorizer", "complete", "No transactions to categorize."))
            return {"events": events, "categorization_result": {}}

        df = pd.read_json(state["transactions_json"], orient="records")
        uncategorized = df[df["category"].isna() | (df["category"] == "")]

        if uncategorized.empty:
            events.append(_evt("categorizer", "complete", "All transactions already categorized."))
            return {"events": events, "categorization_result": {"categorized": 0}}

        events.append(
            _evt("categorizer", "progress", f"Categorizing {len(uncategorized)} transactions…")
        )

        _or_key: str | None = state.get("openrouter_key") or None

        _SYSTEM = (
            "You are a financial transaction categorizer. Given a list of transaction "
            "descriptions and amounts, return a JSON array where each element has:\n"
            '  "index": (same integer as input),\n'
            '  "category": one of [Food & Dining, Shopping, Transportation, Housing, '
            "Utilities, Healthcare, Entertainment, Travel, Education, Personal Care, "
            "Income, Transfers, Investments, Fees & Charges, Other],\n"
            '  "sub_category": a short specific label (e.g. "Groceries", "Rent", "Netflix")\n'
            "Return ONLY the JSON array. No explanation."
        )

        batch_size = 30
        categorized_count = 0
        category_map: dict[int, dict] = {}

        rows = uncategorized.reset_index(drop=True)
        for i in range(0, len(rows), batch_size):
            batch = rows.iloc[i : i + batch_size]
            payload = [
                {"index": j, "description": row["description"], "amount": row["amount"]}
                for j, (_, row) in enumerate(batch.iterrows())
            ]
            try:
                result = await chat_complete_json(
                    "classifier",
                    [
                        {"role": "system", "content": _SYSTEM},
                        {"role": "user", "content": json.dumps(payload)},
                    ],
                    api_key=_or_key,
                    max_tokens=512,
                )
                items = result if isinstance(result, list) else result.get("results", [])
                for item in items:
                    idx = item.get("index", 0)
                    orig_idx = uncategorized.index[i + idx] if (i + idx) < len(uncategorized) else -1
                    if orig_idx >= 0:
                        category_map[int(orig_idx)] = {
                            "category": item.get("category", "Other"),
                            "sub_category": item.get("sub_category"),
                        }
                        categorized_count += 1
            except Exception as exc:
                logger.warning(f"Categorizer batch {i} failed: {exc}")

        events.append(
            _evt(
                "categorizer",
                "complete",
                f"Categorized {categorized_count} transactions.",
                data={"categorized": categorized_count, "category_map": category_map},
            )
        )
        return {
            "events": events,
            "categorization_result": {
                "categorized": categorized_count,
                "category_map": category_map,
            },
        }

    except Exception as exc:
        logger.error(f"categorize_node error: {exc}")
        events.append(_evt("categorizer", "error", str(exc)))
        return {"events": events, "categorization_result": {}, "error": str(exc)}


# ── Node 2: Debt Analyzer ─────────────────────────────────────────────────────

async def debt_analyzer_node(state: PipelineState) -> dict:
    selected = state.get("selected_agents")
    if selected is not None and "debt_analyzer" not in selected:
        return {"events": [], "debt_result": None}

    events: list[dict] = [_evt("debt_analyzer", "started", "Analyzing debts…")]
    _or_key: str | None = state.get("openrouter_key") or None

    try:
        debts = state.get("debts", [])
        if not debts:
            events.append(
                _evt("debt_analyzer", "complete", "No debts on file. Add debts to unlock payoff analysis.")
            )
            return {"events": events, "debt_result": None}

        accounts = [
            DebtAccount(
                name=d["name"],
                balance=float(d["balance"]),
                apr=float(d["apr"]),
                minimum_payment=float(d["minimum_payment"]),
            )
            for d in debts
        ]

        events.append(_evt("debt_analyzer", "progress", "Running payoff simulations…"))
        av = avalanche(accounts)
        sb = snowball(accounts)
        mo = minimum_only(accounts)

        computed = {
            "total_current_debt": round(sum(d["balance"] for d in debts), 2),
            "debt_count": len(debts),
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
            "interest_saved_by_avalanche": round(
                mo.total_interest_paid - av.total_interest_paid, 2
            ),
        }

        events.append(_evt("debt_analyzer", "progress", "Generating plain-language explanation…"))

        llm = get_chat_model_with_fallbacks("analyst", api_key=_or_key)
        msgs = [
            SystemMessage(
                content=(
                    "You are a friendly financial advisor. The user's debt payoff analysis "
                    "has been computed deterministically. Write 2-3 plain-language sentences "
                    "explaining the results. Reference exact numbers. Never invent figures."
                )
            ),
            HumanMessage(
                content=f"Debt analysis:\n{json.dumps(computed, indent=2)}\n\nExplain to the user."
            ),
        ]
        try:
            resp = await llm.ainvoke(msgs)
            explanation = resp.content
        except Exception:
            explanation = (
                f"Using the avalanche strategy pays off your ${computed['total_current_debt']:,.0f} "
                f"in debt in {av.total_months} months, saving ${computed['interest_saved_by_avalanche']:,.0f} "
                f"vs. paying minimums only."
            )

        events.append(_evt("debt_analyzer", "complete", explanation, data=computed))
        return {"events": events, "debt_result": computed}

    except Exception as exc:
        logger.error(f"debt_analyzer_node error: {exc}")
        events.append(_evt("debt_analyzer", "error", str(exc)))
        return {"events": events, "debt_result": None, "error": str(exc)}


# ── Node 3: Savings Strategy ──────────────────────────────────────────────────

async def savings_node(state: PipelineState) -> dict:
    selected = state.get("selected_agents")
    if selected is not None and "savings_agent" not in selected:
        return {"events": [], "savings_result": None}

    events: list[dict] = [_evt("savings_agent", "started", "Building savings projections…")]
    _or_key: str | None = state.get("openrouter_key") or None

    try:
        income_rows = state.get("income", [])
        txn_json = state.get("transactions_json", "[]")

        monthly_income = sum(float(i["monthly_amount"]) for i in income_rows)

        if txn_json and txn_json != "[]":
            df = pd.read_json(txn_json, orient="records")
            expenses = df[df["amount"] < 0]["amount"].sum()
            days = (
                (pd.to_datetime(df["txn_date"]).max() - pd.to_datetime(df["txn_date"]).min()).days
                if len(df) > 1
                else 30
            )
            monthly_expenses = abs(expenses) / max(1, days // 30)
        else:
            monthly_expenses = 0.0

        potential_savings = max(0.0, monthly_income - monthly_expenses)

        projections: dict[str, Any] = {
            "monthly_income": round(monthly_income, 2),
            "monthly_expenses": round(monthly_expenses, 2),
            "potential_monthly_savings": round(potential_savings, 2),
            "scenarios": {},
        }

        if potential_savings > 0:
            for years, rate in [(1, 0.04), (3, 0.05), (5, 0.06), (10, 0.07)]:
                p = compound_savings(potential_savings, rate, years)
                projections["scenarios"][f"{years}yr_{rate:.0%}"] = {
                    "future_value": p.future_value,
                    "interest_earned": p.total_interest_earned,
                }

        events.append(_evt("savings_agent", "progress", "Generating savings recommendations…"))

        llm = get_chat_model_with_fallbacks("analyst", api_key=_or_key)
        msgs = [
            SystemMessage(
                content=(
                    "You are a savings coach. Based on the computed projections below, "
                    "give 2-3 bullet-point actionable tips. Use only the numbers provided. "
                    "Never invent figures."
                )
            ),
            HumanMessage(content=f"Savings data:\n{json.dumps(projections, indent=2)}"),
        ]
        try:
            resp = await llm.ainvoke(msgs)
            advice = resp.content
        except Exception:
            advice = (
                f"You could save ${potential_savings:,.0f}/month. Over 5 years at 6%, "
                f"that grows to ${projections['scenarios'].get('5yr_6%', {}).get('future_value', 0):,.0f}."
            )

        events.append(_evt("savings_agent", "complete", advice, data=projections))
        return {"events": events, "savings_result": projections}

    except Exception as exc:
        logger.error(f"savings_node error: {exc}")
        events.append(_evt("savings_agent", "error", str(exc)))
        return {"events": events, "savings_result": None, "error": str(exc)}


# ── Node 4: Budget Advisor ────────────────────────────────────────────────────

async def budget_advisor_node(state: PipelineState) -> dict:
    selected = state.get("selected_agents")
    if selected is not None and "budget_advisor" not in selected:
        return {"events": [], "budget_result": None}

    events: list[dict] = [_evt("budget_advisor", "started", "Analyzing your budget…")]
    _or_key: str | None = state.get("openrouter_key") or None

    try:
        txn_json = state.get("transactions_json", "[]")
        income_rows = state.get("income", [])
        monthly_income = sum(float(i["monthly_amount"]) for i in income_rows)

        if not txn_json or txn_json == "[]":
            events.append(
                _evt("budget_advisor", "complete", "No transaction data yet. Upload a bank statement first.")
            )
            return {"events": events, "budget_result": None}

        df = pd.read_json(txn_json, orient="records")
        expenses_df = df[df["amount"] < 0].copy()
        expenses_df["amount"] = expenses_df["amount"].abs()

        days = (
            (pd.to_datetime(df["txn_date"]).max() - pd.to_datetime(df["txn_date"]).min()).days
            if len(df) > 1
            else 30
        )
        months = max(1, days // 30)

        cat_col = "category" if "category" in expenses_df.columns else None
        if cat_col:
            cat_totals = (
                expenses_df.groupby(cat_col)["amount"].sum() / months
            ).round(2).sort_values(ascending=False)
            expense_by_cat = cat_totals.to_dict()
        else:
            expense_by_cat = {"Uncategorized": round(expenses_df["amount"].sum() / months, 2)}

        analysis = analyze_budget(monthly_income, expense_by_cat)

        events.append(_evt("budget_advisor", "progress", "Generating budget recommendations…"))

        llm = get_chat_model_with_fallbacks("analyst", api_key=_or_key)
        msgs = [
            SystemMessage(
                content=(
                    "You are a budget advisor. Based on the user's actual spending data, "
                    "identify their top 2-3 problem areas and give specific actionable advice. "
                    "Use exact dollar figures. Keep response to 3-4 sentences."
                )
            ),
            HumanMessage(
                content=json.dumps(
                    {
                        "monthly_income": analysis.total_income,
                        "monthly_expenses": analysis.total_expenses,
                        "net_cash_flow": analysis.net_cash_flow,
                        "savings_rate": f"{analysis.savings_rate:.1%}",
                        "expense_by_category": analysis.expense_by_category,
                        "system_flags": analysis.recommendations,
                    },
                    indent=2,
                )
            ),
        ]
        try:
            resp = await llm.ainvoke(msgs)
            advice = resp.content
        except Exception:
            advice = " ".join(analysis.recommendations) or "Budget analysis complete."

        result = {
            "total_income": analysis.total_income,
            "total_expenses": analysis.total_expenses,
            "net_cash_flow": analysis.net_cash_flow,
            "savings_rate": analysis.savings_rate,
            "top_categories": [
                {"category": k, "amount": v}
                for k, v in list(expense_by_cat.items())[:8]
            ],
        }

        events.append(_evt("budget_advisor", "complete", advice, data=result))
        return {"events": events, "budget_result": result}

    except Exception as exc:
        logger.error(f"budget_advisor_node error: {exc}")
        events.append(_evt("budget_advisor", "error", str(exc)))
        return {"events": events, "budget_result": None, "error": str(exc)}


# ── Conditional edge: skip remaining nodes on hard error ─────────────────────

def should_continue(state: PipelineState) -> str:
    if state.get("error"):
        return "end"
    return "continue"
