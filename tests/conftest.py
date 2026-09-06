import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

# Override settings BEFORE importing the app so DB is in-memory for tests
from backend.app.config import settings
settings.database_url = "sqlite+aiosqlite:///:memory:"
settings.chroma_path = "./data/chroma-test"
settings.upload_dir = "./data/uploads-test"
settings.ensure_dirs()

from backend.app.main import app
from backend.app.db.database import init_db


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def db_setup():
    await init_db()


@pytest_asyncio.fixture(loop_scope="session")
async def client(db_setup):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
