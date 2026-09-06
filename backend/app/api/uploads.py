"""
File upload endpoint.
Accepts CSV / XLSX / PDF / JSON, parses into DB, starts the LangGraph pipeline.
"""
from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.config import settings
from backend.app.db.database import get_db
from backend.app.db.models import AgentRun, Debt, Income, Transaction, UploadedFile
from backend.app.parsers.csv_parser import parse_csv, parse_xlsx
from backend.app.parsers.json_parser import parse_json_debts, parse_json_income
from backend.app.parsers.pdf_parser import parse_pdf
from backend.app.schemas.finance import UploadedFileOut
from backend.app.services.vector_store import upsert_transactions

router = APIRouter(prefix="/api/uploads", tags=["uploads"])

_ALLOWED = {"csv", "xlsx", "pdf", "json"}
_MAGIC = {
    b"%PDF": "pdf",
    b"PK\x03\x04": "xlsx",
}


def _detect_type(header: bytes, ext: str) -> str:
    for magic, ftype in _MAGIC.items():
        if header.startswith(magic):
            return ftype
    return ext  # fall back to extension


@router.post("", response_model=UploadedFileOut)
async def upload_file(
    file: UploadFile = File(...),
    user_id: str = "demo",
    db: AsyncSession = Depends(get_db),
):
    ext = Path(file.filename or "").suffix.lstrip(".").lower()
    if ext not in _ALLOWED:
        raise HTTPException(400, f"Unsupported file type: .{ext}. Allowed: {_ALLOWED}")

    content = await file.read()
    if len(content) > settings.max_upload_bytes:
        raise HTTPException(413, "File too large (max 25 MB)")

    file_type = _detect_type(content[:8], ext)
    stored_name = f"{uuid.uuid4()}.{file_type}"
    stored_path = Path(settings.upload_dir) / stored_name
    stored_path.write_bytes(content)

    # Persist upload record
    upload_rec = UploadedFile(
        user_id=user_id,
        original_filename=file.filename or stored_name,
        stored_filename=stored_name,
        file_type=file_type,
        status="parsing",
    )
    db.add(upload_rec)
    await db.flush()

    # Parse file
    transactions: list = []
    debts_in: list = []
    income_in: list = []

    try:
        if file_type == "csv":
            transactions = parse_csv(stored_path)
        elif file_type == "xlsx":
            transactions = parse_xlsx(stored_path)
        elif file_type == "pdf":
            transactions = parse_pdf(stored_path)
        elif file_type == "json":
            debts_in = parse_json_debts(stored_path)
            income_in = parse_json_income(stored_path)
    except Exception as exc:
        logger.error(f"Parse error: {exc}")
        upload_rec.status = "error"
        await db.commit()
        raise HTTPException(422, f"Could not parse file: {exc}")

    # Persist parsed data
    txn_records = []
    for t in transactions:
        rec = Transaction(
            user_id=user_id,
            source_file_id=upload_rec.id,
            txn_date=t.txn_date,
            description=t.description,
            amount=t.amount,
            account=t.account,
            category=t.category,
            sub_category=t.sub_category,
        )
        db.add(rec)
        txn_records.append(rec)

    for d in debts_in:
        db.add(
            Debt(
                user_id=user_id,
                name=d.name,
                balance=d.balance,
                apr=d.apr,
                minimum_payment=d.minimum_payment,
                debt_type=d.debt_type,
            )
        )

    for i in income_in:
        db.add(
            Income(
                user_id=user_id,
                source=i.source,
                monthly_amount=i.monthly_amount,
                income_type=i.income_type,
            )
        )

    upload_rec.status = "parsed"
    await db.commit()
    await db.refresh(upload_rec)

    # Index transactions in vector store (IDs are Python-generated UUIDs, always set)
    if txn_records:
        ids = [r.id for r in txn_records]
        docs = [f"{r.txn_date} | {r.description} | ${r.amount:.2f}" for r in txn_records]
        metas = [{"user_id": user_id, "amount": r.amount, "date": str(r.txn_date)} for r in txn_records]
        try:
            upsert_transactions(ids, docs, metas)
        except Exception as exc:
            logger.warning(f"Vector store upsert failed (non-fatal): {exc}")

    logger.info(
        f"Uploaded {file.filename}: {len(transactions)} txns, "
        f"{len(debts_in)} debts, {len(income_in)} income rows"
    )
    return upload_rec
