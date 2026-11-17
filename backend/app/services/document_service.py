import hashlib
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import HTTPException, UploadFile
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.config import get_settings
from app.db.models import DocumentRecord
from app.rag.ingestion import ingest_pdf, reingest_pdf
from app.rag.vectorstore import delete_by_document_id
from app.schemas.documents import DocumentInfo, DocumentListResponse, UploadResponse, UploadResult

logger = logging.getLogger(__name__)


def _as_info(record: DocumentRecord) -> DocumentInfo:
    return DocumentInfo(document_id=record.id, filename=record.original_filename,
        chunk_count=record.chunk_count, size_bytes=record.size_bytes, status=record.status,
        uploaded_at=record.uploaded_at, ingested_at=record.ingested_at,
        error_message=record.error_message)


def _stored_path(record: DocumentRecord) -> Path:
    root = Path(get_settings().uploads_dir).resolve()
    path = (root / record.stored_filename).resolve()
    if root not in path.parents:
        raise RuntimeError("Stored document path is outside the uploads directory")
    return path


async def save_and_ingest_files(files: list[UploadFile], db: AsyncSession) -> UploadResponse:
    settings = get_settings()
    if len(files) > settings.max_files_per_upload:
        raise HTTPException(413, f"At most {settings.max_files_per_upload} files may be uploaded at once.")
    uploads_dir = Path(settings.uploads_dir)
    await run_in_threadpool(uploads_dir.mkdir, parents=True, exist_ok=True)
    results: list[UploadResult] = []

    for upload in files:
        original = Path(upload.filename or "unnamed.pdf").name
        try:
            if not upload.filename or Path(upload.filename).suffix.lower() != ".pdf":
                raise ValueError("Only .pdf files are accepted.")
            content = await upload.read(settings.max_upload_bytes + 1)
            if len(content) > settings.max_upload_bytes:
                raise ValueError(f"File exceeds the {settings.max_upload_size_mb} MB limit.")
            if not content.startswith(b"%PDF-"):
                raise ValueError("File content is not a valid PDF signature.")
            digest = hashlib.sha256(content).hexdigest()
            existing = (await db.execute(select(DocumentRecord).where(DocumentRecord.sha256 == digest))).scalar_one_or_none()
            if existing:
                results.append(UploadResult(filename=original, status="duplicate", document=_as_info(existing), error="This PDF is already indexed."))
                continue

            document_id = str(uuid.uuid4())
            stored_filename = f"{document_id}.pdf"
            path = uploads_dir / stored_filename
            await run_in_threadpool(path.write_bytes, content)
            record = DocumentRecord(id=document_id, original_filename=original,
                stored_filename=stored_filename, sha256=digest, size_bytes=len(content), status="pending")
            db.add(record)
            await db.commit()
            await db.refresh(record)
            try:
                ingested = await run_in_threadpool(ingest_pdf, path, original, document_id)
                record.chunk_count = ingested["chunk_count"]
                record.status = "complete"
                record.ingested_at = datetime.now(timezone.utc)
                await db.commit()
                await db.refresh(record)
                results.append(UploadResult(filename=original, status="complete", document=_as_info(record)))
            except Exception as exc:
                logger.warning("Document ingestion failed", extra={"document_id": document_id, "error_type": type(exc).__name__})
                try:
                    await run_in_threadpool(delete_by_document_id, document_id)
                except Exception:
                    logger.exception("Failed to clean vector chunks", extra={"document_id": document_id})
                await db.delete(record)
                await db.commit()
                if path.exists():
                    await run_in_threadpool(path.unlink)
                results.append(UploadResult(filename=original, status="failed", error=str(exc)))
        except Exception as exc:
            await db.rollback()
            logger.info("Upload rejected", extra={"filename": original, "error_type": type(exc).__name__})
            results.append(UploadResult(filename=original, status="failed", error=str(exc)))
        finally:
            await upload.close()

    successful = [r for r in results if r.status == "complete"]
    return UploadResponse(results=results,
        total_chunks=sum(r.document.chunk_count for r in successful if r.document),
        message=f"Indexed {len(successful)} of {len(results)} file(s).")


async def list_documents(db: AsyncSession) -> DocumentListResponse:
    records = (await db.execute(select(DocumentRecord).order_by(DocumentRecord.uploaded_at.desc()))).scalars().all()
    return DocumentListResponse(documents=[_as_info(record) for record in records])


async def get_document(document_id: str, db: AsyncSession) -> DocumentInfo:
    record = await db.get(DocumentRecord, document_id)
    if not record:
        raise HTTPException(404, "Document not found.")
    return _as_info(record)


async def delete_document(document_id: str, db: AsyncSession) -> None:
    record = await db.get(DocumentRecord, document_id)
    if not record:
        raise HTTPException(404, "Document not found.")
    await run_in_threadpool(delete_by_document_id, document_id)
    path = _stored_path(record)
    if path.exists():
        await run_in_threadpool(path.unlink)
    await db.delete(record)
    await db.commit()


async def reindex_document(document_id: str, db: AsyncSession) -> DocumentInfo:
    record = await db.get(DocumentRecord, document_id)
    if not record:
        raise HTTPException(404, "Document not found.")
    path = _stored_path(record)
    if not path.exists():
        raise HTTPException(409, "Stored PDF is missing; upload it again.")
    record.status = "pending"
    record.error_message = None
    await db.commit()
    try:
        result = await run_in_threadpool(reingest_pdf, path, record.id, record.original_filename)
        record.chunk_count = result["chunk_count"]
        record.status = "complete"
        record.ingested_at = datetime.now(timezone.utc)
    except Exception as exc:
        record.status = "failed"
        record.error_message = str(exc)
        await db.commit()
        raise HTTPException(422, f"Re-indexing failed: {exc}") from exc
    await db.commit()
    await db.refresh(record)
    return _as_info(record)


async def clear_documents(db: AsyncSession) -> None:
    records = (await db.execute(select(DocumentRecord))).scalars().all()
    for record in records:
        await run_in_threadpool(delete_by_document_id, record.id)
        path = _stored_path(record)
        if path.exists():
            await run_in_threadpool(path.unlink)
    await db.execute(delete(DocumentRecord))
    await db.commit()
