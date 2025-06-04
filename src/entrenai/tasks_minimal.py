# Apply eventlet monkey patch before any imports
try:
    import eventlet

    eventlet.monkey_patch()
except ImportError:
    # eventlet not available, continue without patching
    pass

import logging
import os
import requests

from celery import Celery

# Create the celery app instance here to avoid circular imports
app = Celery("entrenai_minimal")

# Configure the app directly here
REDIS_URL = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")

app.conf.update(
    broker=REDIS_URL,
    backend=REDIS_URL,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_track_started=True,
    broker_connection_retry_on_startup=True,
)

logger = logging.getLogger(__name__)
logger.info("Celery minimal app configured.")
logger.info(f"Broker: {REDIS_URL}")
logger.info(f"Backend: {REDIS_URL}")

# URL de la aplicación FastAPI (configurable vía env var)
FASTAPI_BASE_URL = os.getenv("FASTAPI_BASE_URL", "http://entrenai_api:8000")


@app.task(bind=True, name="entrenai.minimal.process_moodle_file_http")
def process_moodle_file_http(
    self,
    course_id: int,
    course_name_for_pgvector: str,
    moodle_file_info: dict,
    download_dir_str: str,
    ai_provider_config: dict,
    pgvector_config_dict: dict,
    moodle_config_dict: dict,
    base_config_dict: dict,
):
    """
    Tarea Celery minimalista que solo hace un request HTTP a la aplicación FastAPI.
    """
    filename = moodle_file_info.get("filename", "unknown")
    task_id = self.request.id

    logger.info(
        f"Task ID: {task_id} - Sending HTTP request to FastAPI for file: {filename}"
    )

    try:
        # Preparar el payload para el request
        payload = {
            "task_id": task_id,
            "course_id": course_id,
            "course_name_for_pgvector": course_name_for_pgvector,
            "moodle_file_info": moodle_file_info,
            "download_dir_str": download_dir_str,
            "ai_provider_config": ai_provider_config,
            "pgvector_config_dict": pgvector_config_dict,
            "moodle_config_dict": moodle_config_dict,
            "base_config_dict": base_config_dict,
        }

        # Hacer el request a FastAPI
        url = f"{FASTAPI_BASE_URL}/api/v1/internal/process-file"

        logger.info(f"Task ID: {task_id} - Making HTTP request to: {url}")

        response = requests.post(
            url,
            json=payload,
            timeout=300,  # 5 minutos timeout
            headers={"Content-Type": "application/json"},
        )

        if response.status_code == 200:
            result = response.json()
            logger.info(f"Task ID: {task_id} - Successfully processed file: {filename}")
            return result
        else:
            error_msg = f"FastAPI returned status {response.status_code}"
            try:
                error_detail = response.json().get("detail", error_msg)
            except Exception:
                error_detail = error_msg

            logger.error(f"Task ID: {task_id} - Error from FastAPI: {error_detail}")
            return {
                "filename": filename,
                "status": "error",
                "error_message": error_detail,
                "task_id": task_id,
            }

    except requests.RequestException as e:
        logger.error(f"Task ID: {task_id} - Network error contacting FastAPI: {e}")
        return {
            "filename": filename,
            "status": "error",
            "error_message": f"Network error: {str(e)}",
            "task_id": task_id,
        }
    except Exception as e:
        logger.error(f"Task ID: {task_id} - Unexpected error: {e}", exc_info=True)
        return {
            "filename": filename,
            "status": "error",
            "error_message": f"Unexpected error: {str(e)}",
            "task_id": task_id,
        }
