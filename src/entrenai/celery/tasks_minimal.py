# flake8: noqa: E402 - imports after eventlet monkey patch is required
import os
import requests
from .celery_app_minimal import app

# Get the base URL for the FastAPI application from environment variables
FASTAPI_BASE_URL = os.environ.get("FASTAPI_BASE_URL", "http://localhost:8000")

@app.task(name="process_moodle_course_content_minimal")
def process_moodle_course_content_minimal(course_id: int, user_id: int):
    """
    A minimal Celery task that triggers the file processing endpoint in the FastAPI app.
    """
    endpoint = f"{FASTAPI_BASE_URL}/api/v1/courses/process-moodle-course-content/"
    payload = {
        "course_id": course_id,
        "user_id": user_id
    }
    try:
        response = requests.post(endpoint, json=payload)
        response.raise_for_status()  # Raise an exception for bad status codes
        return response.json()
    except requests.exceptions.RequestException as e:
        # Handle network errors or bad responses
        print(f"An error occurred while calling the FastAPI endpoint: {e}")
        # You might want to retry the task or handle the failure in another way
        raise
