import logging
import os
import httpx # Using httpx for potential async requests in future, and it's a modern choice.
              # Ensure httpx is in requirements.txt

from src.entrenai.celery_app import app # Import the Celery app instance
# We'll need the FileProcessingRequest model to structure the data for the API call,
# and MoodleFile if it's part of the task arguments.
from src.entrenai.api.models import FileProcessingRequest, MoodleFile

logger = logging.getLogger(__name__)

# Determine the Fastapi backend URL from environment variables
# Default to a common local setup if not specified.
FASTAPI_BACKEND_URL = os.getenv("FASTAPI_BACKEND_URL", "http://fastapi_backend:8000")

@app.task(bind=True, name="entrenai.core.tasks.process_moodle_file_task")
def forward_file_processing_to_api(
    self,  # Bound task instance
    course_id: int,
    course_name_for_pgvector: str,
    moodle_file_info: dict,  # Expected to be a dict, will be converted to MoodleFile model
    download_dir_str: str,
    ai_provider_config: dict,
    pgvector_config_dict: dict,
    moodle_config_dict: dict,
    base_config_dict: dict,
):
    """
    Celery task that forwards file processing to the Fastapi backend via an HTTP request.
    It attempts to maintain the original task name 'entrenai.core.tasks.process_moodle_file_task'.
    """
    task_id = self.request.id
    filename = moodle_file_info.get("filename", "unknown_file")
    logger.info(
        f"Task ID: {task_id} - Received task to process file: {filename} for course_id: {course_id}. Forwarding to API."
    )

    # Reconstruct MoodleFile from the input dict to ensure structure
    try:
        moodle_file_model = MoodleFile(**moodle_file_info)
    except Exception as e:
        logger.error(f"Task ID: {task_id} - Error converting moodle_file_info dict to MoodleFile model for {filename}: {e}")
        return {
            "filename": filename,
            "status": "error",
            "error_message": f"Invalid moodle_file_info structure: {e}",
            "task_id": task_id,
        }

    # Prepare the request payload for the Fastapi API endpoint
    payload = FileProcessingRequest(
        course_id=course_id,
        course_name_for_pgvector=course_name_for_pgvector,
        moodle_file_info=moodle_file_model,
        download_dir_str=download_dir_str,
        ai_provider_config=ai_provider_config,
        pgvector_config_dict=pgvector_config_dict,
        moodle_config_dict=moodle_config_dict,
        base_config_dict=base_config_dict,
    )

    api_endpoint = f"{FASTAPI_BACKEND_URL}/processing/process_file"
    logger.info(f"Task ID: {task_id} - Posting to API endpoint: {api_endpoint} with payload for {filename}")

    try:
        # Using httpx.Client for synchronous request from Celery task
        with httpx.Client(timeout=None) as client: # Consider a reasonable timeout, e.g. 300 seconds for long processing
            response = client.post(api_endpoint, json=payload.model_dump(mode='json')) # Use mode='json' to serialize HttpUrl objects properly

        logger.info(f"Task ID: {task_id} - Received response from API for {filename}: {response.status_code}")
        response.raise_for_status()  # Raises an HTTPError for bad responses (4xx or 5xx)

        api_response_data = response.json()
        logger.info(f"Task ID: {task_id} - API processing for {filename} successful: {api_response_data}")

        return {
            "filename": api_response_data.get("filename", filename),
            "status": api_response_data.get("status", "success_from_api"),
            "message": api_response_data.get("message"),
            "chunks_upserted": api_response_data.get("chunks_upserted"),
            "task_id": task_id,
        }

    except httpx.HTTPStatusError as e:
        error_message = f"API request failed for {filename} with status {e.response.status_code}: {e.response.text}"
        logger.error(f"Task ID: {task_id} - {error_message}", exc_info=True)
        return {
            "filename": filename,
            "status": "error",
            "error_message": error_message,
            "task_id": task_id,
        }
    except httpx.RequestError as e:
        error_message = f"API request failed for {filename} due to a network or connection error: {e}"
        logger.error(f"Task ID: {task_id} - {error_message}", exc_info=True)
        return {
            "filename": filename,
            "status": "error",
            "error_message": error_message,
            "task_id": task_id,
        }
    except Exception as e:
        error_message = f"An unexpected error occurred in task {task_id} for file {filename} when calling API: {e}"
        logger.error(f"Task ID: {task_id} - {error_message}", exc_info=True)
        return {
            "filename": filename,
            "status": "error",
            "error_message": error_message,
            "task_id": task_id,
        }
