"""
Shared normalization utilities for all parsers.
"""
from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any

import pandas as pd


_DATE_FMTS = [
    "%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y",
    "%m-%d-%Y", "%d-%m-%Y", "%Y/%m/%d",
    "%b %d, %Y", "%d %b %Y", "%B %d, %Y",
    "%m/%d/%y", "%d/%m/%y",
]


def parse_date(value: Any) -> date | None:
    if isinstance(value, (date, datetime)):
        return value.date() if isinstance(value, datetime) else value
    if pd.isna(value):
        return None
    s = str(value).strip()
    for fmt in _DATE_FMTS:
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def parse_amount(value: Any) -> float | None:
    if pd.isna(value):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip()
    s = re.sub(r"[£€$,\s]", "", s)
    s = re.sub(r"\((.+)\)", r"-\1", s)  # (123.45) -> -123.45
    try:
        return float(s)
    except ValueError:
        return None


def clean_description(value: Any) -> str:
    if pd.isna(value):
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


# Column aliases — map common bank-export headers to canonical names
_COL_ALIASES: dict[str, str] = {
    # date
    "date": "txn_date", "transaction date": "txn_date", "trans date": "txn_date",
    "posted date": "txn_date", "value date": "txn_date",
    # description
    "description": "description", "memo": "description", "narrative": "description",
    "details": "description", "payee": "description", "merchant": "description",
    "transaction description": "description",
    # amount
    "amount": "amount", "debit": "debit", "credit": "credit",
    "transaction amount": "amount", "withdrawal": "debit", "deposit": "credit",
    "withdrawals": "debit", "deposits": "credit",
    # account
    "account": "account", "account name": "account", "account number": "account",
    # category (preserve pre-labeled data)
    "category": "category", "type": "category",
    "sub category": "sub_category", "subcategory": "sub_category", "sub_category": "sub_category",
}


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    df.columns = [c.strip().lower() for c in df.columns]
    df = df.rename(columns={k: v for k, v in _COL_ALIASES.items() if k in df.columns})

    # Merge debit/credit columns into signed amount
    if "debit" in df.columns or "credit" in df.columns:
        df["debit"] = df.get("debit", pd.Series(0, index=df.index)).fillna(0).apply(
            lambda x: abs(parse_amount(x) or 0)
        )
        df["credit"] = df.get("credit", pd.Series(0, index=df.index)).fillna(0).apply(
            lambda x: abs(parse_amount(x) or 0)
        )
        df["amount"] = df["credit"] - df["debit"]
        df = df.drop(columns=["debit", "credit"], errors="ignore")

    return df
