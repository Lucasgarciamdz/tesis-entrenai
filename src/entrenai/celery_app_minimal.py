import os
from logging import getLogger

from celery import Celery

logger = getLogger(__name__)

# Default Redis URL
REDIS_URL = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")

try:
    app = Celery(
        "entrenai_minimal",
        broker=REDIS_URL,
        backend=REDIS_URL,
        include=["src.entrenai.tasks_minimal"],
    )

    # Configuration
    app.conf.update(
        task_serializer="json",
        result_serializer="json",
        accept_content=["json"],
        task_track_started=True,
        broker_connection_retry_on_startup=True,
    )

    logger.info("Celery minimal app initialized.")
    logger.info(f"Broker: {app.conf.broker_url}")
    logger.info(f"Backend: {app.conf.result_backend}")

except Exception as e:
    logger.error(f"Error initializing Celery minimal app: {e}", exc_info=True)
    raise

if __name__ == "__main__":
    app.start()
