# src/entrenai/core/clients/__init__.py
from .moodle_client import MoodleClient, MoodleAPIError
from .n8n_client import N8NClient

__all__ = ["MoodleClient", "MoodleAPIError", "N8NClient"]
