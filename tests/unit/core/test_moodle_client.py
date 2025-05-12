import pytest
import requests
from unittest.mock import patch, MagicMock
from urllib.parse import urljoin
from pathlib import Path  # Added Path import

from src.entrenai.core.moodle_client import MoodleClient, MoodleAPIError, MoodleCourse
from src.entrenai.config import MoodleConfig


@pytest.fixture
def mock_moodle_config() -> MoodleConfig:
    config = MagicMock(spec=MoodleConfig)
    config.url = (
        "http://mockmoodle.com/"  # Ensure trailing slash for urljoin consistency
    )
    config.token = "mocktoken"
    config.course_folder_name = "Entrenai Test Folder"
    config.default_teacher_id = 123
    return config


@pytest.fixture
def moodle_client_with_mock_session(
    mock_moodle_config: MoodleConfig,
) -> tuple[MoodleClient, MagicMock]:
    with patch("requests.Session") as MockSession:
        mock_session_instance = MockSession.return_value
        mock_session_instance.params = {}
        client = MoodleClient(config=mock_moodle_config, session=mock_session_instance)
        return client, mock_session_instance


def test_moodle_client_initialization(
    moodle_client_with_mock_session: tuple[MoodleClient, MagicMock],
    mock_moodle_config: MoodleConfig,
):
    client, mock_session = moodle_client_with_mock_session
    assert client.config == mock_moodle_config
    assert client.session == mock_session
    # MoodleClient's __init__ now constructs self.base_url to be the full webservice URL
    assert mock_moodle_config.url is not None  # Ensure url is not None for Pylance
    expected_ws_url = urljoin(mock_moodle_config.url, "webservice/rest/server.php")
    assert client.base_url == expected_ws_url  # Check against client.base_url
    if client.config.token:  # Params are only set if token exists
        assert mock_session.params["wstoken"] == mock_moodle_config.token
        assert mock_session.params["moodlewsrestformat"] == "json"


def test_format_moodle_params_simple(
    moodle_client_with_mock_session: tuple[MoodleClient, MagicMock],
):
    client, _ = moodle_client_with_mock_session
    params = {"key1": "value1", "key2": 123}
    formatted = client._format_moodle_params(params)
    assert formatted["key1"] == "value1"
    assert formatted["key2"] == 123


def test_format_moodle_params_list_of_dicts(
    moodle_client_with_mock_session: tuple[MoodleClient, MagicMock],
):
    client, _ = moodle_client_with_mock_session
    params = {
        "options": [
            {"name": "opt1", "value": "val1"},
            {"name": "opt2", "value": "val2"},
        ]
    }
    formatted = client._format_moodle_params(params)
    assert formatted["options[0][name]"] == "opt1"
    assert formatted["options[0][value]"] == "val1"
    assert formatted["options[1][name]"] == "opt2"
    assert formatted["options[1][value]"] == "val2"


def test_make_request_success_post(
    moodle_client_with_mock_session: tuple[MoodleClient, MagicMock],
):
    client, mock_session = moodle_client_with_mock_session
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"data": "success"}
    mock_session.post.return_value = mock_response

    response = client._make_request("test_wsfunction", {"param": "value"})
    assert response == {"data": "success"}

    expected_query_params = {
        "wstoken": client.config.token,
        "moodlewsrestformat": "json",
        "wsfunction": "test_wsfunction",
    }
    expected_data_payload = client._format_moodle_params({"param": "value"})
    mock_session.post.assert_called_once_with(
        client.base_url, params=expected_query_params, data=expected_data_payload
    )


def test_make_request_http_error(
    moodle_client_with_mock_session: tuple[MoodleClient, MagicMock],
):
    client, mock_session = moodle_client_with_mock_session
    mock_response = MagicMock()
    mock_response.status_code = 400
    mock_response.json.return_value = {
        "errorcode": "badrequest",
        "message": "Bad request",
    }
    # Simulate the actual request object for the error message
    mock_request = MagicMock()
    mock_request.url = client.base_url
    mock_response.request = mock_request
    mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError(
        "Client Error", response=mock_response
    )
    mock_session.post.return_value = mock_response

    with pytest.raises(MoodleAPIError, match="HTTP error: 400"):
        client._make_request("test_wsfunction", {"param": "value"})


def test_make_request_moodle_error_in_response(
    moodle_client_with_mock_session: tuple[MoodleClient, MagicMock],
):
    client, mock_session = moodle_client_with_mock_session
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "exception": "moodle_exception",
        "errorcode": "somecode",
        "message": "Moodle error message",
    }
    mock_session.post.return_value = mock_response

    with pytest.raises(MoodleAPIError, match="Moodle error message"):
        client._make_request("test_wsfunction", {"param": "value"})


