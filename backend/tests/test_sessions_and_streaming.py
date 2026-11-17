import asyncio

import pytest
from fastapi import HTTPException
from langchain_core.documents import Document
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.database import Base
from app.services import chat_service
from app.services import document_service
from app.config import get_settings
from app.services.session_service import get_or_create_session, get_session_messages, list_sessions, save_message
from app.schemas.chat import ChatRequest


async def _database(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'sessions.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    return engine, async_sessionmaker(engine, expire_on_commit=False)


def test_unknown_session_id_returns_404(tmp_path):
    async def run():
        engine, factory = await _database(tmp_path)
        async with factory() as db:
            with pytest.raises(HTTPException) as raised:
                await get_or_create_session(db, "missing")
        await engine.dispose()
        return raised.value.status_code
    assert asyncio.run(run()) == 404


def test_session_creation_title_and_persistence(tmp_path):
    async def create():
        engine, factory = await _database(tmp_path)
        async with factory() as db:
            session_id = await get_or_create_session(db, None)
            await save_message(db, session_id, "user", "What is the central finding?")
        await engine.dispose()
        return session_id
    session_id = asyncio.run(create())

    async def reopen():
        engine, factory = await _database(tmp_path)
        async with factory() as db:
            sessions = await list_sessions(db)
            messages = await get_session_messages(db, session_id)
        await engine.dispose()
        return sessions, messages
    sessions, messages = asyncio.run(reopen())
    assert sessions.sessions[0].title == "What is the central finding?"
    assert messages.messages[0].content.startswith("What")


def test_stream_emits_session_sources_token_and_done(tmp_path, monkeypatch):
    monkeypatch.setattr(chat_service, "retrieve_documents", lambda *_: [])
    async def run():
        engine, factory = await _database(tmp_path)
        async with factory() as db:
            events = [event async for event in chat_service.chat_stream(ChatRequest(question="Answer me"), db)]
        await engine.dispose()
        return "".join(events)
    stream = asyncio.run(run())
    assert "event: session" in stream
    assert "event: sources" in stream
    assert "event: token" in stream
    assert "event: done" in stream


def test_stream_emits_terminal_error_for_failed_ollama(tmp_path, monkeypatch):
    monkeypatch.setattr(chat_service, "retrieve_documents", lambda *_: [Document(page_content="evidence", metadata={"document_id": "1", "filename": "a.pdf", "page": 1})])
    class BrokenModel:
        async def astream(self, messages):
            if False:
                yield None
            raise ConnectionError("Ollama is down")
    monkeypatch.setattr(chat_service, "get_chat_llm", lambda **_: BrokenModel())
    async def run():
        engine, factory = await _database(tmp_path)
        async with factory() as db:
            events = [event async for event in chat_service.chat_stream(ChatRequest(question="Answer me"), db)]
        await engine.dispose()
        return "".join(events)
    stream = asyncio.run(run())
    assert "event: error" in stream
    assert "event: done" not in stream
    assert "Check Ollama" in stream


def test_mocked_upload_to_cited_stream(tmp_path, monkeypatch):
    from io import BytesIO
    from starlette.datastructures import UploadFile
    settings = get_settings(); old = settings.uploads_dir; settings.uploads_dir = str(tmp_path / "uploads")
    monkeypatch.setattr(document_service, "ingest_pdf", lambda *args: {"chunk_count": 1})
    doc = Document(page_content="Grounded evidence", metadata={"document_id": "pending", "filename": "study.pdf", "page": 4, "relevance_score": .88})
    monkeypatch.setattr(chat_service, "retrieve_documents", lambda *_: [doc])
    class Model:
        async def astream(self, messages):
            class Chunk: content = "Cited answer"
            yield Chunk()
    monkeypatch.setattr(chat_service, "get_chat_llm", lambda **_: Model())
    async def run():
        engine, factory = await _database(tmp_path)
        async with factory() as db:
            upload = await document_service.save_and_ingest_files([UploadFile(filename="study.pdf", file=BytesIO(b"%PDF-study"))], db)
            doc.metadata["document_id"] = upload.results[0].document.document_id
            events = [event async for event in chat_service.chat_stream(ChatRequest(question="What is supported?", document_ids=[doc.metadata["document_id"]]), db)]
        await engine.dispose()
        return "".join(events)
    stream = asyncio.run(run()); settings.uploads_dir = old
    assert "Cited answer" in stream
    assert '"page": 4' in stream
    assert "event: done" in stream
