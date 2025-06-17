"""Proveedor de IA usando Ollama."""

from typing import List, Dict, Any, Optional
import ollama
from loguru import logger

from .providers import AIProvider
from ..config.settings import Settings


class OllamaProvider(AIProvider):
    """Proveedor de IA usando Ollama."""
    
    def __init__(self, settings: Settings):
        super().__init__(settings)
        self.client = ollama.Client(host=settings.ai.ollama_url)
        self.model = settings.ai.ollama_model
        self.embedding_model = settings.ai.embedding_model
        logger.info(f"OllamaProvider inicializado - URL: {settings.ai.ollama_url}, Modelo: {self.model}")
    
    async def generate_embedding(self, text: str) -> List[float]:
        """Genera embedding para un texto."""
        try:
            response = self.client.embed(model=self.embedding_model, input=text)
            if 'embeddings' in response and len(response['embeddings']) > 0:
                return response['embeddings'][0]
            return []
        except Exception as e:
            logger.error(f"Error generando embedding: {e}")
            return []
    
    async def generate_embeddings_batch(self, texts: List[str]) -> List[List[float]]:
        """Genera embeddings para múltiples textos."""
        try:
            response = self.client.embed(model=self.embedding_model, input=texts)
            if 'embeddings' in response:
                return response['embeddings']
            return []
        except Exception as e:
            logger.error(f"Error generando embeddings batch: {e}")
            return []
    
    async def generate_response(self, prompt: str, context: Optional[str] = None) -> str:
        """Genera respuesta de texto."""
        try:
            full_prompt = prompt
            if context:
                full_prompt = f"Contexto: {context}\n\nPregunta: {prompt}"
            
            response = self.client.generate(model=self.model, prompt=full_prompt)
            return response.get('response', '')
        except Exception as e:
            logger.error(f"Error generando respuesta: {e}")
            return "Lo siento, no pude generar una respuesta en este momento."
    
    async def chat(self, messages: List[Dict[str, str]]) -> str:
        """Genera respuesta en formato chat."""
        try:
            response = self.client.chat(model=self.model, messages=messages)
            if 'message' in response and 'content' in response['message']:
                return response['message']['content']
            return "No pude procesar el mensaje."
        except Exception as e:
            logger.error(f"Error en chat: {e}")
            return "Lo siento, ocurrió un error al procesar tu mensaje."
    
    def check_health(self) -> bool:
        """Verifica si Ollama está disponible."""
        try:
            models = self.client.list()
            return True
        except Exception as e:
            logger.error(f"Ollama no está disponible: {e}")
            return False
    
    def list_models(self) -> List[str]:
        """Lista los modelos disponibles."""
        try:
            response = self.client.list()
            if 'models' in response:
                return [model['name'] for model in response['models']]
            return []
        except Exception as e:
            logger.error(f"Error listando modelos: {e}")
            return []
    
    def pull_model(self, model_name: str) -> bool:
        """Descarga un modelo."""
        try:
            self.client.pull(model_name)
            logger.info(f"Modelo {model_name} descargado exitosamente")
            return True
        except Exception as e:
            logger.error(f"Error descargando modelo {model_name}: {e}")
            return False
