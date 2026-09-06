from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field


class TransactionIn(BaseModel):
    txn_date: date
    description: str
    amount: float
    category: str | None = None
    sub_category: str | None = None
    account: str | None = None
    source_file_id: str | None = None


class TransactionOut(TransactionIn):
    id: str
    user_id: str
    created_at: datetime

    model_config = {"from_attributes": True}


class DebtIn(BaseModel):
    name: str
    balance: float = Field(gt=0)
    apr: float = Field(gt=0, lt=2, description="APR as decimal, e.g. 0.19 for 19%")
    minimum_payment: float = Field(gt=0)
    debt_type: str = "other"


class DebtOut(DebtIn):
    id: str
    user_id: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class IncomeIn(BaseModel):
    source: str
    monthly_amount: float = Field(gt=0)
    income_type: str = "salary"


class IncomeOut(IncomeIn):
    id: str
    user_id: str
    created_at: datetime

    model_config = {"from_attributes": True}


class UploadedFileOut(BaseModel):
    id: str
    original_filename: str
    file_type: str
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class ChatMessageIn(BaseModel):
    content: str


class ChatMessageOut(BaseModel):
    id: int
    role: Literal["user", "assistant"]
    content: str
    created_at: datetime

    model_config = {"from_attributes": True}


class DashboardSummary(BaseModel):
    total_income: float
    total_expenses: float
    net_cash_flow: float
    total_debt: float
    top_categories: list[dict]
    monthly_trend: list[dict]
    debt_payoff_months_avalanche: int | None = None
    debt_payoff_months_snowball: int | None = None
    savings_rate: float | None = None


class AgentRunOut(BaseModel):
    id: str
    status: str
    trigger: str
    created_at: datetime
    finished_at: datetime | None = None
    summary_json: str | None = None

    model_config = {"from_attributes": True}
