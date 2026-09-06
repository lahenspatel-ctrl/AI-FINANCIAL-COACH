"""
Generates realistic demo CSV/JSON files and seeds them into the database.
Usage: python scripts/seed_demo_data.py
"""
from __future__ import annotations

import asyncio
import json
import random
import sys
from datetime import date, timedelta
from pathlib import Path

# Make sure backend package is importable
sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd

from backend.app.config import settings

settings.ensure_dirs()


# ── Realistic transaction generator ──────────────────────────────────────────

MERCHANTS = [
    ("Walmart Grocery",     "Food & Dining",    "Groceries",    -180),
    ("Whole Foods Market",  "Food & Dining",    "Groceries",    -95),
    ("Chipotle",            "Food & Dining",    "Restaurants",  -14),
    ("Starbucks",           "Food & Dining",    "Coffee",       -6),
    ("Spotify",             "Entertainment",    "Streaming",    -10),
    ("Netflix",             "Entertainment",    "Streaming",    -16),
    ("Amazon",              "Shopping",         "Online",       -55),
    ("Target",              "Shopping",         "General",      -70),
    ("Shell Gas Station",   "Transportation",   "Gas",          -52),
    ("Uber",                "Transportation",   "Rideshare",    -18),
    ("Rent",                "Housing",          "Rent",         -1450),
    ("Electric Company",    "Utilities",        "Electricity",  -85),
    ("Internet Provider",   "Utilities",        "Internet",     -65),
    ("Planet Fitness",      "Healthcare",       "Gym",          -25),
    ("CVS Pharmacy",        "Healthcare",       "Pharmacy",     -22),
    ("SALARY DEPOSIT",      "Income",           "Salary",       +4500),
    ("Freelance Payment",   "Income",           "Freelance",    +800),
    ("ATM Withdrawal",      "Other",            "Cash",         -60),
    ("Bank Fee",            "Fees & Charges",   "Monthly Fee",  -12),
]


def gen_transactions(months: int = 3) -> pd.DataFrame:
    rows = []
    today = date.today()
    start = today - timedelta(days=months * 30)

    for offset in range(months * 30):
        d = start + timedelta(days=offset)
        # Each day has 0-5 transactions
        n_txns = random.choices([0, 1, 2, 3], weights=[3, 5, 4, 1])[0]
        for _ in range(n_txns):
            m_name, cat, sub, base_amt = random.choice(MERCHANTS)
            # Skip income to only 1x/month
            if cat == "Income" and d.day != 15:
                continue
            jitter = random.uniform(0.85, 1.15)
            amount = round(base_amt * jitter, 2)
            rows.append({
                "Date": d.strftime("%Y-%m-%d"),
                "Description": m_name,
                "Amount": amount,
                "Category": cat,
            })

    return pd.DataFrame(rows)


def gen_debts() -> list[dict]:
    return [
        {"name": "Chase Visa", "balance": 4800, "apr": 0.22, "minimum_payment": 96, "debt_type": "credit_card"},
        {"name": "Student Loan", "balance": 18500, "apr": 0.065, "minimum_payment": 210, "debt_type": "student_loan"},
        {"name": "Car Loan", "balance": 9200, "apr": 0.079, "minimum_payment": 285, "debt_type": "auto_loan"},
    ]


def gen_income() -> list[dict]:
    return [
        {"source": "Primary Job", "monthly_amount": 4500, "income_type": "salary"},
        {"source": "Freelance", "monthly_amount": 600, "income_type": "freelance"},
    ]


# ── Write demo files ──────────────────────────────────────────────────────────

async def seed():
    demo_dir = Path("data/demo")
    demo_dir.mkdir(parents=True, exist_ok=True)

    # Bank CSV
    txns = gen_transactions(months=3)
    csv_path = demo_dir / "bank_statement.csv"
    txns.to_csv(csv_path, index=False)
    print(f"[OK] Wrote {len(txns)} transactions -> {csv_path}")

    # Debts JSON
    debts = gen_debts()
    debt_path = demo_dir / "debts.json"
    debt_path.write_text(json.dumps(debts, indent=2))
    print(f"[OK] Wrote {len(debts)} debts -> {debt_path}")

    # Income JSON
    income = gen_income()
    income_path = demo_dir / "income.json"
    income_path.write_text(json.dumps(income, indent=2))
    print(f"[OK] Wrote {len(income)} income sources -> {income_path}")

    # Now seed via the API parsers directly into the DB
    from backend.app.db.database import init_db, SessionLocal
    from backend.app.db.models import Debt, Income, Transaction
    from backend.app.parsers.csv_parser import parse_csv
    from backend.app.parsers.json_parser import parse_json_debts, parse_json_income
    from backend.app.services.vector_store import upsert_transactions

    await init_db()

    async with SessionLocal() as db:
        from sqlalchemy import delete

        # Clear existing demo data
        for model in [Transaction, Debt, Income]:
            await db.execute(delete(model).where(model.user_id == "demo"))
        await db.commit()

        # Seed transactions
        parsed_txns = parse_csv(csv_path)
        txn_records = []
        for t in parsed_txns:
            rec = Transaction(
                user_id="demo",
                txn_date=t.txn_date,
                description=t.description,
                amount=t.amount,
                category=t.category,
            )
            db.add(rec)
            txn_records.append(rec)
        await db.commit()

        # Refresh to get IDs
        for r in txn_records:
            await db.refresh(r)

        # Index in vector store
        if txn_records:
            ids  = [r.id for r in txn_records]
            docs = [f"{r.txn_date} | {r.description} | ${r.amount:.2f}" for r in txn_records]
            metas = [{"user_id": "demo", "amount": r.amount, "date": str(r.txn_date)} for r in txn_records]
            upsert_transactions(ids, docs, metas)

        print(f"[OK] Seeded {len(txn_records)} transactions into DB")

        # Seed debts
        parsed_debts = parse_json_debts(debt_path)
        for d in parsed_debts:
            db.add(Debt(user_id="demo", **d.model_dump()))
        await db.commit()
        print(f"[OK] Seeded {len(parsed_debts)} debts into DB")

        # Seed income
        parsed_income = parse_json_income(income_path)
        for i in parsed_income:
            db.add(Income(user_id="demo", **i.model_dump()))
        await db.commit()
        print(f"[OK] Seeded {len(parsed_income)} income sources into DB")

    print("\nDemo data ready. Open http://localhost:8000")


if __name__ == "__main__":
    asyncio.run(seed())
