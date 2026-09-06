"""
Deterministic debt payoff calculators.
All numbers are computed here; LLMs only receive results for explanation.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import NamedTuple


@dataclass
class DebtAccount:
    name: str
    balance: float
    apr: float          # annual, e.g. 0.19
    minimum_payment: float

    @property
    def monthly_rate(self) -> float:
        return self.apr / 12


class MonthlySnapshot(NamedTuple):
    month: int
    name: str
    balance: float
    interest_charged: float
    payment: float


@dataclass
class PayoffResult:
    strategy: str
    total_months: int
    total_interest_paid: float
    total_paid: float
    schedule: list[MonthlySnapshot] = field(default_factory=list)
    order: list[str] = field(default_factory=list)  # debt names in payoff order


def _simulate(
    debts: list[DebtAccount],
    extra_monthly: float,
    strategy: str,
) -> PayoffResult:
    """Run a month-by-month debt payoff simulation."""
    accounts = [
        {"name": d.name, "balance": d.balance, "rate": d.monthly_rate, "min": d.minimum_payment}
        for d in debts
    ]
    total_interest = 0.0
    total_paid = 0.0
    schedule: list[MonthlySnapshot] = []
    order: list[str] = []
    month = 0

    while any(a["balance"] > 0.01 for a in accounts) and month < 600:
        month += 1
        active = [a for a in accounts if a["balance"] > 0.01]

        # Sort by strategy
        if strategy == "avalanche":
            active.sort(key=lambda a: -a["rate"])  # highest rate first
        else:
            active.sort(key=lambda a: a["balance"])  # lowest balance first

        # Apply interest to all active accounts
        for a in active:
            interest = a["balance"] * a["rate"]
            a["balance"] += interest
            total_interest += interest
            schedule.append(
                MonthlySnapshot(month, a["name"], round(a["balance"], 2), round(interest, 2), 0)
            )

        # Pay minimums on all
        extra = extra_monthly
        for a in active:
            payment = min(a["min"], a["balance"])
            a["balance"] -= payment
            total_paid += payment

        # Apply extra to focus debt (first in sorted order)
        for a in active:
            if a["balance"] > 0.01:
                extra_applied = min(extra, a["balance"])
                a["balance"] -= extra_applied
                total_paid += extra_applied
                extra -= extra_applied
                if a["balance"] < 0.01:
                    a["balance"] = 0.0
                    if a["name"] not in order:
                        order.append(a["name"])
                break

        # Mark any newly paid-off debts
        for a in active:
            if a["balance"] < 0.01:
                a["balance"] = 0.0
                if a["name"] not in order:
                    order.append(a["name"])

    return PayoffResult(
        strategy=strategy,
        total_months=month,
        total_interest_paid=round(total_interest, 2),
        total_paid=round(total_paid, 2),
        schedule=schedule,
        order=order,
    )


def avalanche(debts: list[DebtAccount], extra_monthly: float = 0.0) -> PayoffResult:
    return _simulate(debts, extra_monthly, "avalanche")


def snowball(debts: list[DebtAccount], extra_monthly: float = 0.0) -> PayoffResult:
    return _simulate(debts, extra_monthly, "snowball")


def minimum_only(debts: list[DebtAccount]) -> PayoffResult:
    return _simulate(debts, 0.0, "avalanche")
