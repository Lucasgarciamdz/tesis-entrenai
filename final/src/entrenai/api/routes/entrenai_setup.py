from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional
from loguru import logger
from pydantic import BaseModel

from entrenai.core.clients.moodle_client import MoodleClient

router = APIRouter()

class ConfiguracionIAResponse(BaseModel):
    """Modelo de respuesta para la configuración de IA de un curso."""
    curso_id: int
    estado: str
    mensaje: str
    nombre_tabla_vectores: str
    url_chat: Optional[str] = None

@router.post("/cursos/{curso_id}/configurar-ia", response_model=ConfiguracionIAResponse)
def configurar_ia_para_curso(
    curso_id: int,
    nombre_curso: Optional[str] = Query(None, alias="nombreCurso", description="Nombre del curso para la IA"),
    mensajes_iniciales: Optional[str] = Query(None, alias="mensajesIniciales", description="Mensajes iniciales para el chat"),
    moodle: MoodleClient = Depends(get_moodle_client),
):
    """
    Configura la IA para un curso específico de Moodle.
    
    Este endpoint realiza las siguientes tareas:
    1. Crea/obtiene una tabla de vectores para el curso
    2. Configura el workflow de chat
    3. Crea una sección en Moodle con los recursos necesarios
    """
    logger.info(f"Iniciando configuración de IA para el curso {curso_id}")
    
    try:
        # 1. Obtener o validar el nombre del curso
        nombre_curso_final = nombre_curso or obtener_nombre_curso(curso_id, moodle)
        logger.info(f"Nombre del curso configurado: {nombre_curso_final}")

        # 2. Crear tabla de vectores
        nombre_tabla = f"curso_{curso_id}_vectores"
        # Aquí llamarías a tu función para crear la tabla de vectores
        
        # 3. Configurar workflow de chat
        url_chat = "URL_PLACEHOLDER"  # Aquí configurarías el workflow real
        
        # 4. Crear sección en Moodle con recursos
        seccion_id = crear_seccion_moodle(curso_id, moodle)
        
        # 5. Preparar y retornar respuesta
        return ConfiguracionIAResponse(
            curso_id=curso_id,
            estado="exitoso",
            mensaje=f"Configuración completada para el curso {curso_id}",
            nombre_tabla_vectores=nombre_tabla,
            url_chat=url_chat
        )

    except Exception as e:
        logger.error(f"Error durante la configuración de IA para el curso {curso_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error en la configuración: {str(e)}"
        )

def obtener_nombre_curso(curso_id: int, moodle: MoodleClient) -> str:
    """Obtiene el nombre del curso desde Moodle."""
    # Implementar lógica para obtener nombre del curso
    return f"Curso_{curso_id}"

def crear_seccion_moodle(curso_id: int, moodle: MoodleClient) -> int:
    """Crea una sección en Moodle con los recursos necesarios."""
    # Implementar lógica para crear sección
    return 1  # Retorna el ID de la sección creada
