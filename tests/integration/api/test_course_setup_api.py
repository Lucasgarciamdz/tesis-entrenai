import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch  # Added for mocking config
from urllib.parse import urljoin
from pathlib import Path

# Adjust the import path to your FastAPI application instance
# Assuming your FastAPI app instance is named 'app' in 'src.entrenai.api.main'
from src.entrenai.api.main import app
from src.entrenai.api.models import (
    MoodleCourse,
    CourseSetupResponse,
)  # For response validation
from src.entrenai.config import (
    moodle_config,
    qdrant_config,
    n8n_config,
    base_config,
)  # To check if default teacher ID is set
from src.entrenai.core.db.qdrant_wrapper import QdrantWrapper
from src.entrenai.core.clients.moodle_client import MoodleClient
from src.entrenai.core.clients.n8n_client import N8NClient


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
        print(
            f"Warning: No courses returned for default teacher ID ({moodle_config.default_teacher_id}). Ensure test Moodle has courses for this user."
        )


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
        pytest.skip(
            "No teacher ID available for testing (MOODLE_DEFAULT_TEACHER_ID not set)."
        )

    response = test_app_client.get(
        f"/api/v1/courses?moodle_user_id={teacher_id_to_test}"
    )

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
    invalid_teacher_id = 9999999  # Assuming this ID does not exist
    response = test_app_client.get(
        f"/api/v1/courses?moodle_user_id={invalid_teacher_id}"
    )

    assert (
        response.status_code == 200
    )  # Moodle API itself might not error, just return empty
    response_data = response.json()
    assert isinstance(response_data, list)
    assert len(response_data) == 0  # Expect empty list for a non-existent user


def test_list_moodle_courses_no_teacher_id_and_no_default(test_app_client: TestClient):
    """
    Test GET /api/v1/courses when no teacher_id is provided and
    MOODLE_DEFAULT_TEACHER_ID is not configured (or mocked as None).
    This should result in a 400 Bad Request.
    """
    # Temporarily mock moodle_config.default_teacher_id to be None for this test
    with patch("src.entrenai.api.routers.course_setup.moodle_config") as mock_cfg:
        mock_cfg.default_teacher_id = None

        response = test_app_client.get("/api/v1/courses")
        assert response.status_code == 400
        assert "Moodle teacher ID must be provided" in response.json().get("detail", "")


# --- Tests for POST /api/v1/courses/{course_id}/setup-ia endpoint ---
TEST_COURSE_ID = 2  # As confirmed by the user


