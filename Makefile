.PHONY: install dev test lint seed reset-db help

PYTHON := python
PIP    := pip
APP    := backend.app.main:app

help:
	@echo ""
	@echo "  make install    Install Python dependencies"
	@echo "  make dev        Start the dev server (hot-reload)"
	@echo "  make test       Run the test suite"
	@echo "  make lint       Run ruff linter + formatter check"
	@echo "  make seed       Populate demo data"
	@echo "  make reset-db   Drop and recreate the SQLite database"
	@echo ""

install:
	$(PIP) install -r requirements.txt

dev:
	uvicorn $(APP) --reload --host 0.0.0.0 --port 8000

test:
	pytest tests/ -v --tb=short

lint:
	ruff check backend/ tests/ scripts/
	ruff format --check backend/ tests/ scripts/

seed:
	$(PYTHON) scripts/seed_demo_data.py

reset-db:
	$(PYTHON) -c "from backend.app.db.database import reset_db; import asyncio; asyncio.run(reset_db())"
	@echo "Database reset complete."
