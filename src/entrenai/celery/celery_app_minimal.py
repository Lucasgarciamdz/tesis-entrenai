import os
from celery import Celery

# Get broker and backend URLs from environment variables
broker_url = os.environ.get("CELERY_BROKER_URL", "redis://redis:6379/0")
result_backend = os.environ.get("CELERY_RESULT_BACKEND", "redis://redis:6379/0")

# Create a Celery app instance
app = Celery(
    "entrenai_minimal",
    broker=broker_url,
    backend=result_backend,
    include=["src.entrenai.tasks_minimal"]
)

# Optional Celery configuration
app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    broker_connection_retry_on_startup=True,  # Fix deprecation warning
)
