"""Servicio de chat simplificado con IA."""

from typing import List, Optional
from ..config import Config
from ..ai.providers import get_ai_provider
from ..db.vector_store import VectorStore
from ..models import ChatMessage, ChatResponse


class ChatService:
    """Servicio simplificado de chat con IA."""
    
    def __init__(self, config: Config):
        self.config = config
        self.ai_provider = get_ai_provider(config.ai)
        self.vector_store = VectorStore(config)
    
    async def chat_with_context(
        self,
        course_id: int,
        message: str,
        chat_history: Optional[List[ChatMessage]] = None
    ) -> ChatResponse:
        """Responde un mensaje usando contexto del curso."""
        
        if not chat_history:
            chat_history = []
        
        # 1. Buscar contexto relevante en vectores
        vector_table = f"curso_{course_id}_vectores"
        context_docs = []
        
        try:
            # Generar embedding de la pregunta
            query_embedding = await self.ai_provider.generate_embeddings([message])
            
            # Buscar documentos similares
            similar_docs = await self.vector_store.similarity_search(
                vector_table,
                query_embedding[0],
                limit=3,
                threshold=0.6
            )
            
            context_docs = [doc["content"] for doc in similar_docs]
            
        except Exception as e:
            print(f"Error buscando contexto: {e}")
        
        # 2. Construir prompt con contexto
        context_text = "\n\n".join(context_docs) if context_docs else ""
        
        system_message = ChatMessage(
            role="system",
            content=f"""Eres un asistente educativo para el curso. 
            
Usa el siguiente contexto para responder las preguntas:

{context_text}

Si no encuentras información relevante en el contexto, indica que no tienes esa información específica del curso."""
        )
        
        # 3. Preparar mensajes para el modelo
        messages = [system_message] + chat_history + [ChatMessage(role="user", content=message)]
        
        # 4. Obtener respuesta de la IA
        try:
            response = await self.ai_provider.chat(messages)
            
            # Añadir fuentes si hay contexto
            if context_docs:
                response.sources = [f"Documento {i+1}" for i in range(len(context_docs))]
            
            return response
            
        except Exception as e:
            return ChatResponse(
                message=f"Error al generar respuesta: {str(e)}",
                sources=[]
            )
    
    async def simple_chat(self, message: str) -> ChatResponse:
        """Chat simple sin contexto específico."""
        messages = [ChatMessage(role="user", content=message)]
        
        try:
            return await self.ai_provider.chat(messages)
        except Exception as e:
            return ChatResponse(
                message=f"Error al generar respuesta: {str(e)}",
                sources=[]
            )
