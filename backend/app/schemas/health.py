from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str
    service: str = "CiteWeave API"


class ComponentStatus(BaseModel):
    ok: bool
    detail: str | None = None


class ReadinessResponse(BaseModel):
    status: str
    sqlite: ComponentStatus
    chroma: ComponentStatus
    ollama: ComponentStatus
    models: ComponentStatus
    ollama_models: list[str] = []
    message: str | None = None
