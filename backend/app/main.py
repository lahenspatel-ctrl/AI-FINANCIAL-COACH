"""
FastAPI application entry point.
"""
from __future__ import annotations

import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from loguru import logger

from backend.app.config import settings
from backend.app.db.database import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Configure logging
    logger.remove()
    logger.add(sys.stderr, level=settings.log_level)

    # Ensure data directories exist
    settings.ensure_dirs()

    # Initialize database
    await init_db()
    logger.info("Database initialized.")

    if not settings.openrouter_api_key:
        logger.warning("OPENROUTER_API_KEY not set — LLM calls will fail.")
    if not settings.tavily_api_key:
        logger.warning("TAVILY_API_KEY not set — web_search tool will be disabled.")

    yield
    logger.info("Shutting down.")


app = FastAPI(
    title="AI Financial Coach Agent",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# API routers
from backend.app.api.uploads import router as uploads_router
from backend.app.api.pipeline import router as pipeline_router
from backend.app.api.chat import router as chat_router
from backend.app.api.dashboard import router as dashboard_router
from backend.app.api.settings import router as settings_router

app.include_router(uploads_router)
app.include_router(pipeline_router)
app.include_router(chat_router)
app.include_router(dashboard_router)
app.include_router(settings_router)


@app.get("/api/health")
async def health():
    return {"status": "ok", "version": "0.1.0"}


# Serve frontend from /frontend directory
_frontend = Path(__file__).parent.parent.parent / "frontend"
if _frontend.exists():
    app.mount("/", StaticFiles(directory=str(_frontend), html=True), name="frontend")
