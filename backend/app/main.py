from contextlib import asynccontextmanager
from pathlib import Path
import logging
import json
from datetime import datetime, timezone

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import chat, documents, health, sessions
from app.config import get_settings
from app.db.database import init_db

logger = logging.getLogger(__name__)


class JsonLogFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "event": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = record.exc_info[0].__name__
        return json.dumps(payload, ensure_ascii=False)


_handler = logging.StreamHandler()
_handler.setFormatter(JsonLogFormatter())
logging.basicConfig(level=logging.INFO, handlers=[_handler])


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    Path(settings.uploads_dir).mkdir(parents=True, exist_ok=True)
    Path(settings.chroma_persist_dir).mkdir(parents=True, exist_ok=True)
    db_path = settings.database_url.replace("sqlite+aiosqlite:///", "")
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    await init_db()
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        description="A local-first multi-PDF research assistant with page-level citations.",
        version="1.0.0",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(health.router)
    app.include_router(documents.router)
    app.include_router(chat.router)
    app.include_router(sessions.router)

    @app.exception_handler(Exception)
    async def unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled request error", extra={"path": request.url.path, "method": request.method})
        return JSONResponse(status_code=500, content={"detail": "An unexpected local server error occurred."})

    return app


app = create_app()
