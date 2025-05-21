import pytest
from unittest.mock import patch, MagicMock
import ollama  # For ollama.ResponseError

from src.entrenai.core.ai.ollama_wrapper import OllamaWrapper, OllamaWrapperError
from src.entrenai.config import OllamaConfig


@pytest.fixture
def mock_ollama_config() -> OllamaConfig:
    config = MagicMock(spec=OllamaConfig)
    config.host = "http://mockollama:11434"
    config.embedding_model = "test_embed_model"
    config.markdown_model = "test_markdown_model"
    config.qa_model = "test_qa_model"
    config.context_model = (
        "test_context_model"  # Though not directly used in current methods
    )
    return config


from typing import Tuple  # For tuple type hint


@pytest.fixture
@patch("ollama.Client")  # Mock ollama.Client for all tests in this module
def ollama_wrapper_with_mock_client(
    MockOllamaClient, mock_ollama_config: OllamaConfig
) -> Tuple[OllamaWrapper, MagicMock]:
    # Configure the mock client instance that OllamaWrapper will create
    mock_client_instance = MockOllamaClient.return_value
    mock_client_instance.list.return_value = {
        "models": [
            {"name": "test_embed_model:latest"},
            {"name": "test_markdown_model:latest"},
            {"name": "test_qa_model:latest"},
        ]
    }  # Simulate models are available

    # Instantiate OllamaWrapper, it will use the mocked ollama.Client
    wrapper = OllamaWrapper(config=mock_ollama_config)
    return wrapper, mock_client_instance


def test_ollama_wrapper_initialization_success(
    ollama_wrapper_with_mock_client: Tuple[OllamaWrapper, MagicMock],
    mock_ollama_config: OllamaConfig,
):
    """Test successful initialization and model check."""
    ollama_wrapper, mock_client = ollama_wrapper_with_mock_client
    assert (
        ollama_wrapper.client is not None
    )  # client attribute of OllamaWrapper should be the mock_client
    assert ollama_wrapper.client == mock_client
    assert ollama_wrapper.config == mock_ollama_config
    mock_client.list.assert_called_once()


@patch("ollama.Client")
def test_ollama_wrapper_initialization_connection_error(
    MockOllamaClient, mock_ollama_config: OllamaConfig, caplog
):
    """Test initialization failure due to connection error."""
    MockOllamaClient.side_effect = Exception("Connection refused")

    # OllamaWrapper's __init__ catches this and sets self.client to None, logs error
    # It does not re-raise the exception by default in current implementation.
    wrapper = OllamaWrapper(config=mock_ollama_config)
    assert wrapper.client is None
    assert "Failed to connect or initialize Ollama client" in caplog.text


def test_ensure_models_available_logs_warning_if_model_missing(
    ollama_wrapper_with_mock_client: Tuple[OllamaWrapper, MagicMock], caplog
):
    """Test that _ensure_models_available logs a warning if a configured model is not in ollama.list()."""
    ollama_wrapper, mock_client = ollama_wrapper_with_mock_client
    # Temporarily change the mock list response to simulate a missing model
    mock_client.list.return_value = {
        "models": [
            {"name": "test_embed_model:latest"},
            # test_markdown_model is now missing
            {"name": "test_qa_model:latest"},
        ]
    }
    # Re-run the check (it's normally called in __init__)
    ollama_wrapper._ensure_models_available()
    assert (
        f"Ollama model for markdown ('{ollama_wrapper.config.markdown_model}') not found"
        in caplog.text
    )


# --- Tests for generate_embedding ---
def test_generate_embedding_success(
    ollama_wrapper_with_mock_client: Tuple[OllamaWrapper, MagicMock],
):
    ollama_wrapper, mock_client = ollama_wrapper_with_mock_client
    mock_response = {"embedding": [0.1, 0.2, 0.3]}
    mock_client.embeddings.return_value = mock_response

    embedding = ollama_wrapper.generate_embedding("test text")
    assert embedding == mock_response["embedding"]
    mock_client.embeddings.assert_called_once_with(
        model=ollama_wrapper.config.embedding_model, prompt="test text"
    )


def test_generate_embedding_api_error(
    ollama_wrapper_with_mock_client: Tuple[OllamaWrapper, MagicMock],
):
    ollama_wrapper, mock_client = ollama_wrapper_with_mock_client
    mock_client.embeddings.side_effect = ollama.ResponseError(
        "Ollama API error", status_code=500
    )

    with pytest.raises(OllamaWrapperError, match="Failed to generate embedding"):
        ollama_wrapper.generate_embedding("test text")


