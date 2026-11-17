import asyncio

import httpx
from fastapi import APIRouter
from sqlalchemy import text
from starlette.concurrency import run_in_threadpool

from app.config import get_settings
from app.db.database import engine
from app.rag.vectorstore import get_vectorstore
from app.schemas.health import ComponentStatus, HealthResponse, ReadinessResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Fast process liveness; intentionally avoids all external dependencies."""
    return HealthResponse(status="ok")


async def _sqlite_status() -> ComponentStatus:
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
        return ComponentStatus(ok=True)
    except Exception as exc:
        return ComponentStatus(ok=False, detail=f"SQLite unavailable: {type(exc).__name__}")


async def _chroma_status() -> ComponentStatus:
    try:
        await run_in_threadpool(get_vectorstore)
        return ComponentStatus(ok=True)
    except Exception as exc:
        return ComponentStatus(ok=False, detail=f"Chroma unavailable: {type(exc).__name__}")


async def _ollama_status() -> tuple[ComponentStatus, list[str]]:
    settings = get_settings()
    try:
        async with httpx.AsyncClient(timeout=settings.readiness_timeout_seconds) as client:
            response = await client.get(f"{settings.ollama_base_url.rstrip('/')}/api/tags")
            response.raise_for_status()
        models = [item.get("name", "") for item in response.json().get("models", []) if item.get("name")]
        return ComponentStatus(ok=True), models
    except Exception as exc:
        return ComponentStatus(ok=False, detail=f"Ollama unavailable: {type(exc).__name__}"), []


@router.get("/ready", response_model=ReadinessResponse)
async def readiness_check() -> ReadinessResponse:
    settings = get_settings()
    try:
        sqlite, chroma, ollama_result = await asyncio.wait_for(
            asyncio.gather(_sqlite_status(), _chroma_status(), _ollama_status()),
            timeout=settings.readiness_timeout_seconds + 0.5,
        )
        ollama, models = ollama_result
    except TimeoutError:
        timeout = ComponentStatus(ok=False, detail="Readiness check timed out.")
        return ReadinessResponse(status="not_ready", sqlite=timeout, chroma=timeout,
            ollama=timeout, models=timeout, message="A dependency check exceeded its timeout.")
    installed = {name.split(":")[0] for name in models}
    required = {settings.ollama_chat_model.split(":")[0], settings.ollama_embed_model.split(":")[0]}
    missing = sorted(required - installed)
    model_status = ComponentStatus(ok=not missing and ollama.ok,
        detail=(f"Missing models: {', '.join(missing)}. Run: ollama pull <model>" if missing else None))
    ready = all(item.ok for item in (sqlite, chroma, ollama, model_status))
    return ReadinessResponse(status="ready" if ready else "not_ready", sqlite=sqlite,
        chroma=chroma, ollama=ollama, models=model_status, ollama_models=models,
        message=None if ready else "Complete the reported local setup steps.")
