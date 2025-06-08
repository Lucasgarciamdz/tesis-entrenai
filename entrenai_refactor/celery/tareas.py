import logging
from celery import shared_task

logger = logging.getLogger("entrenai")

@shared_task
def delegar_tarea_api(curso_id: int):
    logger.info(f"Delegando tarea para el curso {curso_id} a la API principal")
    # Aquí se haría una petición HTTP a la API principal
    return f"Tarea delegada para el curso {curso_id}" 