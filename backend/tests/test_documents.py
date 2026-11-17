import asyncio
from io import BytesIO

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from starlette.datastructures import UploadFile

from app.config import get_settings
from app.db.database import Base
from app.db.models import DocumentRecord
from app.services import document_service


async def _with_db(tmp_path, action):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'test.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as db:
        result = await action(db)
    await engine.dispose()
    return result


def _upload(name: str, content: bytes) -> UploadFile:
    return UploadFile(filename=name, file=BytesIO(content))


def test_valid_pdf_upload_and_listing(tmp_path, monkeypatch):
    settings = get_settings(); old = settings.uploads_dir; settings.uploads_dir = str(tmp_path / "uploads")
    monkeypatch.setattr(document_service, "ingest_pdf", lambda path, name, doc_id: {"chunk_count": 3})
    async def action(db):
        response = await document_service.save_and_ingest_files([_upload("paper.pdf", b"%PDF-1.4 sample")], db)
        return response, await document_service.list_documents(db)
    response, listing = asyncio.run(_with_db(tmp_path, action)); settings.uploads_dir = old
    assert response.results[0].status == "complete"
    assert response.total_chunks == 3
    assert listing.documents[0].filename == "paper.pdf"


def test_invalid_extension_and_signature(tmp_path):
    async def action(db):
        return await document_service.save_and_ingest_files([_upload("notes.txt", b"%PDF-1.4"), _upload("fake.pdf", b"not a pdf")], db)
    response = asyncio.run(_with_db(tmp_path, action))
    assert [item.status for item in response.results] == ["failed", "failed"]
    assert "Only .pdf" in response.results[0].error
    assert "signature" in response.results[1].error


def test_oversized_file(tmp_path):
    settings = get_settings(); old_size = settings.max_upload_size_mb; settings.max_upload_size_mb = 1
    async def action(db):
        return await document_service.save_and_ingest_files([_upload("large.pdf", b"%PDF-" + b"x" * (1024 * 1024))], db)
    response = asyncio.run(_with_db(tmp_path, action)); settings.max_upload_size_mb = old_size
    assert response.results[0].status == "failed"
    assert "limit" in response.results[0].error


def test_duplicate_pdf(tmp_path, monkeypatch):
    settings = get_settings(); old = settings.uploads_dir; settings.uploads_dir = str(tmp_path / "uploads")
    monkeypatch.setattr(document_service, "ingest_pdf", lambda *args: {"chunk_count": 1})
    async def action(db):
        await document_service.save_and_ingest_files([_upload("one.pdf", b"%PDF-duplicate")], db)
        return await document_service.save_and_ingest_files([_upload("two.pdf", b"%PDF-duplicate")], db)
    second = asyncio.run(_with_db(tmp_path, action)); settings.uploads_dir = old
    assert second.results[0].status == "duplicate"
    assert second.results[0].document.filename == "one.pdf"


def test_pdf_without_text_cleans_up(tmp_path, monkeypatch):
    settings = get_settings(); old = settings.uploads_dir; settings.uploads_dir = str(tmp_path / "uploads")
    monkeypatch.setattr(document_service, "ingest_pdf", lambda *args: (_ for _ in ()).throw(ValueError("no extractable text")))
    monkeypatch.setattr(document_service, "delete_by_document_id", lambda *_: None)
    async def action(db):
        response = await document_service.save_and_ingest_files([_upload("scan.pdf", b"%PDF-scan")], db)
        count = len((await db.execute(select(DocumentRecord))).scalars().all())
        return response, count
    response, count = asyncio.run(_with_db(tmp_path, action)); settings.uploads_dir = old
    assert response.results[0].status == "failed"
    assert count == 0
    assert not list((tmp_path / "uploads").glob("*.pdf"))


def test_document_deletion(tmp_path, monkeypatch):
    settings = get_settings(); old = settings.uploads_dir; settings.uploads_dir = str(tmp_path / "uploads")
    monkeypatch.setattr(document_service, "ingest_pdf", lambda *args: {"chunk_count": 1})
    monkeypatch.setattr(document_service, "delete_by_document_id", lambda *_: None)
    async def action(db):
        response = await document_service.save_and_ingest_files([_upload("paper.pdf", b"%PDF-delete")], db)
        await document_service.delete_document(response.results[0].document.document_id, db)
        return await document_service.list_documents(db)
    listing = asyncio.run(_with_db(tmp_path, action)); settings.uploads_dir = old
    assert listing.documents == []
