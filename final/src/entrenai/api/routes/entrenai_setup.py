from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional
from loguru import logger

from entrenai.api.models.base import ConfiguracionIAResponse
from entrenai.core.clients.moodle_client import MoodleClient, get_moodle_client
from entrenai.core.clients.n8n_client import N8NClient, get_n8n_client
from entrenai.core.db.pgvector_wrapper import PgvectorWrapper, get_pgvector_client

router = APIRouter()

@router.post("/cursos/{curso_id}/configurar-ia", response_model=ConfiguracionIAResponse)
def configurar_ia_para_curso(
    curso_id: int,
    nombre_curso: Optional[str] = Query(None, alias="nombreCurso", description="Nombre del curso para la IA"),
    mensajes_iniciales: Optional[str] = Query("", alias="mensajesIniciales", description="Mensajes iniciales para el chat"),
    moodle: MoodleClient = Depends(get_moodle_client),
    n8n: N8NClient = Depends(get_n8n_client),
    pgvector: PgvectorWrapper = Depends(get_pgvector_client),
):
    """
    Configura la IA para un curso específico de Moodle.
    
    Flujo simplificado:
    1. Obtiene el nombre del curso desde Moodle
    2. Crea la tabla de vectores en PostgreSQL
    3. Configura y despliega el workflow de chat en N8N
    4. Crea una sección en Moodle con el enlace al chat
    """
    logger.info(f"Iniciando configuración de IA para el curso {curso_id}")
    
    try:
        # 1. Obtener información del curso
        if nombre_curso:
            nombre_curso_final = nombre_curso
        else:
            curso_info = moodle.get_course_info(curso_id)
            nombre_curso_final = curso_info.get("displayname", f"Curso_{curso_id}")
        
        logger.info(f"Configurando IA para: {nombre_curso_final}")

        # 2. Crear tabla de vectores
        nombre_tabla = f"curso_{curso_id}_vectores"
        if not pgvector.ensure_table(nombre_tabla):
            raise Exception("No se pudo crear la tabla de vectores")
        
        # 3. Configurar workflow de chat en N8N
        url_chat = n8n.configure_and_deploy_chat_workflow(
            course_id=curso_id,
            table_name=nombre_tabla,
            initial_messages=mensajes_iniciales or "¡Hola! Soy el asistente de IA de este curso."
        )
        
        # 4. Crear sección en Moodle con el chat
        moodle.create_course_section(curso_id, "IA del Curso")
        # TODO: Obtener el ID de la sección creada y agregar el enlace al chat
        
        logger.info(f"Configuración completada para curso {curso_id}")
        
        return ConfiguracionIAResponse(
            curso_id=curso_id,
            estado="exitoso",
            mensaje=f"IA configurada exitosamente para '{nombre_curso_final}'",
            nombre_tabla_vectores=nombre_tabla,
            url_chat=url_chat
        )

    except Exception as e:
        logger.error(f"Error configurando IA para curso {curso_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error en la configuración: {str(e)}"
        )

# Funciones auxiliares removidas - ahora integradas en el endpoint principal