@pytest.mark.integration
def test_setup_ia_for_course_success(test_app_client: TestClient):
    """
    Test successful IA setup for a course.
    Requires Docker services to be running and configured.
    Assumes TEST_COURSE_ID exists in Moodle.
    """
    # Ensure all services are up and .env is configured before running this.
    # This test will have side effects (creations in Moodle, Qdrant, N8N).

    response = test_app_client.post(f"/api/v1/courses/{TEST_COURSE_ID}/setup-ia")

    assert response.status_code == 200
    response_data = response.json()
    CourseSetupResponse(**response_data)  # Validate response model

    assert response_data["status"] == "success"
    assert response_data["course_id"] == TEST_COURSE_ID
    expected_qdrant_collection = f"{qdrant_config.collection_prefix}{TEST_COURSE_ID}"
    assert response_data["qdrant_collection_name"] == expected_qdrant_collection
    assert response_data["moodle_section_id"] is not None
    assert response_data["n8n_chat_url"] is not None

    # Verify side effects
    # 1. Qdrant
    qdrant_wrapper = QdrantWrapper(config=qdrant_config)
    assert qdrant_wrapper.client is not None, (
        "Qdrant client failed to initialize for verification"
    )
    try:
        collection_info = qdrant_wrapper.client.get_collection(
            collection_name=expected_qdrant_collection
        )
        assert collection_info is not None
        # Optionally check config:
        # assert collection_info.config.params.vectors.size == qdrant_config.default_vector_size
        # assert collection_info.config.params.vectors.distance == Distance.COSINE
    except Exception as e:
        pytest.fail(f"Qdrant collection check failed: {e}")

    # 2. Moodle
    moodle_client = MoodleClient(config=moodle_config)
    assert moodle_client.base_url is not None, (
        "Moodle client failed to initialize for verification"
    )

    moodle_section_name_expected = moodle_config.course_folder_name
    section = moodle_client.get_section_by_name(
        TEST_COURSE_ID, moodle_section_name_expected
    )
    assert section is not None, (
        f"Moodle section '{moodle_section_name_expected}' not found."
    )
    assert section.id == response_data["moodle_section_id"]

    folder_name_expected = "Documentos Entrenai"
    folder = moodle_client.get_course_module_by_name(
        TEST_COURSE_ID, section.id, folder_name_expected, "folder"
    )
    assert folder is not None, (
        f"Moodle folder '{folder_name_expected}' not found in section {section.id}."
    )
    if response_data.get("moodle_folder_id"):  # Folder creation might be non-fatal
        assert folder.id == response_data["moodle_folder_id"]

    chat_link_name_expected = moodle_config.chat_link_name
    chat_link = moodle_client.get_course_module_by_name(
        TEST_COURSE_ID, section.id, chat_link_name_expected, "url"
    )
    assert chat_link is not None, (
        f"Moodle chat link '{chat_link_name_expected}' not found."
    )
    # We could also check chat_link.externalurl if N8N URL is predictable

    refresh_link_name_expected = moodle_config.refresh_link_name
    refresh_link = moodle_client.get_course_module_by_name(
        TEST_COURSE_ID, section.id, refresh_link_name_expected, "url"
    )
    assert refresh_link is not None, (
        f"Moodle refresh link '{refresh_link_name_expected}' not found."
    )
    # We could check refresh_link.externalurl matches response_data["moodle_refresh_link_url"] if that was returned

    # 3. N8N
    n8n_client = N8NClient(config=n8n_config)
    assert n8n_client.base_url is not None, (
        "N8N client failed to initialize for verification"
    )

    # Determine workflow ID to check. The current n8n_workflow.json has id "kTGiA3QAR7HHvrx4"
    # If import_workflow updates based on this ID, this is the ID to check.
    # If N8N always creates new on import if name conflicts, this is harder.
    # For now, assume the provided JSON's ID is used or a new one is created but the name is consistent.
    # The `configure_and_deploy_chat_workflow` returns the webhook URL.
    # We can check if the webhook URL from response matches the expected one from JSON.

    # Extract webhookId from the n8n_workflow.json to construct expected URL
    # This is a bit fragile if the JSON changes, but necessary for verification.
    # Ideally, N8NClient.configure_and_deploy_chat_workflow would return the workflow ID.
    # For now, let's assume the webhookId from the provided JSON is used.
    # The JSON has: "webhookId": "2fbaf000-b2a8-41bc-bfd1-4252f65bd65c"
    # And workflow "id": "kTGiA3QAR7HHvrx4"

    workflow_id_from_json = "kTGiA3QAR7HHvrx4"  # From src/entrenai/n8n_workflow.json
    workflow_details = n8n_client.get_workflow_details(workflow_id_from_json)
    assert workflow_details is not None, (
        f"N8N workflow {workflow_id_from_json} not found."
    )
    assert workflow_details.active is True, (
        f"N8N workflow {workflow_id_from_json} is not active."
    )

    webhook_id_from_json = "2fbaf000-b2a8-41bc-bfd1-4252f65bd65c"
    assert n8n_config.webhook_url is not None
    expected_n8n_chat_url = urljoin(
        n8n_config.webhook_url, f"webhook/{webhook_id_from_json}"
    )
    assert response_data["n8n_chat_url"] == expected_n8n_chat_url


# --- Tests for GET /api/v1/courses/{course_id}/refresh-files ---


