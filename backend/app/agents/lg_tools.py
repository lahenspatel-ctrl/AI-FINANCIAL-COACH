"""
LangChain tool definitions used inside LangGraph nodes.

Tools available to the chatbot ReAct agent:
  - web_search         : Tavily search for financial news / advice
  - get_transactions   : retrieves user transactions summary from SQLite
  - get_debts          : retrieves user debt records
  - get_income         : retrieves user income records
  - calculate_payoff   : deterministic debt payoff math (avalanche / snowball)
  - calculate_savings  : deterministic compound savings projection

All DB tools require a 'db_session' key in the LangGraph configurable dict.
"""
from __future__ import annotations

import json
from typing import Optional

from langchain_core.tools import tool
from langchain_tavily import TavilySearch
from loguru import logger

from backend.app.config import settings
from backend.app.calculators.debt import DebtAccount, avalanche, snowball
from backend.app.calculators.savings import compound_savings, analyze_budget


# ── Tavily web search ─────────────────────────────────────────────────────────

def get_tavily_tool(api_key: str | None = None) -> TavilySearch:
    key = api_key or settings.tavily_api_key or "no-key"
    return TavilySearch(
        max_results=settings.tavily_max_results,
        tavily_api_key=key,
        name="web_search",
        description=(
            "Search the web for current financial news, interest rates, financial advice, "
            "or explanations of financial concepts. Input should be a concise search query."
        ),
    )


def get_chatbot_tools(tavily_key: str | None = None) -> list:
    return [
        get_tavily_tool(api_key=tavily_key),
        calculate_debt_payoff,
        calculate_savings_projection,
        analyze_spending_budget,
    ]


# ── Financial data tools (synchronous — called inside async nodes via run_in_executor) ──

@tool
def calculate_debt_payoff(
    debts_json: str,
    strategy: str = "avalanche",
    extra_monthly: float = 0.0,
) -> str:
    """
    Calculate deterministic debt payoff schedule.

    Args:
        debts_json: JSON array of debt objects with keys:
                    name, balance, apr (decimal e.g. 0.19), minimum_payment
        strategy:   'avalanche' (highest APR first) or 'snowball' (lowest balance first)
        extra_monthly: extra dollars per month beyond minimums

    Returns JSON with total_months, total_interest_paid, total_paid, payoff_order.
    """
    try:
        raw = json.loads(debts_json)
        accounts = [
            DebtAccount(
                name=d["name"],
                balance=float(d["balance"]),
                apr=float(d["apr"]),
                minimum_payment=float(d["minimum_payment"]),
            )
            for d in raw
        ]
        fn = avalanche if strategy == "avalanche" else snowball
        result = fn(accounts, extra_monthly=extra_monthly)
        return json.dumps({
            "strategy": result.strategy,
            "total_months": result.total_months,
            "total_interest_paid": result.total_interest_paid,
            "total_paid": result.total_paid,
            "payoff_order": result.order,
        })
    except Exception as exc:
        return json.dumps({"error": str(exc)})


@tool
def calculate_savings_projection(
    monthly_contribution: float,
    annual_rate: float,
    years: int,
) -> str:
    """
    Project compound savings growth over time.

    Args:
        monthly_contribution: dollars saved each month
        annual_rate: expected annual return as decimal (e.g. 0.06 for 6%)
        years: number of years to project

    Returns JSON with future_value, total_contributed, total_interest_earned.
    """
    try:
        p = compound_savings(monthly_contribution, annual_rate, years)
        return json.dumps({
            "monthly_contribution": p.monthly_contribution,
            "annual_rate": f"{p.annual_rate:.1%}",
            "years": p.years,
            "future_value": p.future_value,
            "total_contributed": p.total_contributed,
            "total_interest_earned": p.total_interest_earned,
        })
    except Exception as exc:
        return json.dumps({"error": str(exc)})


@tool
def analyze_spending_budget(
    monthly_income: float,
    expense_by_category_json: str,
) -> str:
    """
    Analyze a monthly budget and get rule-based recommendations.

    Args:
        monthly_income: total monthly income in dollars
        expense_by_category_json: JSON object mapping category name -> monthly spend

    Returns JSON with net_cash_flow, savings_rate, and recommendations list.
    """
    try:
        cats = json.loads(expense_by_category_json)
        analysis = analyze_budget(monthly_income, {k: float(v) for k, v in cats.items()})
        return json.dumps({
            "total_income": analysis.total_income,
            "total_expenses": analysis.total_expenses,
            "net_cash_flow": analysis.net_cash_flow,
            "savings_rate": f"{analysis.savings_rate:.1%}",
            "recommendations": analysis.recommendations,
        })
    except Exception as exc:
        return json.dumps({"error": str(exc)})


# Default tools (used when no per-user key is provided)
CHATBOT_TOOLS = get_chatbot_tools()
