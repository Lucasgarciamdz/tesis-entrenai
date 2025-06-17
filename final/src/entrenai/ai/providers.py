"""Interfaz base para proveedores de IA."""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from ..config.settings import Settings, get_settings


class AIProvider(ABC):
    """Interfaz base para proveedores de IA."""
    
    def __init__(self, settings: Settings):
        self.settings = settings
    
    @abstractmethod
    async def generate_embedding(self, text: str) -> List[float]:
        """Genera embedding para un texto."""
        pass
    
    @abstractmethod
    async def generate_embeddings_batch(self, texts: List[str]) -> List[List[float]]:
        """Genera embeddings para múltiples textos."""
        pass
    
    @abstractmethod
    async def generate_response(self, prompt: str, context: Optional[str] = None) -> str:
        """Genera respuesta de texto."""
        pass
    
    @abstractmethod
    async def chat(self, messages: List[Dict[str, str]]) -> str:
        """Genera respuesta en formato chat."""
        pass


def get_ai_provider(settings: Settings = None) -> AIProvider:
    """Factory para obtener el proveedor de IA configurado."""
    if settings is None:
        settings = get_settings()
    
    if settings.ai.provider == "ollama":
        from .ollama import OllamaProvider
        return OllamaProvider(settings)
    elif settings.ai.provider == "gemini":
        from .gemini import GeminiProvider
        return GeminiProvider(settings)
    else:
        raise ValueError(f"Proveedor de IA no soportado: {settings.ai.provider}")