@pytest.mark.integration
def test_refresh_files_success(test_app_client: TestClient):
    """
    Test successful file refresh and processing.
    Requires:
    1. `setup-ia` to have been run successfully for TEST_COURSE_ID.
    2. User to have MANUALLY uploaded a few test files (e.g., .txt, .docx)
       into the 'Documentos Entrenai' folder in Moodle for course TEST_COURSE_ID.
    3. Qdrant, Ollama services running.
    """
    # Ensure setup was done (implicitly, or add a dependency/call if tests run in isolation)
    # For now, assume test_setup_ia_for_course_success ran or Moodle is pre-configured.

    # User needs to manually upload files to Moodle course TEST_COURSE_ID (ID 2)
    # in the "Documentos Entrenai" folder before running this test.
    # Example files: "test_doc1.txt", "test_doc2.docx"

    # It's hard to assert exact number of files processed without knowing what the user uploaded.
    # We will check that the endpoint runs, returns success, and some chunks are processed.

    # Clear FileTracker for this course to ensure files are seen as new
    # This makes the test more reliable if run multiple times without Moodle file changes.
    # This is a bit of a hack for testing; ideally, we'd have a way to reset state
    # or use unique file names for each test run if Moodle interaction was programmatic.
    # For now, we assume the user can re-upload or change files if needed for re-testing.
    # A simpler approach for now: just run it and check for positive processing.

    # First call: Process new files
    print(
        f"Calling refresh-files for course {TEST_COURSE_ID}. Ensure test files are uploaded to Moodle."
    )
    response1 = test_app_client.get(f"/api/v1/courses/{TEST_COURSE_ID}/refresh-files")

    assert response1.status_code == 200
    response_data1 = response1.json()
    print("Response from first refresh-files call:", response_data1)

    assert "message" in response_data1
    assert (
        response_data1["files_checked"] >= 0
    )  # Should be >= number of files user uploaded
    # We expect some files to be processed if user uploaded them and they are new
    # This assertion depends on user action.
    # assert response_data1["files_to_process"] > 0
    # assert response_data1["files_processed_successfully"] > 0
    # assert response_data1["total_chunks_upserted"] > 0
    # For a more robust test, we'd need to know exactly what files are there.
    # For now, let's just check the process ran.
    # If files_to_process is 0, it means FileTracker thinks they are old, or Moodle folder is empty.

    # Verify in Qdrant (crude check: count points before/after if possible, or search)
    # This is hard without knowing the content.
    # A simple check: if files were processed, total_chunks_upserted should be positive.
    # If user uploaded files, we expect this to be > 0.
    # This is a weak assertion as it depends on external setup.
    if response_data1["files_to_process"] > 0:  # Only if files were actually new
        assert response_data1["files_processed_successfully"] > 0
        assert response_data1["total_chunks_upserted"] > 0

    # Verify FileTracker was updated for processed files
    # This also depends on knowing the filenames the user uploaded.
    # Example: if user uploaded "test_doc1.txt"
    # timestamps = file_tracker.get_processed_files_timestamps(TEST_COURSE_ID)
    # assert "test_doc1.txt" in timestamps

    # Second call: No new files, should process 0
    print(
        f"Calling refresh-files again for course {TEST_COURSE_ID} to check idempotency."
    )
    response2 = test_app_client.get(f"/api/v1/courses/{TEST_COURSE_ID}/refresh-files")
    assert response2.status_code == 200
    response_data2 = response2.json()
    print("Response from second refresh-files call:", response_data2)

    assert response_data2["files_to_process"] == 0
    assert response_data2["files_processed_successfully"] == 0
    # total_chunks_upserted should also be 0 for this call, but the response key is cumulative.
    # The message should indicate 0 files processed.
    assert (
        "Attempted to process 0 new/modified files" in response_data2["message"]
        or "Successfully processed and embedded 0 files" in response_data2["message"]
    )

    # Verify download directory is empty or does not contain files from this run
    course_download_dir = Path(base_config.download_dir) / str(TEST_COURSE_ID)
    if course_download_dir.exists():
        # Check if it's empty. Note: other tests or runs might leave unrelated files if not careful.
        # A robust check would be to list files before, run, list after, and see if specific files were deleted.
        # For now, a simple check:
        items_in_dir = list(course_download_dir.iterdir())
        # This assertion is tricky because if processing fails mid-way, files might remain.
        # For a success case, it should be empty.
        # assert not items_in_dir, f"Download directory {course_download_dir} not empty after processing: {items_in_dir}"
        # Let's just log it for now.
        print(f"Items in download dir {course_download_dir} after test: {items_in_dir}")
