"""
Parses JSON files containing debt lists or income lists.
Expected schema (debts):
  [{"name": str, "balance": float, "apr": float, "minimum_payment": float, "debt_type": str}, ...]

Expected schema (income):
  [{"source": str, "monthly_amount": float, "income_type": str}, ...]
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Union

from backend.app.schemas.finance import DebtIn, IncomeIn


def parse_json_debts(path: Path) -> list[DebtIn]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        data = data.get("debts", [data])
    return [DebtIn(**item) for item in data if _looks_like_debt(item)]


def parse_json_income(path: Path) -> list[IncomeIn]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        data = data.get("income", [data])
    return [IncomeIn(**item) for item in data if _looks_like_income(item)]


def _looks_like_debt(d: dict) -> bool:
    return "balance" in d and "apr" in d


def _looks_like_income(d: dict) -> bool:
    return "monthly_amount" in d or "monthly_income" in d
