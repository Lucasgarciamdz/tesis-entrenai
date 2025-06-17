# Clientes simplificados para Entrenai
from .moodle_client import MoodleClient, MoodleAPIError
from .n8n_client import N8NClient, N8NClientError

__all__ = ["MoodleClient", "MoodleAPIError", "N8NClient", "N8NClientError"]
