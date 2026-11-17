from langchain_ollama import OllamaEmbeddings

from app.config import get_settings


def get_embeddings() -> OllamaEmbeddings:
    settings = get_settings()
    return OllamaEmbeddings(
        model=settings.ollama_embed_model,
        base_url=settings.ollama_base_url,
        client_kwargs={"timeout": settings.ollama_timeout_seconds},
    )