@patch.object(MoodleClient, "_make_request")
def test_get_courses_by_user_success(
    mock_make_request, mock_moodle_config: MoodleConfig
):
    client = MoodleClient(config=mock_moodle_config)
    mock_response_data = [
        {
            "id": 1,
            "fullname": "Course 1",
            "shortname": "C1",
            "displayname": "Course 1 Display",
        },
        {
            "id": 2,
            "fullname": "Course 2",
            "shortname": "C2",
            "displayname": "Course 2 Display",
        },
    ]
    mock_make_request.return_value = mock_response_data

    courses = client.get_courses_by_user(user_id=123)
    assert len(courses) == 2
    assert isinstance(courses[0], MoodleCourse)
    assert courses[0].fullname == "Course 1"
    mock_make_request.assert_called_once_with(
        "core_enrol_get_users_courses", payload_params={"userid": 123}
    )


@patch.object(MoodleClient, "_make_request", side_effect=MoodleAPIError("API Down"))
def test_get_courses_by_user_api_error(
    mock_make_request_error, mock_moodle_config: MoodleConfig
):
    client = MoodleClient(config=mock_moodle_config)
    with pytest.raises(MoodleAPIError, match="API Down"):
        client.get_courses_by_user(user_id=123)


@patch.object(MoodleClient, "_make_request")
def test_create_course_section_success(
    mock_make_request, mock_moodle_config: MoodleConfig
):
    client = MoodleClient(config=mock_moodle_config)

    # Mock response for local_wsmanagesections_create_sections
    mock_create_response = [{"id": 10, "name": "Topic 1", "section": 1}]
    # Mock response for local_wsmanagesections_update_sections (often empty or just status)
    mock_update_response = []  # Or some success indicator if API provides one
    # Mock response for local_wsmanagesections_get_sections
    mock_get_response = [
        {
            "id": 10,
            "name": "New Section Name",
            "section": 1,
            "visible": 1,
            "summary": "",
        }
    ]

    mock_make_request.side_effect = [
        mock_create_response,
        mock_update_response,
        mock_get_response,
    ]

    section = client.create_course_section(
        course_id=1, section_name="New Section Name", position=1
    )
    assert section is not None
    assert section.id == 10
    assert section.name == "New Section Name"

    assert mock_make_request.call_count == 3

    # Call 1: create_sections
    call_args_create = mock_make_request.call_args_list[0]
    assert call_args_create[0][0] == "local_wsmanagesections_create_sections"
    assert call_args_create[1]["payload_params"] == {
        "courseid": 1,
        "position": 1,
        "number": 1,
    }

    # Call 2: update_sections
    call_args_update = mock_make_request.call_args_list[1]
    assert call_args_update[0][0] == "local_wsmanagesections_update_sections"
    assert call_args_update[1]["payload_params"] == {
        "courseid": 1,
        "sections": [{"id": 10, "name": "New Section Name", "visible": 1}],
    }

    # Call 3: get_sections
    call_args_get = mock_make_request.call_args_list[2]
    assert call_args_get[0][0] == "local_wsmanagesections_get_sections"
    assert call_args_get[1]["payload_params"] == {"courseid": 1, "sectionids": [10]}


@patch("requests.get")  # Patch the global requests.get for download_file
def test_download_file_success(
    mock_requests_get, mock_moodle_config: MoodleConfig, tmp_path: Path
):
    # We don't use moodle_client_with_mock_session here because download_file uses requests.get directly
    client = MoodleClient(config=mock_moodle_config)

    file_url_str = "http://mockmoodle.com/pluginfile.php/123/mod_folder/content/0/testfile.pdf?forcedownload=1"
    file_content = b"dummy pdf content"
    filename = "testfile.pdf"
    download_dir = tmp_path

    mock_download_response = MagicMock()
    mock_download_response.status_code = 200
    mock_download_response.iter_content.return_value = [file_content]
    mock_download_response.headers = {"Content-Type": "application/pdf"}
    # Simulate the 'raw' attribute for shutil.copyfileobj
    mock_download_response.raw = MagicMock()
    mock_download_response.raw.read.side_effect = [
        file_content,
        b"",
    ]  # Simulate reading content then EOF

    mock_requests_get.return_value.__enter__.return_value = (
        mock_download_response  # For 'with requests.get(...) as r:'
    )

    downloaded_path = client.download_file(
        file_url_str, download_dir, filename
    )  # Pass string URL

    assert downloaded_path.exists()
    assert downloaded_path.read_bytes() == file_content

    expected_download_params = (
        {"wstoken": client.config.token} if "wstoken" not in file_url_str else None
    )
    mock_requests_get.assert_called_once_with(
        file_url_str, params=expected_download_params, stream=True
    )
