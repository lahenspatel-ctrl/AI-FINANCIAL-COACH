"""
Deterministic savings & budget calculators.
LLMs receive computed results for explanation only.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SavingsProjection:
    monthly_contribution: float
    annual_rate: float          # e.g. 0.05 for 5%
    years: int
    future_value: float
    total_contributed: float
    total_interest_earned: float


def compound_savings(
    monthly_contribution: float,
    annual_rate: float,
    years: int,
) -> SavingsProjection:
    monthly_rate = annual_rate / 12
    n = years * 12
    if monthly_rate == 0:
        fv = monthly_contribution * n
    else:
        fv = monthly_contribution * ((1 + monthly_rate) ** n - 1) / monthly_rate
    contributed = monthly_contribution * n
    return SavingsProjection(
        monthly_contribution=round(monthly_contribution, 2),
        annual_rate=annual_rate,
        years=years,
        future_value=round(fv, 2),
        total_contributed=round(contributed, 2),
        total_interest_earned=round(fv - contributed, 2),
    )


@dataclass
class BudgetAnalysis:
    total_income: float
    total_expenses: float
    net_cash_flow: float
    savings_rate: float
    expense_by_category: dict[str, float]
    recommendations: list[str]


def analyze_budget(
    monthly_income: float,
    expense_by_category: dict[str, float],
) -> BudgetAnalysis:
    total_expenses = sum(expense_by_category.values())
    net = monthly_income - total_expenses
    savings_rate = (net / monthly_income) if monthly_income > 0 else 0.0

    recs: list[str] = []
    if savings_rate < 0.10:
        recs.append("Savings rate is below 10%. Try reducing the top spending category.")
    if savings_rate < 0:
        recs.append("Expenses exceed income this period. Review non-essential spending.")
    if savings_rate >= 0.20:
        recs.append("Great savings rate! Consider investing surplus in a diversified fund.")

    # Flag top category if > 40% of expenses
    if expense_by_category:
        top_cat, top_amt = max(expense_by_category.items(), key=lambda x: x[1])
        if total_expenses > 0 and top_amt / total_expenses > 0.40:
            recs.append(
                f"{top_cat!r} accounts for over 40% of expenses. "
                "Examine if this can be reduced."
            )

    return BudgetAnalysis(
        total_income=round(monthly_income, 2),
        total_expenses=round(total_expenses, 2),
        net_cash_flow=round(net, 2),
        savings_rate=round(savings_rate, 4),
        expense_by_category={k: round(v, 2) for k, v in expense_by_category.items()},
        recommendations=recs,
    )
