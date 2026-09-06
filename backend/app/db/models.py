from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import (
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class UploadedFile(Base):
    __tablename__ = "uploaded_files"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(64), index=True, default="demo")
    original_filename: Mapped[str] = mapped_column(String(512))
    stored_filename: Mapped[str] = mapped_column(String(512))
    file_type: Mapped[str] = mapped_column(String(16))  # csv | xlsx | pdf | json
    status: Mapped[str] = mapped_column(String(32), default="uploaded")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    transactions: Mapped[list[Transaction]] = relationship(back_populates="source_file")


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(64), index=True, default="demo")
    source_file_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("uploaded_files.id"), nullable=True
    )
    txn_date: Mapped[date] = mapped_column(Date, index=True)
    description: Mapped[str] = mapped_column(Text)
    amount: Mapped[float] = mapped_column(Float)  # negative = debit, positive = credit
    category: Mapped[str | None] = mapped_column(String(128), nullable=True)
    sub_category: Mapped[str | None] = mapped_column(String(128), nullable=True)
    account: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    source_file: Mapped[UploadedFile | None] = relationship(back_populates="transactions")


class Debt(Base):
    __tablename__ = "debts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(64), index=True, default="demo")
    name: Mapped[str] = mapped_column(String(256))
    balance: Mapped[float] = mapped_column(Float)
    apr: Mapped[float] = mapped_column(Float)  # annual percentage rate, e.g. 0.19 = 19%
    minimum_payment: Mapped[float] = mapped_column(Float)
    debt_type: Mapped[str] = mapped_column(String(64), default="other")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class Income(Base):
    __tablename__ = "income"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(64), index=True, default="demo")
    source: Mapped[str] = mapped_column(String(256))
    monthly_amount: Mapped[float] = mapped_column(Float)
    income_type: Mapped[str] = mapped_column(String(64), default="salary")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class AgentRun(Base):
    __tablename__ = "agent_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(64), index=True, default="demo")
    trigger: Mapped[str] = mapped_column(String(64), default="upload")
    status: Mapped[str] = mapped_column(String(32), default="pending")
    summary_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True, default="demo")
    role: Mapped[str] = mapped_column(String(16))  # user | assistant
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
