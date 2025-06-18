from typing import Optional
from fastapi import HTTPException

from src.entrenai.config.logger import get_logger
from src.entrenai.core.clients.moodle_client import MoodleClient, MoodleAPIError
from src.entrenai.config import moodle_config

logger = get_logger(__name__)


async def get_course_name_for_operations(course_id: int, moodle: MoodleClient) -> str:
    """
    Obtiene el nombre del curso para operaciones de Pgvector.
    """
    course_name_for_pgvector: Optional[str] = None
    try:
        logger.info(f"Obteniendo nombre del curso {course_id}...")
        target_user_id_for_name = moodle_config.default_teacher_id
        if target_user_id_for_name:
            courses = moodle.get_courses_by_user(user_id=target_user_id_for_name)
            course = next((c for c in courses if c.id == course_id), None)
            if course:
                course_name_for_pgvector = course.displayname or course.fullname

        if not course_name_for_pgvector:
            all_courses = moodle.get_all_courses()
            course = next((c for c in all_courses if c.id == course_id), None)
            if course:
                course_name_for_pgvector = course.displayname or course.fullname

        if not course_name_for_pgvector:
            logger.warning(f"No se pudo encontrar el curso {course_id} en Moodle.")
            raise HTTPException(
                status_code=404,
                detail=f"Curso con ID {course_id} no encontrado en Moodle.",
            )

        logger.info(f"Nombre del curso obtenido: '{course_name_for_pgvector}'")
        return course_name_for_pgvector
    except MoodleAPIError as e:
        logger.error(f"Error de API de Moodle al obtener el nombre del curso {course_id}: {e}")
        raise HTTPException(
            status_code=502,
            detail=f"Error de API de Moodle al intentar obtener el nombre del curso {course_id}.",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error inesperado al obtener el nombre del curso {course_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"No se pudo determinar el nombre del curso {course_id}.",
        )


def get_course_name_from_query_or_moodle(
    course_id: int, course_name_query: Optional[str], moodle: MoodleClient
) -> str:
    """
    Obtiene el nombre del curso desde la query o desde Moodle como fallback.
    """
    if course_name_query:
        logger.info(f"Nombre del curso proporcionado: '{course_name_query}'")
        return course_name_query

    try:
        logger.info(f"Intentando obtener nombre del curso {course_id} desde Moodle...")
        course_name = None
        
        if moodle_config.default_teacher_id:
            courses = moodle.get_courses_by_user(user_id=moodle_config.default_teacher_id)
            course = next((c for c in courses if c.id == course_id), None)
            if course:
                course_name = course.displayname or course.fullname
        
        if not course_name:
            all_courses = moodle.get_all_courses()
            course = next((c for c in all_courses if c.id == course_id), None)
            if course:
                course_name = course.displayname or course.fullname
                
        if course_name:
            logger.info(f"Nombre del curso obtenido de Moodle: '{course_name}'")
            return course_name
        else:
            logger.warning(f"No se pudo encontrar el curso {course_id} en Moodle.")
            
    except Exception as e:
        logger.warning(f"Excepción al obtener el nombre del curso {course_id} desde Moodle: {e}")
    
    # Fallback
    fallback_name = f"Curso_{course_id}"
    logger.warning(f"Usando nombre de curso por defecto: '{fallback_name}'")
    return fallback_name
