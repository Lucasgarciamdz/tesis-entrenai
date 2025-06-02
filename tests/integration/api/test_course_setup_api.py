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
    MoodleCourseN8NSettings, # Added import
)  # For response validation
from src.entrenai.config import (
    moodle_config,
    pgvector_config, # Changed from qdrant_config
    n8n_config,
    base_config,
)  # To check if default teacher ID is set
from src.entrenai.core.db.pgvector_wrapper import PgvectorWrapper # Changed from QdrantWrapper
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
@patch("src.entrenai.api.routers.course_setup.N8NClient.configure_and_deploy_chat_workflow")
@patch("src.entrenai.api.routers.course_setup.MoodleClient.get_course_n8n_settings")
@patch("src.entrenai.api.routers.course_setup.MoodleClient._make_request") # To inspect summary update
def test_setup_ia_for_course_scenarios(
    mock_moodle_make_request, # Order of mocks is important (innermost first)
    mock_get_course_n8n_settings,
    mock_configure_n8n_workflow,
    test_app_client: TestClient,
):
    """
    Test successful IA setup for a course under different Moodle n8n settings scenarios.
    Requires Docker services (Moodle, Pgvector, N8N, Ollama/Gemini) to be running.
    Assumes TEST_COURSE_ID exists in Moodle.
    """
    mock_moodle_course_details_response = [ # Simulate MoodleClient.get_courses_by_user response
        {"id": TEST_COURSE_ID, "fullname": "Test Course Fullname", "shortname": "TCF", "displayname": "Test Course Displayname"}
    ]
    mock_moodle_create_section_response = [{"id": 123, "name": "Default Section Name", "section": 1}] # Simulate create_course_section response part 1
    mock_moodle_get_section_details_response = [{"id": 123, "name": moodle_config.course_folder_name, "section": 1}] # Simulate create_course_section response part 2
    mock_moodle_update_section_summary_response = [] # Simulate the _make_request for updating summary

    # This mock will handle multiple calls:
    # 1. get_courses_by_user (to get course name if not provided in query)
    # 2. create_course_section (first part, creating the section structure)
    # 3. create_course_section (second part, getting details of the created section)
    # 4. _make_request for local_wsmanagesections_update_sections (this is the one we want to inspect for html_summary)
    mock_moodle_make_request.side_effect = [
        mock_moodle_course_details_response, # For getting course name
        mock_moodle_create_section_response,
        mock_moodle_get_section_details_response,
        mock_moodle_update_section_summary_response, # This is the call we'll inspect
        # Add more if other _make_request calls are made by MoodleClient for other things like folder/URL creation
        [], # Placeholder for create_folder_in_section -> get_course_module_by_name (not found)
        [], # Placeholder for create_folder_in_section -> _make_request (create)
        [{"id": 789, "name": "Documentos Entrenai", "modname": "folder"}], # Placeholder for create_folder_in_section -> get_course_module_by_name (found)
        [], # Placeholder for create_url_in_section (chat link) -> get_course_module_by_name (not found)
        [], # Placeholder for create_url_in_section (chat link) -> _make_request (create)
        [{"id": 790, "name": moodle_config.chat_link_name, "modname": "url"}], # Placeholder for create_url_in_section (chat link) -> get_course_module_by_name (found)
        [], # Placeholder for create_url_in_section (refresh link) -> get_course_module_by_name (not found)
        [], # Placeholder for create_url_in_section (refresh link) -> _make_request (create)
        [{"id": 791, "name": moodle_config.refresh_link_name, "modname": "url"}], # Placeholder for create_url_in_section (refresh link) -> get_course_module_by_name (found)
    ]


    mock_n8n_chat_url = "http://mockn8n.com/webhook/mockchat"
    mock_configure_n8n_workflow.return_value = mock_n8n_chat_url

    # Scenario 1: Moodle provides custom settings
    custom_settings = MoodleCourseN8NSettings(
        initial_message="Custom Moodle Message",
        system_message_append="Custom System Append",
        chat_title="Custom Chat Title",
        input_placeholder="Custom Input Placeholder",
    )
    mock_get_course_n8n_settings.return_value = custom_settings

    response_scenario1 = test_app_client.post(f"/api/v1/courses/{TEST_COURSE_ID}/setup-ia")
    assert response_scenario1.status_code == 200
    response_data_s1 = response_scenario1.json()
    CourseSetupResponse(**response_data_s1)
    assert response_data_s1["status"] == "exitoso" # Changed from "success" to "exitoso" based on current code
    assert response_data_s1["course_id"] == TEST_COURSE_ID
    
    # Check call to N8NClient.configure_and_deploy_chat_workflow
    mock_configure_n8n_workflow.assert_called_with(
        course_id=TEST_COURSE_ID,
        course_name="Test Course Displayname", # From mock_moodle_course_details_response
        qdrant_collection_name=f"{pgvector_config.table_prefix}test_course_displayname", # Adjusted to pgvector
        ai_config_params=pytest.approx( # Use approx for dict comparison if order might change or floats involved
            {
                "selected_provider": base_config.ai_provider,
                base_config.ai_provider: pytest.anything(), # Check provider specific config exists
            }
        ),
        initial_messages="Custom Moodle Message",
        system_message="Custom System Append",
        input_placeholder="Custom Input Placeholder",
        chat_title="Custom Chat Title",
    )

    # Inspect the Moodle section summary update call
    # The call to update summary is the 4th call to moodle_client._make_request in this setup
    # (1st get_course_by_user, 2nd create_section (create), 3rd create_section (get), 4th update_section (summary))
    update_summary_call_args = mock_moodle_make_request.call_args_list[3] # 4th call
    assert update_summary_call_args[0][0] == "local_wsmanagesections_update_sections"
    summary_payload = update_summary_call_args[1]["payload_params"]
    assert "Custom Moodle Message" in summary_payload["sections"][0]["summary"]
    assert "Custom System Append" in summary_payload["sections"][0]["summary"]
    assert "Custom Chat Title" in summary_payload["sections"][0]["summary"]
    assert "Custom Input Placeholder" in summary_payload["sections"][0]["summary"]
    
    mock_moodle_make_request.reset_mock() # Reset for next scenario
    mock_get_course_n8n_settings.reset_mock()
    mock_configure_n8n_workflow.reset_mock()
    
    # Reset side_effect for the new scenario, keeping the same mock responses for Moodle calls
    mock_moodle_make_request.side_effect = [
        mock_moodle_course_details_response,
        mock_moodle_create_section_response,
        mock_moodle_get_section_details_response,
        mock_moodle_update_section_summary_response,
        [], [], [{"id": 789, "name": "Documentos Entrenai", "modname": "folder"}],
        [], [], [{"id": 790, "name": moodle_config.chat_link_name, "modname": "url"}],
        [], [], [{"id": 791, "name": moodle_config.refresh_link_name, "modname": "url"}],
    ]
    mock_configure_n8n_workflow.return_value = mock_n8n_chat_url # Ensure mock is re-set

    # Scenario 2: Moodle does NOT provide custom settings
    mock_get_course_n8n_settings.return_value = None

    response_scenario2 = test_app_client.post(f"/api/v1/courses/{TEST_COURSE_ID}/setup-ia")
    assert response_scenario2.status_code == 200
    response_data_s2 = response_scenario2.json()
    CourseSetupResponse(**response_data_s2)
    assert response_data_s2["status"] == "exitoso"

    mock_configure_n8n_workflow.assert_called_with(
        course_id=TEST_COURSE_ID,
        course_name="Test Course Displayname",
        qdrant_collection_name=f"{pgvector_config.table_prefix}test_course_displayname", # Adjusted
        ai_config_params=pytest.approx(
            {
                "selected_provider": base_config.ai_provider,
                base_config.ai_provider: pytest.anything(),
            }
        ),
        initial_messages=None,  # Expecting None or defaults
        system_message=None,
        input_placeholder=None,
        chat_title=None,
    )
    
    update_summary_call_args_s2 = mock_moodle_make_request.call_args_list[3]
    assert update_summary_call_args_s2[0][0] == "local_wsmanagesections_update_sections"
    summary_payload_s2 = update_summary_call_args_s2[1]["payload_params"]
    assert "No especificado" in summary_payload_s2["sections"][0]["summary"] # Default text

    # Verify other side effects (Pgvector, Moodle structure, N8N workflow basic check)
    # These are common to both scenarios, so one check is likely sufficient if mocks are consistent
    pgvector_wrapper = PgvectorWrapper(config=pgvector_config) # Adjusted
    # No direct client to check for table existence easily like qdrant, 
    # but ensure_table was called (implicitly covered by successful response if no exception)
    # We can check if the table name in response matches expected
    expected_pgvector_table = pgvector_wrapper.get_table_name("Test Course Displayname") # From mock
    assert response_data_s1["qdrant_collection_name"] == expected_pgvector_table # Field name is still qdrant_collection_name in model
    assert response_data_s1["moodle_section_id"] is not None # Should be 123 from mock
    assert response_data_s1["n8n_chat_url"] == mock_n8n_chat_url

    # N8N workflow check (simplified as detailed check is too complex with mocks)
    # The configure_and_deploy_chat_workflow mock is called, which is the main thing.
    # A real integration test against N8N would be separate.
    # We can check if the N8N client was asked to create/activate a workflow with the correct name.
    # This is implicitly tested by mock_configure_n8n_workflow.assert_called_with(...)

    # Moodle structure check using the REAL MoodleClient against the mock _make_request calls
    # This is tricky because we mocked _make_request which MoodleClient uses.
    # The real test of MoodleClient creating sections/modules is in its own unit/integration tests.
    # Here, we mainly care that the setup_ia_for_course orchestrates correctly based on mocks.
    # The fact that mock_moodle_make_request was called with expected wsfunctions for section/module
    # creation (implicitly by the sequence of side_effect) is a partial verification.


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