@patch("ollama.Client")  # Need to patch here as well for this specific test case
def test_generate_embedding_no_client(
    MockOllamaClientNoInit, mock_ollama_config: OllamaConfig
):
    # Simulate client failing to initialize by not setting up MockOllamaClientNoInit.return_value
    # or by having OllamaWrapper's __init__ logic for client assignment fail.
    # The current OllamaWrapper.__init__ sets self.client = None if ollama.Client() fails.
    # So, we can test this by ensuring the OllamaWrapper instance has client=None.

    # To ensure client is None, we can mock the ollama.Client constructor to raise an error
    # during the OllamaWrapper's __init__ call.
    MockOllamaClientNoInit.side_effect = Exception("Simulated client init failure")
    wrapper = OllamaWrapper(
        config=mock_ollama_config
    )  # This will set wrapper.client to None
    assert wrapper.client is None

    with pytest.raises(OllamaWrapperError, match="Ollama client not initialized"):
        wrapper.generate_embedding("test text")


# --- Tests for format_to_markdown ---
def test_format_to_markdown_success(
    ollama_wrapper_with_mock_client: Tuple[OllamaWrapper, MagicMock],
):
    ollama_wrapper, mock_client = ollama_wrapper_with_mock_client
    mock_chat_response = {"message": {"content": "## Markdown Output"}}
    mock_client.chat.return_value = mock_chat_response

    markdown_text = ollama_wrapper.format_to_markdown("raw text")
    assert markdown_text == "## Markdown Output"

    system_prompt = (
        "You are an expert text processing assistant. Your task is to convert the given text content "
        "into a clean, well-structured Markdown format. "
        "Preserve all factual information, lists, headings, and code blocks if present. "
        "Ensure the Markdown is readable and accurately represents the original content structure. "
        "Do not add any introductory phrases, summaries, or comments that are not part of the original text. "
        "Output only the Markdown content."
    )
    mock_client.chat.assert_called_once_with(
        model=ollama_wrapper.config.markdown_model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": "raw text"},
        ],
        stream=False,
    )


def test_format_to_markdown_api_error(
    ollama_wrapper_with_mock_client: Tuple[OllamaWrapper, MagicMock],
):
    ollama_wrapper, mock_client = ollama_wrapper_with_mock_client
    mock_client.chat.side_effect = ollama.ResponseError(
        "Ollama API error for chat", status_code=500
    )
    with pytest.raises(OllamaWrapperError, match="Failed to format text to Markdown"):
        ollama_wrapper.format_to_markdown("raw text")


# --- Tests for generate_chat_completion (basic) ---
def test_generate_chat_completion_success(
    ollama_wrapper_with_mock_client: Tuple[OllamaWrapper, MagicMock],
):
    ollama_wrapper, mock_client = ollama_wrapper_with_mock_client
    mock_response_content = "This is a QA response."
    mock_client.chat.return_value = {"message": {"content": mock_response_content}}

    response = ollama_wrapper.generate_chat_completion("A question?")
    assert response == mock_response_content

    expected_messages = [{"role": "user", "content": "A question?"}]
    mock_client.chat.assert_called_with(
        model=ollama_wrapper.config.qa_model, messages=expected_messages, stream=False
    )


def test_generate_chat_completion_with_system_message_and_context(
    ollama_wrapper_with_mock_client: Tuple[OllamaWrapper, MagicMock],
):
    ollama_wrapper, mock_client = ollama_wrapper_with_mock_client
    mock_response_content = "RAG response."
    mock_client.chat.return_value = {"message": {"content": mock_response_content}}

    prompt = "What is X?"
    system_msg = "You are helpful."
    context = ["Context chunk 1.", "Context chunk 2."]

    response = ollama_wrapper.generate_chat_completion(
        prompt, system_message=system_msg, context_chunks=context
    )
    assert response == mock_response_content

    full_prompt_expected = (
        f"Context:\n{context[0]}\n\n{context[1]}\n\nQuestion: {prompt}"
    )
    expected_messages = [
        {"role": "system", "content": system_msg},
        {"role": "user", "content": full_prompt_expected},
    ]
    mock_client.chat.assert_called_with(
        model=ollama_wrapper.config.qa_model, messages=expected_messages, stream=False
    )


def test_generate_chat_completion_api_error(
    ollama_wrapper_with_mock_client: Tuple[OllamaWrapper, MagicMock],
):
    ollama_wrapper, mock_client = ollama_wrapper_with_mock_client
    mock_client.chat.side_effect = ollama.ResponseError(
        "Ollama API error for QA", status_code=500
    )
    with pytest.raises(OllamaWrapperError, match="Failed to generate chat completion"):
        ollama_wrapper.generate_chat_completion("A question?")
