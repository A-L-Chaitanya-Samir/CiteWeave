import asyncio

from app.api.routes import health
from app.schemas.health import ComponentStatus


def test_health_endpoint_is_dependency_free(monkeypatch):
    monkeypatch.setattr(health, "get_vectorstore", lambda: (_ for _ in ()).throw(AssertionError("Chroma touched")))
    response = asyncio.run(health.health_check())
    assert response.status == "ok"
    assert response.service == "CiteWeave API"


def test_readiness_reports_mocked_dependencies(monkeypatch):
    async def ok(): return ComponentStatus(ok=True)
    async def ollama(): return ComponentStatus(ok=True), ["llama3.2:latest", "nomic-embed-text:latest"]
    monkeypatch.setattr(health, "_sqlite_status", ok)
    monkeypatch.setattr(health, "_chroma_status", ok)
    monkeypatch.setattr(health, "_ollama_status", ollama)
    response = asyncio.run(health.readiness_check())
    assert response.status == "ready"
    assert response.models.ok is True


def test_readiness_reports_missing_models(monkeypatch):
    async def ok(): return ComponentStatus(ok=True)
    async def ollama(): return ComponentStatus(ok=True), []
    monkeypatch.setattr(health, "_sqlite_status", ok)
    monkeypatch.setattr(health, "_chroma_status", ok)
    monkeypatch.setattr(health, "_ollama_status", ollama)
    response = asyncio.run(health.readiness_check())
    assert response.status == "not_ready"
    assert "Missing models" in (response.models.detail or "")
