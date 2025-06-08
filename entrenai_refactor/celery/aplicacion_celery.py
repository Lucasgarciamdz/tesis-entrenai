from celery import Celery
import logging

logger = logging.getLogger("entrenai")

app = Celery("entrenai_celery", broker="redis://localhost:6379/0")

@app.task
def tarea_ejemplo():
    logger.info("Ejecutando tarea de ejemplo en Celery")
    return "Tarea completada" 