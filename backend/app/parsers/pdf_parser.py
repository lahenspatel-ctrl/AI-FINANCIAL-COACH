from __future__ import annotations

from pathlib import Path

import pandas as pd
import pdfplumber

from backend.app.parsers.base import (
    clean_description,
    normalize_columns,
    parse_amount,
    parse_date,
)
from backend.app.schemas.finance import TransactionIn


def parse_pdf(path: Path) -> list[TransactionIn]:
    all_rows: list[dict] = []

    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            tables = page.extract_tables()
            for table in tables:
                if not table or len(table) < 2:
                    continue
                header = table[0]
                for row in table[1:]:
                    if len(row) == len(header):
                        all_rows.append(dict(zip(header, row)))

    if not all_rows:
        return []

    df = pd.DataFrame(all_rows, dtype=str)
    df = normalize_columns(df)

    results: list[TransactionIn] = []
    for _, row in df.iterrows():
        txn_date = parse_date(row.get("txn_date"))
        amount = parse_amount(row.get("amount"))
        if txn_date is None or amount is None:
            continue
        results.append(
            TransactionIn(
                txn_date=txn_date,
                description=clean_description(row.get("description", "")),
                amount=amount,
                account=str(row["account"]) if "account" in row and pd.notna(row.get("account")) else None,
            )
        )
    return results
