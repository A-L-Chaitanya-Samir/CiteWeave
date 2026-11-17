from pathlib import Path

from chromadb.config import Settings as ChromaSettings
from langchain_chroma import Chroma
from langchain_core.documents import Document

from app.config import get_settings
from app.rag.embeddings import get_embeddings

_vectorstore: Chroma | None = None


def get_vectorstore() -> Chroma:
    global _vectorstore
    if _vectorstore is None:
        settings = get_settings()
        persist_dir = Path(settings.chroma_persist_dir)
        persist_dir.mkdir(parents=True, exist_ok=True)
        _vectorstore = Chroma(
            collection_name=settings.chroma_collection_name,
            embedding_function=get_embeddings(),
            persist_directory=str(persist_dir),
            client_settings=ChromaSettings(anonymized_telemetry=False),
        )
    return _vectorstore


def add_documents(chunks: list[Document]) -> None:
    store = get_vectorstore()
    store.add_documents(chunks)


def delete_by_document_id(document_id: str) -> None:
    store = get_vectorstore()
    result = store.get(where={"document_id": document_id}, include=[])
    ids = result.get("ids") or []
    if ids:
        store.delete(ids=ids)


def retrieve_documents(query: str, document_ids: list[str] | None = None) -> list[Document]:
    settings = get_settings()
    store = get_vectorstore()
    search_kwargs: dict = {"k": settings.retrieval_top_k}
    if document_ids:
        search_kwargs["filter"] = {"document_id": {"$in": document_ids}}
    results = store.similarity_search_with_relevance_scores(query, **search_kwargs)
    docs: list[Document] = []
    for doc, score in results:
        if score >= settings.minimum_relevance_score:
            doc.metadata["relevance_score"] = max(0.0, min(1.0, float(score)))
            docs.append(doc)
    return docs
