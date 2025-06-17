"""Proveedores de IA simplificados."""

from .providers import AIProvider, get_ai_provider
from .ollama import OllamaProvider 
from .gemini import GeminiProvider

__all__ = [
    "AIProvider",
    "get_ai_provider",
    "OllamaProvider",
    "GeminiProvider"
]
