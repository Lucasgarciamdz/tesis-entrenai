import pytest
from fastapi.testclient import TestClient
from httpx import Response # For type hinting response if needed
from unittest.mock import patch # Added for mocking config

# Adjust the import path to your FastAPI application instance
# Assuming your FastAPI app instance is named 'app' in 'src.entrenai.api.main'
from src.entrenai.api.main import app 
from src.entrenai.core.models import MoodleCourse # For response validation
from src.entrenai.config import moodle_config # To check if default teacher ID is set

# Fixture for the TestClient
@pytest.fixture(scope="module")
def test_app_client() -> TestClient:
    """
    Provides a TestClient instance for the FastAPI application.
    Scope is 'module' to create it once per test module.
    """
    client = TestClient(app)
    return client

# Basic integration test for the /health endpoint (good starting point)
def test_health_check(test_app_client: TestClient):
    response = test_app_client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}

# --- Tests for /api/v1/courses endpoint ---

def test_list_moodle_courses_default_teacher_id(test_app_client: TestClient):
    """
    Test GET /api/v1/courses using the default teacher ID from config.
    Assumes MOODLE_DEFAULT_TEACHER_ID is set in .env and corresponds to a valid teacher
    in the Dockerized Moodle instance with at least one course.
    """
    if not moodle_config.default_teacher_id:
        pytest.skip("MOODLE_DEFAULT_TEACHER_ID not set in .env, skipping this test.")

    response = test_app_client.get("/api/v1/courses")
    
    assert response.status_code == 200
    response_data = response.json()
    assert isinstance(response_data, list)
    
    # If you know specific courses should be returned for the default teacher, assert them.
    # For now, just check structure if list is not empty.
    if response_data:
        for course_data in response_data:
            # Validate structure using Pydantic model (will raise error if invalid)
            MoodleCourse(**course_data) 
            assert "id" in course_data
            assert "fullname" in course_data
            assert "shortname" in course_data
    else:
        # This is a valid response if the teacher has no courses.
        # You might want to log a warning or ensure your test Moodle setup has courses.
        print(f"Warning: No courses returned for default teacher ID ({moodle_config.default_teacher_id}). Ensure test Moodle has courses for this user.")

def test_list_moodle_courses_with_specific_teacher_id(test_app_client: TestClient):
    """
    Test GET /api/v1/courses with a specific teacher ID.
    Requires knowing a valid teacher ID and their courses in the Dockerized Moodle.
    For this example, we'll use the default_teacher_id if available, or skip.
    In a real scenario, you might have a dedicated test teacher ID.
    """
    teacher_id_to_test = moodle_config.default_teacher_id 
    # Or replace with a known test teacher ID from your Moodle setup, e.g., 2 (often admin)
    
    if not teacher_id_to_test:
        pytest.skip("No teacher ID available for testing (MOODLE_DEFAULT_TEACHER_ID not set).")

    response = test_app_client.get(f"/api/v1/courses?moodle_user_id={teacher_id_to_test}")
    
    assert response.status_code == 200
    response_data = response.json()
    assert isinstance(response_data, list)
    if response_data:
        for course_data in response_data:
            MoodleCourse(**course_data)

def test_list_moodle_courses_invalid_teacher_id(test_app_client: TestClient):
    """
    Test GET /api/v1/courses with an invalid/non-existent teacher ID.
    Moodle API might return an empty list or an error depending on its configuration.
    core_enrol_get_users_courses usually returns empty list for non-existent user.
    """
    invalid_teacher_id = 9999999 # Assuming this ID does not exist
    response = test_app_client.get(f"/api/v1/courses?moodle_user_id={invalid_teacher_id}")
    
    assert response.status_code == 200 # Moodle API itself might not error, just return empty
    response_data = response.json()
    assert isinstance(response_data, list)
    assert len(response_data) == 0 # Expect empty list for a non-existent user

def test_list_moodle_courses_no_teacher_id_and_no_default(test_app_client: TestClient):
    """
    Test GET /api/v1/courses when no teacher_id is provided and 
    MOODLE_DEFAULT_TEACHER_ID is not configured (or mocked as None).
    This should result in a 400 Bad Request.
    """
    # Temporarily mock moodle_config.default_teacher_id to be None for this test
    with patch('src.entrenai.api.routers.course_setup.moodle_config') as mock_cfg:
        mock_cfg.default_teacher_id = None
        
        response = test_app_client.get("/api/v1/courses")
        assert response.status_code == 400
        assert "Moodle teacher ID must be provided" in response.json().get("detail", "")

# Placeholder for POST /courses/{course_id}/setup-ia tests
# These will be more complex as they interact with Moodle, Qdrant, N8N.
# They will require a Moodle course to exist and services to be running.

# @pytest.mark.integration # Optional: mark as integration test
# def test_setup_ia_for_course_success(test_app_client: TestClient):
#     # 1. Ensure a course exists in your test Moodle (e.g., course_id = 2 if it's the demo course)
#     #    This might involve a setup fixture or manual setup.
#     test_course_id = 2 # Example: Assuming Moodle's "My first course" or similar
    
#     # 2. Ensure dependent services (Qdrant, N8N, Ollama) are running and configured in .env
    
#     response = test_app_client.post(f"/api/v1/courses/{test_course_id}/setup-ia")
    
#     assert response.status_code == 200 # Or 201 Created, depending on API design
#     response_data = response.json()
#     assert response_data["status"] == "success"
#     assert response_data["course_id"] == test_course_id
#     assert response_data["qdrant_collection_name"] == f"test_course_{test_course_id}" # Assuming prefix
#     assert response_data["moodle_section_id"] is not None
#     # Further assertions: check Moodle for section/folder/links, Qdrant for collection, N8N for workflow (harder)

# Placeholder for GET /courses/{course_id}/refresh-files tests
# These are also complex and depend on prior setup and file uploads.
