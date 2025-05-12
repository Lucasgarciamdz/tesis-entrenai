import pytest
import requests
import json
from pathlib import Path
from unittest.mock import patch, MagicMock, mock_open
from urllib.parse import urljoin

from src.entrenai.core.n8n_client import N8NClient, N8NClientError, N8NWorkflow
from src.entrenai.config import N8NConfig, OllamaConfig  # For type hints


@pytest.fixture
def mock_n8n_config() -> N8NConfig:
    config = MagicMock(spec=N8NConfig)
    config.url = "http://mockn8n.com/"  # Ensure trailing slash
    config.api_key = "mock_n8n_api_key"
    config.workflow_json_path = "dummy/path/to/workflow.json"  # Path for tests
    config.webhook_url = (
        "http://mockn8n.com/webhook-base/"  # Base for constructing webhook URLs
    )
    return config


@pytest.fixture
def n8n_client_with_mock_session(
    mock_n8n_config: N8NConfig,
) -> tuple[N8NClient, MagicMock]:
    """Provides an N8NClient instance with a mocked requests.Session."""
    with patch("requests.Session") as MockSession:
        mock_session_instance = MockSession.return_value
        # N8NClient __init__ doesn't make a call by default now
        client = N8NClient(config=mock_n8n_config, session=mock_session_instance)
        return client, mock_session_instance


def test_n8n_client_initialization(
    n8n_client_with_mock_session: tuple[N8NClient, MagicMock],
    mock_n8n_config: N8NConfig,
):
    client, mock_session = n8n_client_with_mock_session
    assert client.config == mock_n8n_config
    assert client.session == mock_session
    assert mock_n8n_config.url is not None  # For Pylance
    expected_base_api_url = urljoin(mock_n8n_config.url, "api/v1/")
    assert client.base_url == expected_base_api_url
    if client.config.api_key:
        assert mock_session.headers["X-N8N-API-KEY"] == mock_n8n_config.api_key


# --- Test _make_request (similar to MoodleClient, adapt if needed) ---
def test_make_request_success_post_n8n(
    n8n_client_with_mock_session: tuple[N8NClient, MagicMock],
):
    client, mock_session = n8n_client_with_mock_session
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"data": "n8n_success"}
    mock_session.post.return_value = mock_response

    response = client._make_request(
        "POST", "test_endpoint", json_data={"param": "value"}
    )
    assert response == {"data": "n8n_success"}
    assert client.base_url is not None  # For Pylance
    mock_session.post.assert_called_once_with(
        urljoin(client.base_url, "test_endpoint"), params=None, json={"param": "value"}
    )


def test_make_request_http_error_n8n(
    n8n_client_with_mock_session: tuple[N8NClient, MagicMock],
):
    client, mock_session = n8n_client_with_mock_session
    mock_response = MagicMock()
    mock_response.status_code = 401
    mock_response.text = "Unauthorized"
    mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError(
        "Client Error - Unauthorized", response=mock_response
    )
    mock_session.post.return_value = mock_response

    with pytest.raises(N8NClientError, match="Client Error - Unauthorized"):
        client._make_request("POST", "test_endpoint", json_data={"param": "value"})


# --- Test import_workflow ---
@patch.object(N8NClient, "_make_request")
def test_import_workflow_success(mock_make_request, mock_n8n_config: N8NConfig):
    client = N8NClient(config=mock_n8n_config)
    workflow_content = {"name": "Test Workflow", "nodes": [], "connections": {}}
    mock_response_data = {
        "id": "wf123",
        "name": "Test Workflow",
        "active": False,
        "nodes": [],
        "connections": {},
        "settings": {},
        "staticData": None,
    }  # N8NWorkflow compatible
    mock_make_request.return_value = mock_response_data

    workflow = client.import_workflow(workflow_content)
    assert workflow is not None
    assert workflow.id == "wf123"
    assert workflow.name == "Test Workflow"
    mock_make_request.assert_called_once_with(
        "POST", "workflows", json_data=workflow_content
    )


@patch.object(N8NClient, "_make_request", side_effect=N8NClientError("Import failed"))
def test_import_workflow_api_error(mock_make_request_error, mock_n8n_config: N8NConfig):
    client = N8NClient(config=mock_n8n_config)
    workflow_content = {"name": "Test Workflow", "nodes": [], "connections": {}}
    assert client.import_workflow(workflow_content) is None


# --- Test activate_workflow ---
@patch.object(N8NClient, "_make_request")
def test_activate_workflow_success(mock_make_request, mock_n8n_config: N8NConfig):
    client = N8NClient(config=mock_n8n_config)
    # _make_request for POST with no content often returns None or empty on success (e.g. 204 or 200 with empty body)
    mock_make_request.return_value = None  # Or {"success": True} depending on N8N API

    assert client.activate_workflow("wf123") is True
    mock_make_request.assert_called_once_with("POST", "workflows/wf123/activate")


