"""Unit tests for deterministic financial calculators — no LLM calls."""
import pytest
from backend.app.calculators.debt import DebtAccount, avalanche, snowball, minimum_only
from backend.app.calculators.savings import compound_savings, analyze_budget


def test_avalanche_pays_off():
    debts = [
        DebtAccount("High APR", 1000, 0.24, 50),
        DebtAccount("Low APR",  2000, 0.10, 50),
    ]
    result = avalanche(debts)
    assert result.total_months > 0
    assert result.total_interest_paid > 0
    assert result.strategy == "avalanche"
    # Avalanche should pay High APR card first
    assert result.order[0] == "High APR"


def test_snowball_pays_smallest_first():
    debts = [
        DebtAccount("Big",   5000, 0.15, 100),
        DebtAccount("Small",  500, 0.20, 25),
    ]
    result = snowball(debts)
    assert result.order[0] == "Small"


def test_avalanche_cheaper_than_snowball():
    debts = [
        DebtAccount("A", 3000, 0.25, 60),
        DebtAccount("B", 1000, 0.10, 25),
    ]
    av = avalanche(debts)
    sb = snowball(debts)
    assert av.total_interest_paid <= sb.total_interest_paid


def test_minimum_only_longest():
    debts = [DebtAccount("Card", 2000, 0.20, 40)]
    mo = minimum_only(debts)
    av = avalanche(debts)
    assert mo.total_months >= av.total_months


def test_compound_savings_grows():
    p = compound_savings(500, 0.07, 10)
    assert p.future_value > p.total_contributed
    assert p.total_interest_earned > 0
    assert p.future_value == pytest.approx(p.total_contributed + p.total_interest_earned, rel=0.01)


def test_compound_savings_zero_rate():
    p = compound_savings(100, 0.0, 5)
    assert p.future_value == pytest.approx(100 * 60, rel=0.01)


def test_analyze_budget_savings_rate():
    analysis = analyze_budget(5000, {"Rent": 1500, "Food": 500, "Entertainment": 200})
    assert analysis.total_expenses == pytest.approx(2200)
    assert analysis.net_cash_flow == pytest.approx(2800)
    assert analysis.savings_rate == pytest.approx(0.56, rel=0.01)


def test_analyze_budget_recommends_when_low_savings():
    analysis = analyze_budget(3000, {"Rent": 1400, "Food": 800, "Entertainment": 600, "Shopping": 400})
    # Net = 3000 - 3200 = negative → recommendations should mention it
    assert len(analysis.recommendations) > 0
