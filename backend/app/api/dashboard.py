"""
Dashboard data endpoint — returns aggregated financial summary for the charts.
All math is deterministic Python/pandas; no LLM involved here.
"""
from __future__ import annotations

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete as sql_delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.calculators.debt import DebtAccount, avalanche, snowball
from backend.app.db.database import get_db
from backend.app.db.models import Debt, Income, Transaction
from backend.app.schemas.finance import (
    DashboardSummary,
    DebtIn,
    DebtOut,
    IncomeIn,
    IncomeOut,
)
from backend.app.services.data_service import clear_user_data, get_debts, get_income, get_transactions_df
from backend.app.services.vector_store import reset_user_data

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/summary", response_model=DashboardSummary)
async def get_summary(user_id: str = "demo", db: AsyncSession = Depends(get_db)):
    txn_df = await get_transactions_df(db, user_id)
    debts_orm = await get_debts(db, user_id)
    income_orm = await get_income(db, user_id)

    monthly_income = sum(i.monthly_amount for i in income_orm)
    total_debt = round(sum(d.balance for d in debts_orm), 2)

    if txn_df.empty:
        return DashboardSummary(
            total_income=monthly_income,
            total_expenses=0.0,
            net_cash_flow=monthly_income,
            total_debt=total_debt,
            top_categories=[],
            monthly_trend=[],
        )

    total_income_txn = float(txn_df[txn_df["amount"] > 0]["amount"].sum())
    total_expenses = abs(float(txn_df[txn_df["amount"] < 0]["amount"].sum()))
    net = total_income_txn - total_expenses
    savings_rate = (net / total_income_txn) if total_income_txn > 0 else None

    # Top categories by absolute spend
    top_categories: list[dict] = []
    if "category" in txn_df.columns:
        top = (
            txn_df[txn_df["amount"] < 0]
            .assign(amount=lambda df: df["amount"].abs())
            .groupby("category")["amount"]
            .sum()
            .sort_values(ascending=False)
            .head(8)
            .round(2)
        )
        top_categories = [{"category": k, "amount": float(v)} for k, v in top.items()]

    # Monthly trend — avoid groupby.apply returning dict (pandas 2.x deprecation)
    txn_df = txn_df.copy()
    txn_df["month"] = pd.to_datetime(txn_df["txn_date"]).dt.to_period("M").astype(str)
    income_by_month = (
        txn_df[txn_df["amount"] > 0].groupby("month")["amount"].sum().round(2)
    )
    expense_by_month = (
        txn_df[txn_df["amount"] < 0].groupby("month")["amount"].sum().abs().round(2)
    )
    all_months = sorted(set(txn_df["month"].unique()))
    trend = [
        {
            "month": m,
            "income": float(income_by_month.get(m, 0)),
            "expenses": float(expense_by_month.get(m, 0)),
        }
        for m in all_months
    ]

    # Debt payoff months
    av_months = sb_months = None
    if debts_orm:
        accounts = [
            DebtAccount(d.name, d.balance, d.apr, d.minimum_payment) for d in debts_orm
        ]
        av_months = avalanche(accounts).total_months
        sb_months = snowball(accounts).total_months

    return DashboardSummary(
        total_income=round(total_income_txn, 2),
        total_expenses=round(total_expenses, 2),
        net_cash_flow=round(net, 2),
        total_debt=total_debt,
        top_categories=top_categories,
        monthly_trend=trend,
        debt_payoff_months_avalanche=av_months,
        debt_payoff_months_snowball=sb_months,
        savings_rate=round(savings_rate, 4) if savings_rate is not None else None,
    )


@router.get("/transactions")
async def list_transactions(
    user_id: str = "demo",
    limit: int = 100,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Transaction)
        .where(Transaction.user_id == user_id)
        .order_by(Transaction.txn_date.desc())
        .offset(offset)
        .limit(limit)
    )
    txns = result.scalars().all()
    return [
        {
            "id": t.id,
            "date": str(t.txn_date),
            "description": t.description,
            "amount": t.amount,
            "category": t.category,
            "sub_category": t.sub_category,
            "account": t.account,
        }
        for t in txns
    ]


@router.get("/debts")
async def list_debts(user_id: str = "demo", db: AsyncSession = Depends(get_db)):
    debts = await get_debts(db, user_id)
    return [DebtOut.model_validate(d) for d in debts]


@router.post("/debts", response_model=DebtOut)
async def add_debt(
    body: DebtIn,
    user_id: str = "demo",
    db: AsyncSession = Depends(get_db),
):
    rec = Debt(user_id=user_id, **body.model_dump())
    db.add(rec)
    await db.commit()
    await db.refresh(rec)
    return DebtOut.model_validate(rec)


@router.get("/income")
async def list_income(user_id: str = "demo", db: AsyncSession = Depends(get_db)):
    income = await get_income(db, user_id)
    return [IncomeOut.model_validate(i) for i in income]


@router.post("/income", response_model=IncomeOut)
async def add_income(
    body: IncomeIn,
    user_id: str = "demo",
    db: AsyncSession = Depends(get_db),
):
    rec = Income(user_id=user_id, **body.model_dump())
    db.add(rec)
    await db.commit()
    await db.refresh(rec)
    return IncomeOut.model_validate(rec)


@router.delete("/debts/{debt_id}", status_code=204)
async def delete_debt(
    debt_id: str,
    user_id: str = "demo",
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        sql_delete(Debt).where(Debt.id == debt_id, Debt.user_id == user_id)
    )
    if result.rowcount == 0:
        raise HTTPException(404, "Debt not found")
    await db.commit()


@router.delete("/income/{income_id}", status_code=204)
async def delete_income(
    income_id: str,
    user_id: str = "demo",
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        sql_delete(Income).where(Income.id == income_id, Income.user_id == user_id)
    )
    if result.rowcount == 0:
        raise HTTPException(404, "Income not found")
    await db.commit()


@router.post("/reset", status_code=204)
async def reset_all_data(user_id: str = "demo", db: AsyncSession = Depends(get_db)):
    """Wipe all data for this user — transactions, debts, income, chat history."""
    await clear_user_data(db, user_id)
    reset_user_data(user_id)
