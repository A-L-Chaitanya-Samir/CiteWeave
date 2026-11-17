import json
import uuid
from datetime import datetime, timezone

from fastapi import HTTPException
from langchain_core.messages import AIMessage, HumanMessage
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.models import ChatMessage, ChatSession
from app.schemas.chat import SourceCitation
from app.schemas.sessions import MessageInfo, SessionInfo, SessionListResponse, SessionMessagesResponse


async def get_or_create_session(db: AsyncSession, session_id: str | None) -> str:
    if session_id:
        if await db.get(ChatSession, session_id):
            return session_id
        raise HTTPException(404, "Chat session not found.")
    new_session = ChatSession(id=str(uuid.uuid4()), title=None)
    db.add(new_session)
    await db.commit()
    return new_session.id


async def save_message(db: AsyncSession, session_id: str, role: str, content: str,
    sources: list[SourceCitation] | None = None, status: str = "complete") -> str:
    message = ChatMessage(session_id=session_id, role=role, content=content, status=status,
        sources_json=json.dumps([source.model_dump() for source in sources]) if sources else None)
    db.add(message)
    session = await db.get(ChatSession, session_id)
    if not session:
        raise HTTPException(404, "Chat session not found.")
    session.updated_at = datetime.now(timezone.utc)
    if not session.title and role == "user":
        session.title = content.strip()[:80]
    await db.commit()
    await db.refresh(message)
    return message.id


async def update_message(db: AsyncSession, message_id: str, *, content: str,
    status: str, sources: list[SourceCitation] | None = None) -> None:
    message = await db.get(ChatMessage, message_id)
    if not message:
        return
    message.content = content
    message.status = status
    message.sources_json = json.dumps([source.model_dump() for source in sources]) if sources else None
    session = await db.get(ChatSession, message.session_id)
    if session:
        session.updated_at = datetime.now(timezone.utc)
    await db.commit()


async def get_history_messages(db: AsyncSession, session_id: str) -> list:
    limit = get_settings().max_history_messages
    result = await db.execute(select(ChatMessage).where(ChatMessage.session_id == session_id,
        ChatMessage.status == "complete").order_by(ChatMessage.created_at.desc()).limit(limit))
    messages = list(reversed(result.scalars().all()))
    return [HumanMessage(content=item.content) if item.role == "user" else AIMessage(content=item.content)
        for item in messages if item.role in {"user", "assistant"}]


async def list_sessions(db: AsyncSession) -> SessionListResponse:
    sessions = (await db.execute(select(ChatSession).order_by(ChatSession.updated_at.desc()))).scalars().all()
    return SessionListResponse(sessions=[SessionInfo(id=item.id, title=item.title,
        created_at=item.created_at, updated_at=item.updated_at) for item in sessions])


async def get_session_messages(db: AsyncSession, session_id: str) -> SessionMessagesResponse:
    if not await db.get(ChatSession, session_id):
        raise HTTPException(404, "Chat session not found.")
    messages = (await db.execute(select(ChatMessage).where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at))).scalars().all()
    items = [MessageInfo(id=item.id, role=item.role, content=item.content,
        sources=[SourceCitation(**source) for source in json.loads(item.sources_json)] if item.sources_json else [],
        status=item.status, created_at=item.created_at) for item in messages]
    return SessionMessagesResponse(session_id=session_id, messages=items)


async def delete_session(db: AsyncSession, session_id: str) -> None:
    session = await db.get(ChatSession, session_id)
    if not session:
        raise HTTPException(404, "Chat session not found.")
    await db.delete(session)
    await db.commit()
