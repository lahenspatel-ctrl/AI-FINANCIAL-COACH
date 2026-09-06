"""Unit tests for file parsers."""
import io
import tempfile
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from backend.app.parsers.csv_parser import parse_csv, parse_xlsx
from backend.app.parsers.base import parse_date, parse_amount, normalize_columns


# ── parse_date ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("raw,expected", [
    ("2024-01-15", date(2024, 1, 15)),
    ("01/15/2024", date(2024, 1, 15)),
    ("15/01/2024", date(2024, 1, 15)),
    ("Jan 15, 2024", date(2024, 1, 15)),
])
def test_parse_date_formats(raw, expected):
    assert parse_date(raw) == expected


def test_parse_date_none_on_garbage():
    assert parse_date("not-a-date") is None


# ── parse_amount ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize("raw,expected", [
    ("$1,234.56", 1234.56),
    ("-45.00",    -45.00),
    ("(100.00)",  -100.00),
    ("€200",       200.0),
    (99.9,          99.9),
])
def test_parse_amount(raw, expected):
    assert parse_amount(raw) == pytest.approx(expected)


# ── CSV parser ────────────────────────────────────────────────────────────────

def _make_csv(content: str) -> Path:
    p = Path(tempfile.mktemp(suffix=".csv"))
    p.write_text(content)
    return p


def test_parse_csv_basic():
    csv = _make_csv(
        "Date,Description,Amount\n"
        "2024-03-01,Walmart,-85.32\n"
        "2024-03-02,Salary,3000.00\n"
    )
    txns = parse_csv(csv)
    csv.unlink()
    assert len(txns) == 2
    assert txns[0].amount == pytest.approx(-85.32)
    assert txns[1].amount == pytest.approx(3000.0)


def test_parse_csv_debit_credit_columns():
    csv = _make_csv(
        "Date,Description,Debit,Credit\n"
        "2024-03-01,Rent,1200,\n"
        "2024-03-15,Paycheck,,4000\n"
    )
    txns = parse_csv(csv)
    csv.unlink()
    assert len(txns) == 2
    rent = next(t for t in txns if "Rent" in t.description)
    pay  = next(t for t in txns if "Paycheck" in t.description)
    assert rent.amount == pytest.approx(-1200)
    assert pay.amount  == pytest.approx(4000)


def test_parse_csv_skips_bad_rows():
    csv = _make_csv(
        "Date,Description,Amount\n"
        "not-a-date,Bad,100\n"
        "2024-01-01,Good,-50\n"
    )
    txns = parse_csv(csv)
    csv.unlink()
    assert len(txns) == 1
    assert txns[0].description == "Good"


# ── normalize_columns ─────────────────────────────────────────────────────────

def test_normalize_column_aliases():
    df = pd.DataFrame({"Transaction Date": ["2024-01-01"], "Memo": ["Starbucks"], "Amount": ["-5.50"]})
    normed = normalize_columns(df)
    assert "txn_date" in normed.columns
    assert "description" in normed.columns
