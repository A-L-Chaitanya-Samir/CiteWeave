from langchain_core.documents import Document

from app.rag import vectorstore


def test_document_filter_is_applied_during_retrieval(monkeypatch):
    captured = {}
    class Store:
        def similarity_search_with_relevance_scores(self, query, **kwargs):
            captured.update(kwargs)
            return [(Document(page_content="match", metadata={}), .9)]
    monkeypatch.setattr(vectorstore, "get_vectorstore", lambda: Store())
    docs = vectorstore.retrieve_documents("query", ["doc-a", "doc-b"])
    assert captured["filter"] == {"document_id": {"$in": ["doc-a", "doc-b"]}}
    assert docs[0].metadata["relevance_score"] == .9
