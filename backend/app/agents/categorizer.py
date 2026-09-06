"""
Data Normalizer / Categorizer Agent.
Uses LLM (classifier role) to assign category + sub_category to transactions.
Batches requests to minimize LLM calls.
"""
from __future__ import annotations

import json
from typing import AsyncGenerator

from loguru import logger
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.agents.events import AgentEvent
from backend.app.db.models import Transaction
from backend.app.llm.client import chat_complete_json

_SYSTEM = """\
You are a financial transaction categorizer. Given a list of transaction descriptions,
return a JSON array where each element has:
  "index": (same integer as input),
  "category": one of [Food & Dining, Shopping, Transportation, Housing, Utilities,
    Healthcare, Entertainment, Travel, Education, Personal Care, Income,
    Transfers, Investments, Fees & Charges, Other],
  "sub_category": a short specific label (e.g. "Groceries", "Rent", "Netflix")

Return ONLY the JSON array. No explanation."""


async def run_categorizer(
    db: AsyncSession,
    user_id: str = "demo",
) -> AsyncGenerator[AgentEvent, None]:
    yield AgentEvent("categorizer", "started", "Categorizing transactions…")

    # Fetch uncategorized transactions
    result = await db.execute(
        select(Transaction).where(
            Transaction.user_id == user_id,
            Transaction.category.is_(None),
        )
    )
    txns = list(result.scalars().all())
    if not txns:
        yield AgentEvent("categorizer", "complete", "No uncategorized transactions found.")
        return

    yield AgentEvent("categorizer", "progress", f"Categorizing {len(txns)} transactions…")

    # Batch into groups of 30 to stay within context limits
    batch_size = 30
    categorized = 0

    for i in range(0, len(txns), batch_size):
        batch = txns[i : i + batch_size]
        payload = [
            {"index": j, "description": t.description, "amount": t.amount}
            for j, t in enumerate(batch)
        ]
        messages = [
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": json.dumps(payload)},
        ]
        try:
            raw = await chat_complete_json("classifier", messages, max_tokens=512)
            # raw may be {"results": [...]} or directly a list
            items = raw if isinstance(raw, list) else raw.get("results", raw.get("categories", []))
            for item in items:
                idx = item.get("index", 0)
                if 0 <= idx < len(batch):
                    txn = batch[idx]
                    await db.execute(
                        update(Transaction)
                        .where(Transaction.id == txn.id)
                        .values(
                            category=item.get("category", "Other"),
                            sub_category=item.get("sub_category"),
                        )
                    )
                    categorized += 1
        except Exception as exc:
            logger.warning(f"Categorizer batch failed: {exc}")

        await db.commit()
        yield AgentEvent(
            "categorizer",
            "progress",
            f"Categorized {min(i + batch_size, len(txns))}/{len(txns)} transactions",
        )

    yield AgentEvent(
        "categorizer",
        "complete",
        f"Done. {categorized} transactions categorized.",
        data={"categorized": categorized},
    )
