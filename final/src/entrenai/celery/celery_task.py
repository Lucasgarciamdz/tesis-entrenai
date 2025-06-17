"""
Tareas de Celery para procesamiento asíncrono.
"""
import logging
from typing import Dict, Any

from .celery_app import app
from ..core.tasks import process_document_task, generate_response_task

logger = logging.getLogger(__name__)


@app.task(bind=True, name="process_document")
def process_document_async(self, file_path: str, document_id: str, user_id: str = None) -> Dict[str, Any]:
    """
    Tarea de Celery para procesar documentos de forma asíncrona.
    
    Args:
        file_path: Ruta al archivo a procesar
        document_id: ID único del documento
        user_id: ID del usuario (opcional)
        
    Returns:
        Dict con el resultado del procesamiento
    """
    task_id = self.request.id
    logger.info(f"Task {task_id}: Iniciando procesamiento de documento {document_id}")
    
    try:
        result = process_document_task(file_path, document_id, user_id)
        result['task_id'] = task_id
        return result
        
    except Exception as e:
        logger.error(f"Task {task_id}: Error en procesamiento: {str(e)}")
        return {
            'status': 'error',
            'task_id': task_id,
            'document_id': document_id,
            'error': str(e),
            'message': 'Error en tarea de procesamiento'
        }


@app.task(bind=True, name="generate_response")
def generate_response_async(
    self,
    question: str,
    user_id: str = None,
    context_limit: int = 5
) -> Dict[str, Any]:
    """
    Tarea de Celery para generar respuestas de forma asíncrona.
    
    Args:
        question: Pregunta del usuario
        user_id: ID del usuario (opcional)
        context_limit: Número máximo de contextos a usar
        
    Returns:
        Dict con la respuesta generada
    """
    task_id = self.request.id
    logger.info(f"Task {task_id}: Generando respuesta para pregunta")
    
    try:
        result = generate_response_task(question, user_id, context_limit)
        result['task_id'] = task_id
        return result
        
    except Exception as e:
        logger.error(f"Task {task_id}: Error generando respuesta: {str(e)}")
        return {
            'status': 'error',
            'task_id': task_id,
            'error': str(e),
            'message': 'Error en tarea de generación de respuesta'
        }


@app.task(bind=True, name="health_check")
def health_check_task(self) -> Dict[str, Any]:
    """
    Tarea simple para verificar el estado del worker.
    """
    task_id = self.request.id
    logger.info(f"Task {task_id}: Health check")
    
    return {
        'status': 'healthy',
        'task_id': task_id,
        'message': 'Celery worker está funcionando correctamente'
    }
