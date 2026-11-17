from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.schemas.documents import ClearDocumentsRequest, DocumentInfo, DocumentListResponse, UploadResponse
from app.services.document_service import clear_documents, delete_document, get_document, list_documents, reindex_document, save_and_ingest_files

router = APIRouter(prefix="/api/documents", tags=["documents"])


@router.post("/upload", response_model=UploadResponse)
async def upload_documents(files: list[UploadFile] = File(...), db: AsyncSession = Depends(get_db)) -> UploadResponse:
    if not files:
        raise HTTPException(status_code=400, detail="No files provided.")
    return await save_and_ingest_files(files, db)


@router.get("", response_model=DocumentListResponse)
async def get_documents(db: AsyncSession = Depends(get_db)) -> DocumentListResponse:
    return await list_documents(db)


@router.post("/clear", status_code=204)
async def clear_all(request: ClearDocumentsRequest, db: AsyncSession = Depends(get_db)) -> Response:
    if not request.confirm:
        raise HTTPException(400, "Set confirm=true to clear all documents.")
    await clear_documents(db)
    return Response(status_code=204)


@router.get("/{document_id}", response_model=DocumentInfo)
async def get_document_metadata(document_id: str, db: AsyncSession = Depends(get_db)) -> DocumentInfo:
    return await get_document(document_id, db)


@router.delete("/{document_id}", status_code=204)
async def remove_document(document_id: str, db: AsyncSession = Depends(get_db)) -> Response:
    await delete_document(document_id, db)
    return Response(status_code=204)


@router.post("/{document_id}/reindex", response_model=DocumentInfo)
async def reindex(document_id: str, db: AsyncSession = Depends(get_db)) -> DocumentInfo:
    return await reindex_document(document_id, db)
