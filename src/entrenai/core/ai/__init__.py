# src/entrenai/core/ai/__init__.py
# Use lazy imports to avoid import errors when modules are missing
__all__ = [
    "get_ai_wrapper",
    "AIProviderError",
    "EmbeddingManager",
    "GeminiWrapper",
    "GeminiWrapperError",
    "OllamaWrapper",
    "OllamaWrapperError",
]


# Define AIProviderError here to avoid circular imports
class AIProviderError(Exception):
    """Custom exception for AI provider errors."""

    pass


def get_ai_wrapper(*args, **kwargs):
    from .ai_provider import get_ai_wrapper as _get_ai_wrapper

    return _get_ai_wrapper(*args, **kwargs)


class EmbeddingManager:
    def __new__(cls, *args, **kwargs):
        from .embedding_manager import EmbeddingManager as _EmbeddingManager

        return _EmbeddingManager(*args, **kwargs)


class GeminiWrapper:
    def __new__(cls, *args, **kwargs):
        from .gemini_wrapper import GeminiWrapper as _GeminiWrapper

        return _GeminiWrapper(*args, **kwargs)


class GeminiWrapperError(Exception):
    """Custom exception for GeminiWrapper errors."""

    pass


class OllamaWrapper:
    def __new__(cls, *args, **kwargs):
        from .ollama_wrapper import OllamaWrapper as _OllamaWrapper

        return _OllamaWrapper(*args, **kwargs)


class OllamaWrapperError(Exception):
    """Custom exception for OllamaWrapper errors."""

    pass
