"""API integration tests — LLM calls are mocked."""
import io
import json
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio


@pytest.mark.asyncio
async def test_health(client):
    res = await client.get("/api/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_dashboard_summary_empty(client):
    res = await client.get("/api/dashboard/summary?user_id=test_empty")
    assert res.status_code == 200
    data = res.json()
    assert "total_income" in data
    assert "total_debt" in data


@pytest.mark.asyncio
async def test_add_debt(client):
    payload = {
        "name": "Test Card",
        "balance": 1000.0,
        "apr": 0.19,
        "minimum_payment": 25.0,
        "debt_type": "credit_card",
    }
    res = await client.post("/api/dashboard/debts?user_id=test_debt", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["name"] == "Test Card"
    assert data["balance"] == 1000.0


@pytest.mark.asyncio
async def test_add_income(client):
    payload = {"source": "Salary", "monthly_amount": 5000.0, "income_type": "salary"}
    res = await client.post("/api/dashboard/income?user_id=test_income", json=payload)
    assert res.status_code == 200
    assert res.json()["monthly_amount"] == 5000.0


@pytest.mark.asyncio
async def test_upload_csv(client, tmp_path):
    csv_content = (
        "Date,Description,Amount\n"
        "2024-01-10,Groceries,-120.00\n"
        "2024-01-15,Salary,3500.00\n"
    )
    res = await client.post(
        "/api/uploads?user_id=test_upload",
        files={"file": ("bank.csv", csv_content.encode(), "text/csv")},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["file_type"] == "csv"
    assert data["status"] == "parsed"


@pytest.mark.asyncio
async def test_upload_invalid_type(client):
    res = await client.post(
        "/api/uploads?user_id=test_upload",
        files={"file": ("file.exe", b"MZ...", "application/octet-stream")},
    )
    assert res.status_code == 400


@pytest.mark.asyncio
async def test_pipeline_trigger(client):
    res = await client.post("/api/pipeline/run?user_id=test_pipe")
    assert res.status_code == 202
    data = res.json()
    assert "id" in data
    assert data["status"] == "pending"


@pytest.mark.asyncio
async def test_chat_history_empty(client):
    res = await client.get("/api/chat/history?user_id=test_chat_empty")
    assert res.status_code == 200
    assert isinstance(res.json(), list)


@pytest.mark.asyncio
async def test_delete_debt(client):
    # Create then delete
    payload = {"name": "Delete Me", "balance": 500.0, "apr": 0.15, "minimum_payment": 15.0}
    create = await client.post("/api/dashboard/debts?user_id=test_del_debt", json=payload)
    assert create.status_code == 200
    debt_id = create.json()["id"]

    res = await client.delete(f"/api/dashboard/debts/{debt_id}?user_id=test_del_debt")
    assert res.status_code == 204

    # Confirm gone
    list_res = await client.get("/api/dashboard/debts?user_id=test_del_debt")
    ids = [d["id"] for d in list_res.json()]
    assert debt_id not in ids


@pytest.mark.asyncio
async def test_delete_income(client):
    payload = {"source": "Side Job", "monthly_amount": 300.0}
    create = await client.post("/api/dashboard/income?user_id=test_del_inc", json=payload)
    assert create.status_code == 200
    inc_id = create.json()["id"]

    res = await client.delete(f"/api/dashboard/income/{inc_id}?user_id=test_del_inc")
    assert res.status_code == 204

    list_res = await client.get("/api/dashboard/income?user_id=test_del_inc")
    ids = [i["id"] for i in list_res.json()]
    assert inc_id not in ids


@pytest.mark.asyncio
async def test_reset_data(client):
    # Seed data then reset
    await client.post("/api/dashboard/debts?user_id=test_reset",
                      json={"name": "X", "balance": 100.0, "apr": 0.1, "minimum_payment": 10.0})
    res = await client.post("/api/dashboard/reset?user_id=test_reset")
    assert res.status_code == 204

    debts = await client.get("/api/dashboard/debts?user_id=test_reset")
    assert debts.json() == []


@pytest.mark.asyncio
async def test_upload_csv_preserves_category(client):
    csv_content = (
        "Date,Description,Amount,Category,Sub Category\n"
        "2024-02-01,Netflix,-15.99,Entertainment,Streaming\n"
        "2024-02-15,Salary,4000.00,Income,Salary\n"
    )
    res = await client.post(
        "/api/uploads?user_id=test_cat",
        files={"file": ("labeled.csv", csv_content.encode(), "text/csv")},
    )
    assert res.status_code == 200

    txns = await client.get("/api/dashboard/transactions?user_id=test_cat")
    assert txns.status_code == 200
    rows = txns.json()
    # Both rows should have category set from the CSV
    cats = {r["category"] for r in rows if r["category"]}
    assert "Entertainment" in cats
    assert "Income" in cats
