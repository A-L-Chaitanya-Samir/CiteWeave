from langchain_core.documents import Document

from app.rag.chains import RAG_SYSTEM_PROMPT, docs_to_sources


def test_citation_serialization_deduplicates_document_page():
    docs = [
        Document(page_content="first", metadata={"document_id": "a", "filename": "paper.pdf", "page": 2, "relevance_score": .82}),
        Document(page_content="second", metadata={"document_id": "a", "filename": "paper.pdf", "page": 2, "relevance_score": .7}),
    ]
    sources = docs_to_sources(docs)
    assert len(sources) == 1
    assert sources[0].score == .82
    assert sources[0].model_dump()["page"] == 2


def test_prompt_marks_pdf_text_as_untrusted():
    assert "untrusted evidence" in RAG_SYSTEM_PROMPT
    assert "<evidence>" in RAG_SYSTEM_PROMPT
