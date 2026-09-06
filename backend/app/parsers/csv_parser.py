from __future__ import annotations

from pathlib import Path

import pandas as pd

from backend.app.parsers.base import (
    clean_description,
    normalize_columns,
    parse_amount,
    parse_date,
)
from backend.app.schemas.finance import TransactionIn


def parse_csv(path: Path) -> list[TransactionIn]:
    df = pd.read_csv(path, dtype=str, on_bad_lines="skip")
    return _process_df(df)


def parse_xlsx(path: Path) -> list[TransactionIn]:
    df = pd.read_excel(path, dtype=str)
    return _process_df(df)


def _process_df(df: pd.DataFrame) -> list[TransactionIn]:
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
                category=str(row["category"]) if "category" in row and pd.notna(row.get("category")) else None,
                sub_category=str(row["sub_category"]) if "sub_category" in row and pd.notna(row.get("sub_category")) else None,
            )
        )
    return results
