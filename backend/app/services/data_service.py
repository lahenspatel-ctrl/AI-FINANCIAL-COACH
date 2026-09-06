"""
Data access layer — wraps SQLAlchemy queries for financial data.
All aggregations use pandas for clarity; raw SQL via SQLAlchemy for retrieval.
"""
from __future__ import annotations

from datetime import date

import pandas as pd
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.models import ChatMessage, Debt, Income, Transaction


async def get_transactions_df(
    db: AsyncSession,
    user_id: str = "demo",
    start_date: date | None = None,
    end_date: date | None = None,
) -> pd.DataFrame:
    stmt = select(Transaction).where(Transaction.user_id == user_id)
    if start_date:
        stmt = stmt.where(Transaction.txn_date >= start_date)
    if end_date:
        stmt = stmt.where(Transaction.txn_date <= end_date)
    result = await db.execute(stmt)
    rows = result.scalars().all()
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(
        [
            {
                "id": r.id,
                "txn_date": r.txn_date,
                "description": r.description,
                "amount": r.amount,
                "category": r.category,
                "sub_category": r.sub_category,
                "account": r.account,
            }
            for r in rows
        ]
    )


async def get_debts(db: AsyncSession, user_id: str = "demo") -> list[Debt]:
    result = await db.execute(select(Debt).where(Debt.user_id == user_id))
    return list(result.scalars().all())


async def get_income(db: AsyncSession, user_id: str = "demo") -> list[Income]:
    result = await db.execute(select(Income).where(Income.user_id == user_id))
    return list(result.scalars().all())


async def get_recent_chat(
    db: AsyncSession,
    user_id: str = "demo",
    limit: int = 20,
) -> list[ChatMessage]:
    result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.user_id == user_id)
        .order_by(ChatMessage.id.desc())
        .limit(limit)
    )
    msgs = list(result.scalars().all())
    return list(reversed(msgs))


async def clear_user_data(db: AsyncSession, user_id: str = "demo") -> None:
    for model in [Transaction, Debt, Income, ChatMessage]:
        await db.execute(delete(model).where(model.user_id == user_id))
    await db.commit()
