"""Cliente simplificado para Ollama."""

import httpx
from typing import List

from ...config import settings


class OllamaClient:
    """Cliente para interactuar con Ollama."""
    
    def __init__(self):
        self.base_url = settings.ollama_url
        
    def generate_embeddings(self, text: str) -> List[float]:
        """Genera embeddings para un texto."""
        url = f"{self.base_url}/api/embeddings"
        data = {
            "model": settings.embedding_model,
            "prompt": text
        }
        
        with httpx.Client() as client:
            response = client.post(url, json=data)
            response.raise_for_status()
            return response.json()["embedding"]
    
    def chat(self, messages: List[dict], stream: bool = False) -> str:
        """Genera respuesta de chat."""
        url = f"{self.base_url}/api/chat"
        data = {
            "model": settings.chat_model,
            "messages": messages,
            "stream": stream
        }
        
        with httpx.Client() as client:
            response = client.post(url, json=data)
            response.raise_for_status()
            result = response.json()
            return result["message"]["content"]
