"""
Tareas asíncronas para el procesamiento de documentos.
"""
import logging
from typing import Dict, Any

from ..config.settings import get_settings
from .files.processor import FileProcessor
from .ai.service import AIService
from .db.repository import DocumentRepository

logger = logging.getLogger(__name__)
settings = get_settings()


def process_document_task(
    file_path: str,
    document_id: str,
    user_id: str = None
) -> Dict[str, Any]:
    """
    Procesa un documento de forma asíncrona.
    
    Args:
        file_path: Ruta al archivo a procesar
        document_id: ID único del documento
        user_id: ID del usuario (opcional)
        
    Returns:
        Dict con el resultado del procesamiento
    """
    try:
        logger.info(f"Iniciando procesamiento del documento {document_id}")
        
        # Procesar archivo
        processor = FileProcessor()
        content = processor.process_file(file_path)
        
        if not content:
            raise ValueError("No se pudo extraer contenido del archivo")
        
        # Generar embeddings
        ai_service = AIService()
        chunks = processor.split_text(content)
        embeddings = []
        
        for chunk in chunks:
            embedding = ai_service.generate_embedding(chunk)
            embeddings.append({
                'text': chunk,
                'embedding': embedding
            })
        
        # Guardar en base de datos
        doc_repo = DocumentRepository()
        result = doc_repo.save_document_embeddings(
            document_id=document_id,
            embeddings=embeddings,
            user_id=user_id
        )
        
        logger.info(f"Documento {document_id} procesado exitosamente. {len(embeddings)} chunks guardados.")
        
        return {
            'status': 'success',
            'document_id': document_id,
            'chunks_processed': len(embeddings),
            'message': 'Documento procesado exitosamente'
        }
        
    except Exception as e:
        logger.error(f"Error procesando documento {document_id}: {str(e)}")
        return {
            'status': 'error',
            'document_id': document_id,
            'error': str(e),
            'message': 'Error procesando el documento'
        }


def generate_response_task(
    question: str,
    user_id: str = None,
    context_limit: int = 5
) -> Dict[str, Any]:
    """
    Genera una respuesta basada en los documentos procesados.
    
    Args:
        question: Pregunta del usuario
        user_id: ID del usuario (opcional)
        context_limit: Número máximo de contextos a usar
        
    Returns:
        Dict con la respuesta generada
    """
    try:
        logger.info(f"Generando respuesta para pregunta: {question[:100]}...")
        
        # Buscar contexto relevante
        doc_repo = DocumentRepository()
        ai_service = AIService()
        
        # Generar embedding de la pregunta
        question_embedding = ai_service.generate_embedding(question)
        
        # Buscar documentos similares
        similar_docs = doc_repo.search_similar_documents(
            embedding=question_embedding,
            limit=context_limit,
            user_id=user_id
        )
        
        if not similar_docs:
            return {
                'status': 'success',
                'response': 'Lo siento, no encontré información relevante para responder tu pregunta.',
                'sources': []
            }
        
        # Construir context
        context = "\n\n".join([doc['text'] for doc in similar_docs])
        
        # Generar respuesta
        response = ai_service.generate_response(question, context)
        
        logger.info("Respuesta generada exitosamente")
        
        return {
            'status': 'success',
            'response': response,
            'sources': [doc['document_id'] for doc in similar_docs],
            'context_used': len(similar_docs)
        }
        
    except Exception as e:
        logger.error(f"Error generando respuesta: {str(e)}")
        return {
            'status': 'error',
            'error': str(e),
            'message': 'Error generando la respuesta'
        }
