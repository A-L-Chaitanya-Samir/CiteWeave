import asyncio
import json
import logging
from collections.abc import AsyncGenerator

from fastapi import HTTPException
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.rag.chains import RAG_SYSTEM_PROMPT, _format_docs, docs_to_sources
from app.rag.llm import get_chat_llm
from app.rag.vectorstore import retrieve_documents
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.session_service import get_history_messages, get_or_create_session, save_message, update_message

logger = logging.getLogger(__name__)
INSUFFICIENT = "The uploaded documents do not contain enough information to answer that."


def _event(name: str, data: object) -> str:
    return f"event: {name}\ndata: {json.dumps(data)}\n\n"


def _rewrite(question: str, history: list) -> str:
    words = question.lower().split()
    if len(words) < 12 and any(word in words for word in {"it", "they", "this", "that", "these", "those"}):
        previous = next((item.content for item in reversed(history) if isinstance(item, HumanMessage)), "")
        if previous:
            return f"Previous question: {previous}\nFollow-up question: {question}"
    return question


async def _rewrite_query(question: str, history: list) -> str:
    fallback = _rewrite(question, history)
    if fallback == question:
        return question
    try:
        model = get_chat_llm(streaming=False)
        prompt = [SystemMessage(content="Rewrite the follow-up as one standalone retrieval query. Return only the query."),
            *history[-4:], HumanMessage(content=question)]
        response = await run_in_threadpool(model.invoke, prompt)
        rewritten = str(response.content if isinstance(response, AIMessage) else response).strip()
        return rewritten or fallback
    except Exception:
        logger.info("Using deterministic query rewrite fallback")
        return fallback


def _messages(question: str, history: list, context: str) -> list:
    return [SystemMessage(content=RAG_SYSTEM_PROMPT.format(context=context)), *history, HumanMessage(content=question)]


async def chat(request: ChatRequest, db: AsyncSession) -> ChatResponse:
    session_id = await get_or_create_session(db, request.session_id)
    history = await get_history_messages(db, session_id)
    await save_message(db, session_id, "user", request.question)
    assistant_id = await save_message(db, session_id, "assistant", "", status="pending")
    try:
        query = await _rewrite_query(request.question, history)
        docs = await run_in_threadpool(retrieve_documents, query, request.document_ids)
        sources = docs_to_sources(docs)
        if not docs:
            answer = INSUFFICIENT
        else:
            llm = get_chat_llm(streaming=False)
            response = await run_in_threadpool(llm.invoke, _messages(request.question, history, _format_docs(docs)))
            answer = response.content if isinstance(response, AIMessage) else str(response)
        await update_message(db, assistant_id, content=answer, status="complete", sources=sources)
        return ChatResponse(answer=answer, sources=sources, session_id=session_id)
    except Exception as exc:
        logger.exception("Chat generation failed", extra={"session_id": session_id})
        await update_message(db, assistant_id, content="Generation failed. You can retry this question.", status="failed")
        if isinstance(exc, HTTPException):
            raise
        raise HTTPException(503, "Local generation failed. Check Ollama and the required models.") from exc


async def chat_stream(request: ChatRequest, db: AsyncSession) -> AsyncGenerator[str, None]:
    session_id: str | None = None
    assistant_id: str | None = None
    full_answer = ""
    try:
        session_id = await get_or_create_session(db, request.session_id)
        history = await get_history_messages(db, session_id)
        await save_message(db, session_id, "user", request.question)
        assistant_id = await save_message(db, session_id, "assistant", "", status="pending")
        yield _event("session", {"session_id": session_id})
        query = await _rewrite_query(request.question, history)
        docs = await run_in_threadpool(retrieve_documents, query, request.document_ids)
        sources = docs_to_sources(docs)
        yield _event("sources", [source.model_dump() for source in sources])
        if not docs:
            full_answer = INSUFFICIENT
            yield _event("token", full_answer)
        else:
            llm = get_chat_llm(streaming=True)
            async for chunk in llm.astream(_messages(request.question, history, _format_docs(docs))):
                token = chunk.content if hasattr(chunk, "content") else str(chunk)
                if token:
                    full_answer += token
                    yield _event("token", token)
        await update_message(db, assistant_id, content=full_answer, status="complete", sources=sources)
        yield _event("done", {"session_id": session_id})
    except asyncio.CancelledError:
        if assistant_id:
            await update_message(db, assistant_id, content=full_answer, status="failed")
        raise
    except Exception as exc:
        logger.exception("Streaming chat failed", extra={"session_id": session_id})
        message = str(exc.detail) if isinstance(exc, HTTPException) else "Generation failed. Check Ollama and retry."
        if assistant_id:
            await update_message(db, assistant_id, content=message, status="failed")
        yield _event("error", {"message": message, "code": type(exc).__name__})