@patch.object(
    N8NClient, "_make_request", side_effect=N8NClientError("Activation failed")
)
def test_activate_workflow_api_error(
    mock_make_request_error, mock_n8n_config: N8NConfig
):
    client = N8NClient(config=mock_n8n_config)
    assert client.activate_workflow("wf123") is False


# --- Test _get_webhook_url_from_workflow_json ---
def test_get_webhook_url_from_workflow_json_found(
    n8n_client_with_mock_session: tuple[N8NClient, MagicMock],
):
    client, _ = n8n_client_with_mock_session
    assert (
        client.config.webhook_url is not None
    )  # Ensure it's set for the test for Pylance

    webhook_id = "test-webhook-id-123"
    workflow_json = {
        "nodes": [
            {"type": "some_other_node"},
            {"type": "@n8n/n8n-nodes-langchain.chatTrigger", "webhookId": webhook_id},
        ]
    }
    assert (
        client.config.webhook_url is not None
    )  # Redundant but for clarity with Pylance
    expected_url = urljoin(client.config.webhook_url, f"webhook/{webhook_id}")
    assert client._get_webhook_url_from_workflow_json(workflow_json) == expected_url


def test_get_webhook_url_from_workflow_json_not_found(
    n8n_client_with_mock_session: tuple[N8NClient, MagicMock],
):
    client, _ = n8n_client_with_mock_session
    workflow_json = {"nodes": [{"type": "some_other_node"}]}
    assert client._get_webhook_url_from_workflow_json(workflow_json) is None


# --- Test configure_and_deploy_chat_workflow ---
@patch("builtins.open", new_callable=mock_open)  # Mock open to control file reading
@patch.object(N8NClient, "import_workflow")
@patch.object(N8NClient, "activate_workflow")
@patch.object(N8NClient, "_get_webhook_url_from_workflow_json")
def test_configure_and_deploy_success(
    mock_get_webhook_url,
    mock_activate,
    mock_import,
    mock_file_open,
    mock_n8n_config: N8NConfig,
):
    client = N8NClient(config=mock_n8n_config)

    # Setup mocks
    mock_file_open.return_value.read.return_value = json.dumps(
        {
            "name": "My Workflow",
            "nodes": [
                {"type": "@n8n/n8n-nodes-langchain.chatTrigger", "webhookId": "wh123"}
            ],
        }
    )
    mock_imported_workflow = MagicMock(spec=N8NWorkflow)
    mock_imported_workflow.id = "imported_wf_id"
    mock_imported_workflow.name = "My Workflow"
    mock_imported_workflow.active = False
    mock_import.return_value = mock_imported_workflow
    mock_activate.return_value = True
    mock_get_webhook_url.return_value = "http://mockn8n.com/webhook-base/webhook/wh123"

    # Dummy OllamaConfig for the test call signature
    dummy_ollama_cfg = MagicMock(spec=OllamaConfig)
    dummy_ollama_cfg_params = {
        "host": dummy_ollama_cfg.host,
        "embedding_model": dummy_ollama_cfg.embedding_model,
        "qa_model": dummy_ollama_cfg.qa_model,
    }

    result_url = client.configure_and_deploy_chat_workflow(
        course_id=1,
        qdrant_collection_name="test_coll",
        ollama_config_params=dummy_ollama_cfg_params,
    )

    assert result_url == "http://mockn8n.com/webhook-base/webhook/wh123"
    assert mock_n8n_config.workflow_json_path is not None  # For Pylance with Path()
    mock_file_open.assert_called_once_with(
        Path(mock_n8n_config.workflow_json_path), "r"
    )
    mock_import.assert_called_once()  # Check it was called with the loaded JSON content
    mock_activate.assert_called_once_with("imported_wf_id")
    mock_get_webhook_url.assert_called_once()


def test_configure_and_deploy_no_json_path(mock_n8n_config: N8NConfig, caplog):
    mock_n8n_config.workflow_json_path = None
    client = N8NClient(config=mock_n8n_config)
    assert client.configure_and_deploy_chat_workflow(1, "c", {}) is None
    assert "N8N_WORKFLOW_JSON_PATH not configured" in caplog.text


@patch("pathlib.Path.is_file", return_value=False)  # Mock Path.is_file to return False
def test_configure_and_deploy_json_file_not_found(
    mock_is_file, mock_n8n_config: N8NConfig, caplog
):
    client = N8NClient(config=mock_n8n_config)  # workflow_json_path is set in fixture
    assert client.configure_and_deploy_chat_workflow(1, "c", {}) is None
    assert (
        f"N8N workflow JSON file not found at: {mock_n8n_config.workflow_json_path}"
        in caplog.text
    )
