"""Proveedor de IA usando Google Gemini."""

from typing import List, Dict, Any, Optional
import google.genai as genai
from google.genai import types
from loguru import logger

from .providers import AIProvider
from ..config.settings import Settings


class GeminiProvider(AIProvider):
    """Proveedor de IA usando Google Gemini."""
    
    def __init__(self, settings: Settings):
        super().__init__(settings)
        if not settings.ai.gemini_api_key:
            raise ValueError("API key de Gemini no configurada")
        
        # Configurar cliente de Gemini
        self.client = genai.Client(api_key=settings.ai.gemini_api_key)
        self.model = settings.ai.gemini_model
        self.embedding_model = "text-embedding-004"  # Modelo de embeddings de Gemini
        logger.info(f"GeminiProvider inicializado - Modelo: {self.model}")
    
    async def generate_embedding(self, text: str) -> List[float]:
        """Genera embedding para un texto."""
        try:
            response = self.client.models.embed_content(
                model=self.embedding_model,
                contents=text
            )
            
            if hasattr(response, 'embeddings') and len(response.embeddings) > 0:
                return response.embeddings[0].values
            return []
        except Exception as e:
            logger.error(f"Error generando embedding: {e}")
            return []
    
    async def generate_embeddings_batch(self, texts: List[str]) -> List[List[float]]:
        """Genera embeddings para múltiples textos."""
        try:
            response = self.client.models.embed_content(
                model=self.embedding_model,
                contents=texts
            )
            
            if hasattr(response, 'embeddings'):
                return [embedding.values for embedding in response.embeddings]
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
            
            response = self.client.models.generate_content(
                model=self.model,
                contents=full_prompt
            )
            
            return response.text if hasattr(response, 'text') else ""
        except Exception as e:
            logger.error(f"Error generando respuesta: {e}")
            return "Lo siento, no pude generar una respuesta en este momento."
    
    async def chat(self, messages: List[Dict[str, str]]) -> str:
        """Genera respuesta en formato chat."""
        try:
            # Convertir mensajes al formato de Gemini
            contents = []
            for message in messages:
                role = message.get('role', 'user')
                content = message.get('content', '')
                
                if role == 'user':
                    contents.append(types.Content(
                        role='user',
                        parts=[types.Part.from_text(text=content)]
                    ))
                elif role == 'assistant':
                    contents.append(types.Content(
                        role='model',
                        parts=[types.Part.from_text(text=content)]
                    ))
            
            # Si solo hay un mensaje de usuario, generar respuesta directamente
            if len(contents) == 1 and contents[0].role == 'user':
                response = self.client.models.generate_content(
                    model=self.model,
                    contents=contents[0].parts[0].text
                )
                return response.text if hasattr(response, 'text') else ""
            
            # Para conversaciones multi-turno, usar chat
            chat = self.client.chats.create(model=self.model)
            
            # Enviar todos los mensajes excepto el último
            for content in contents[:-1]:
                if content.role == 'user':
                    chat.send_message(content.parts[0].text)
            
            # Enviar el último mensaje y obtener respuesta
            if contents:
                last_message = contents[-1]
                if last_message.role == 'user':
                    response = chat.send_message(last_message.parts[0].text)
                    return response.text if hasattr(response, 'text') else ""
            
            return "No se pudo procesar la conversación."
            
        except Exception as e:
            logger.error(f"Error en chat: {e}")
            return "Lo siento, ocurrió un error al procesar tu mensaje."
    
    def check_health(self) -> bool:
        """Verifica si Gemini está disponible."""
        try:
            # Hacer una llamada simple para verificar conectividad
            response = self.client.models.generate_content(
                model=self.model,
                contents="Hello"
            )
            return True
        except Exception as e:
            logger.error(f"Gemini no está disponible: {e}")
            return False
    
    def list_models(self) -> List[str]:
        """Lista los modelos disponibles de Gemini."""
        try:
            # Gemini tiene modelos predefinidos
            return [
                "gemini-1.5-flash",
                "gemini-1.5-pro", 
                "gemini-2.0-flash-001",
                "text-embedding-004"
            ]
        except Exception as e:
            logger.error(f"Error listando modelos: {e}")
            return []
    
    async def generate_structured_response(self, prompt: str, schema: Dict[str, Any]) -> Dict[str, Any]:
        """Genera respuesta estructurada usando un schema JSON."""
        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type='application/json',
                    response_schema=schema
                )
            )
            
            import json
            return json.loads(response.text) if hasattr(response, 'text') else {}
        except Exception as e:
            logger.error(f"Error generando respuesta estructurada: {e}")
            return {}
