from datetime import datetime
from pydantic import BaseModel


class DocumentInfo(BaseModel):
    document_id: str
    filename: str
    chunk_count: int
    size_bytes: int
    status: str
    uploaded_at: datetime
    ingested_at: datetime | None = None
    error_message: str | None = None


class UploadResult(BaseModel):
    filename: str
    status: str
    document: DocumentInfo | None = None
    error: str | None = None


class UploadResponse(BaseModel):
    results: list[UploadResult]
    total_chunks: int
    message: str


class DocumentListResponse(BaseModel):
    documents: list[DocumentInfo]


class ClearDocumentsRequest(BaseModel):
    confirm: bool
