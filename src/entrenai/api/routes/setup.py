"""Endpoints para setup de IA."""

from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional
from loguru import logger
from pydantic import BaseModel

from entrenai.core.clients.moodle_client import MoodleClient
from entrenai.core.clients.n8n_client import N8NClient
from entrenai.core.db.pgvector_wrapper import PgVectorWrapper
from entrenai.config import get_config

router = APIRouter()


class SetupIAResponse(BaseModel):
    """Respuesta del setup de IA."""
    curso_id: int
    estado: str
    mensaje: str
    tabla_vectores: str
    workflow_url: Optional[str] = None


def get_moodle_client() -> MoodleClient:
    """Dependency para obtener cliente de Moodle."""
    config = get_config()
    return MoodleClient(config.moodle)


def get_n8n_client() -> N8NClient:
    """Dependency para obtener cliente de N8N."""
    config = get_config()
    return N8NClient(config.n8n)


def get_pgvector_wrapper() -> PgVectorWrapper:
    """Dependency para obtener wrapper de PgVector."""
    config = get_config()
    return PgVectorWrapper(config.pgvector)


@router.post("/courses/{course_id}/setup-ia", response_model=SetupIAResponse)
def setup_ia_curso(
    course_id: int,
    nombre_curso: Optional[str] = Query(None, description="Nombre del curso para la IA"),
    mensajes_iniciales: Optional[str] = Query(None, description="Mensajes iniciales para el chat"),
    moodle: MoodleClient = Depends(get_moodle_client),
    n8n: N8NClient = Depends(get_n8n_client),
    db: PgVectorWrapper = Depends(get_pgvector_wrapper),
):
    """
    Configura la IA para un curso específico.
    
    Pasos:
    1. Crea tabla de vectores
    2. Configura workflow en N8N
    3. Crea sección en Moodle
    """
    logger.info(f"Iniciando setup de IA para curso {course_id}")
    
    try:
        # 1. Obtener nombre del curso si no se proporciona
        if not nombre_curso:
            courses = moodle.get_all_courses()
            course = next((c for c in courses if c.id == course_id), None)
            if not course:
                raise HTTPException(status_code=404, detail="Curso no encontrado")
            nombre_curso = course.fullname
        
        # 2. Crear tabla de vectores
        tabla_vectores = f"curso_{course_id}_vectores"
        db.create_collection(tabla_vectores)
        logger.info(f"Tabla de vectores creada: {tabla_vectores}")
        
        # 3. Configurar workflow en N8N
        workflow_name = f"Chat_Curso_{course_id}"
        workflow_data = {
            "name": workflow_name,
            "nodes": [
                {
                    "name": "Webhook",
                    "type": "n8n-nodes-base.webhook",
                    "parameters": {"path": f"curso-{course_id}"}
                }
            ]
        }
        
        workflow = n8n.create_workflow(workflow_data)
        workflow_url = f"{n8n.base_url}/webhook/curso-{course_id}" if workflow else None
        
        # 4. Crear sección en Moodle
        seccion_nombre = "Asistente IA"
        seccion = moodle.create_course_section(course_id, seccion_nombre)
        
        if seccion:
            # Crear enlace al chat
            if workflow_url:
                moodle.create_url_in_section(
                    course_id,
                    seccion.id,
                    "Chat con IA",
                    workflow_url,
                    "Asistente inteligente para el curso"
                )
        
        return SetupIAResponse(
            curso_id=course_id,
            estado="exitoso",
            mensaje=f"Setup completado para {nombre_curso}",
            tabla_vectores=tabla_vectores,
            workflow_url=workflow_url
        )
        
    except Exception as e:
        logger.error(f"Error en setup de IA para curso {course_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Error en setup: {str(e)}")
