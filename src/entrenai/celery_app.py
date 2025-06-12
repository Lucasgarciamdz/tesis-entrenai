import os
from logging import getLogger

from celery import Celery

logger = getLogger(__name__)

# Default Redis URL
REDIS_URL = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")

try:
    app = Celery(
        "src.entrenai",  # Changed to be more specific
        broker=REDIS_URL,
        backend=REDIS_URL,
        include=["src.entrenai.celery_tasks"],  # Point to the new simplified tasks module
    )

    # Autodiscover tasks from all registered Django app configs.
    # app.autodiscover_tasks() # This is for Django, not directly applicable here.
    # We are using the 'include' argument in Celery constructor for non-Django projects.

    # Configuration
    app.conf.update(
        task_serializer="json",
        result_serializer="json",
        accept_content=["json"],
        task_track_started=True,
        broker_connection_retry_on_startup=True,
    )

    # Optional: Log Celery configuration
    logger.info(f"Celery app '{app.main}' initialized.")
    logger.info(f"Broker: {app.conf.broker_url}")
    logger.info(f"Backend: {app.conf.result_backend}")

except Exception as e:
    logger.error(f"Error initializing Celery app: {e}", exc_info=True)
    # You might want to raise the exception or handle it as appropriate
    # For example, if Celery is critical, you might exit the application
    raise

# Example task (can be in a different file like entrenai/background_tasks.py)
# @app.task
# def example_task(x, y):
#     return x + y

if __name__ == "__main__":
    # This is for running the Celery worker directly
    # e.g., celery -A entrenai.celery_app worker -l info
    app.start()
