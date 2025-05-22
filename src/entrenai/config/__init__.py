# src/entrenai/config/__init__.py
from .config import (
    # Config instances
    base_config,
    moodle_config,
    pgvector_config,
    ollama_config,
    gemini_config,
    n8n_config,
    celery_config,
    # Config classes
    BaseConfig,
    MoodleConfig,
    PgvectorConfig,
    OllamaConfig,
    GeminiConfig,
    N8NConfig,
    CeleryConfig,
)

__all__ = [
    # Config instances
    "base_config",
    "moodle_config",
    "pgvector_config",
    "ollama_config",
    "gemini_config",
    "n8n_config",
    "celery_config",
    # Config classes
    "BaseConfig",
    "MoodleConfig",
    "PgvectorConfig",
    "OllamaConfig",
    "GeminiConfig",
    "N8NConfig",
    "CeleryConfig",
]
