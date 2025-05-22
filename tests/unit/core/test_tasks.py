import pytest
from unittest.mock import patch, MagicMock

# from src.entrenai.db.models import MoodleFile # If needed for constructing moodle_file_info

# It's good practice to have sample data available for tests
SAMPLE_MOODLE_FILE_INFO = {
    "filename": "test_document.pdf",
    "fileurl": "http://example.com/test_document.pdf",
    "timemodified": 1678886400,  # Example timestamp
    "contextid": 100,
    "component": "mod_folder",
    "filearea": "content",
    "itemid": 123,
    "license": "allrightsreserved",
    "author": "Test User",
    "source": "",  # Usually empty or a URL
}

SAMPLE_PGVECTOR_CONFIG_DICT = {
    "host": "localhost",
    "port": 5432,
    "user": "test",
    "password": "test",
    "db_name": "test_db",
    "collection_prefix": "test_course_",
    "default_vector_size": 384,
}
SAMPLE_MOODLE_CONFIG_DICT = {
    "url": "http://moodle.example.com",
    "token": "test_token",
    "course_folder_name": "Entrenai Docs",
    "refresh_link_name": "Refresh",
    "chat_link_name": "Chat",
    "default_teacher_id": 1,
}
SAMPLE_AI_PROVIDER_CONFIG_OLLAMA = {
    "selected_provider": "ollama",
    "ollama": {
        "host": "http://ollama:11434",
        "embedding_model": "nomic-embed-text",
        "markdown_model": "llama3",
        "qa_model": "llama3",
        "context_model": "llama3",
    },
}
SAMPLE_BASE_CONFIG_DICT = {
    "log_level": "INFO",
    "fastapi_host": "0.0.0.0",
    "fastapi_port": 8000,
    "data_dir": "test_data",
    "download_dir": "test_data/downloads",
    "ai_provider": "ollama",
}


@pytest.fixture
def mock_celery_task_instance():
    """Mocks the bound Celery task instance (self)"""
    task_instance = MagicMock()
    task_instance.request.id = "test_task_id_123"
    return task_instance


@pytest.fixture
def mock_dependencies():
    """Mocks all external dependencies for the task"""
    with (
        patch("src.entrenai.core.tasks.MoodleClient") as MockMoodleClient,
        patch("src.entrenai.core.tasks.PgvectorWrapper") as MockPgvectorWrapper,
        patch("src.entrenai.core.tasks.FileProcessor") as MockFileProcessor,
        patch("src.entrenai.core.tasks.OllamaWrapper") as MockOllamaWrapper,
        patch("src.entrenai.core.tasks.GeminiWrapper") as MockGeminiWrapper,
        patch("src.entrenai.core.tasks.EmbeddingManager") as MockEmbeddingManager,
        patch("src.entrenai.core.tasks.Path") as MockPath,
    ):
        # Configure default return values for mocks if needed
        mock_moodle_client_instance = MockMoodleClient.return_value
        mock_pgvector_db_instance = MockPgvectorWrapper.return_value
        mock_file_processor_instance = MockFileProcessor.return_value
        # AI Client and Embedding Manager will be chosen based on config
        mock_ollama_wrapper_instance = MockOllamaWrapper.return_value
        mock_gemini_wrapper_instance = MockGeminiWrapper.return_value
        mock_embedding_manager_instance = MockEmbeddingManager.return_value

        # Mock Pathlib behavior
        mock_path_instance = MockPath.return_value
        mock_path_instance.__truediv__.return_value = (
            mock_path_instance  # e.g. Path() / "subdir"
        )
        mock_path_instance.stem = "test_document"

        yield {
            "moodle_client": mock_moodle_client_instance,
            "pgvector_db": mock_pgvector_db_instance,
            "file_processor": mock_file_processor_instance,
            "ollama_wrapper": mock_ollama_wrapper_instance,
            "gemini_wrapper": mock_gemini_wrapper_instance,
            "embedding_manager": mock_embedding_manager_instance,
            "path_lib": MockPath,  # The class itself for Path() calls
            "path_instance": mock_path_instance,  # Instance for operations like .unlink()
        }


# --- Test Cases for process_moodle_file_task ---

# 1. Test successful file processing (Ollama provider)
#    - Mock all external calls:
#        - MoodleClient.download_file returns a mock path.
#        - FileProcessor.process_file returns mock text.
#        - AIWrapper (Ollama).format_to_markdown returns mock markdown.
#        - EmbeddingManager.split_text_into_chunks returns mock chunks.
#        - EmbeddingManager.contextualize_chunk returns mock contextualized chunks.
#        - EmbeddingManager.generate_embeddings_for_chunks returns mock embeddings.
#        - EmbeddingManager.prepare_document_chunks_for_vector_db returns mock DB chunks.
#        - PgvectorWrapper.upsert_chunks returns True.
#        - PgvectorWrapper.mark_file_as_processed returns True.
#        - Path.unlink for cleanup is successful.
#    - Ensure the task runs to completion.
#    - Assert the task returns a dictionary with "status": "success" and correct "filename" and "chunks_upserted".
#    - Assert that pgvector_db.close_connection() was called (important for resource management).

# 2. Test successful file processing (Gemini provider)
#    - Similar to the Ollama success test, but ensure GeminiWrapper is used.
#    - Provide `ai_provider_config` that specifies Gemini.

# 3. Test failure during download
#    - Mock MoodleClient.download_file to raise an exception (e.g., ConnectionError).
#    - Ensure the task handles the exception gracefully.
#    - Assert the task returns a dictionary with "status": "error" and an "error_message".
#    - Assert that pgvector_db.close_connection() was called in the finally block.

# 4. Test failure during text extraction
#    - Mock FileProcessor.process_file to return None or raise an exception.
#    - Ensure graceful handling.
#    - Assert "status": "error" and appropriate message.
#    - Assert pgvector_db.close_connection() was called.

# 5. Test failure during AI processing (e.g., Markdown formatting)
#    - Mock AIWrapper.format_to_markdown to return None or raise an exception.
#    - Assert "status": "error".
#    - Assert pgvector_db.close_connection() was called.

# 6. Test failure during DB upsert
#    - Mock PgvectorWrapper.upsert_chunks to return False or raise an exception.
#    - Assert "status": "error".
#    - Assert pgvector_db.close_connection() was called.
#    - Consider if mark_file_as_processed should still be called or not in this case (current logic calls it).

# 7. Test scenario where no chunks are generated
#    - Mock EmbeddingManager.split_text_into_chunks to return an empty list.
#    - Ensure the task logs a warning.
#    - Ensure PgvectorWrapper.mark_file_as_processed is still called.
#    - Assert the task returns "status": "success_no_chunks" and "chunks_upserted": 0.
#    - Assert pgvector_db.close_connection() was called.

# 8. Test that pgvector_db.close_connection() is always called
#    - This is critical. Can be tested by checking `mock_pgvector_db_instance.close_connection.assert_called_once()`
#      in the `finally` part of each test or in a dedicated test that forces an earlier exception.

# 9. Test with various input parameters (edge cases)
#    - e.g., filename with special characters (if relevant to Path handling or external systems).
#    - e.g., empty moodle_file_info (though the task currently assumes valid basic info).
#    - This is more about robustness if the inputs can be unpredictable.

# 10. Test cleanup of downloaded file
#    - Ensure `downloaded_path.unlink(missing_ok=True)` is called after successful processing.
#    - Mock `downloaded_path.unlink` to verify its call.

# 11. Test cleanup failure of downloaded file
#     - Mock `downloaded_path.unlink` to raise an Exception.
#     - Ensure this failure is logged but does not cause the task to fail if main processing was successful.

# Example structure for a test:
# def test_process_moodle_file_successful_ollama(mock_celery_task_instance, mock_dependencies):
#     # 1. Arrange
#     # Configure mock_dependencies for a successful run with Ollama
#     mock_dependencies["moodle_client"].download_file.return_value = mock_dependencies["path_instance"]
#     mock_dependencies["file_processor"].process_file.return_value = ("Raw text", {}) # text, metadata
#     mock_dependencies["ollama_wrapper"].format_to_markdown.return_value = "Markdown text"
#     mock_dependencies["embedding_manager"].split_text_into_chunks.return_value = ["chunk1"]
#     mock_dependencies["embedding_manager"].contextualize_chunk.return_value = "contextualized_chunk1"
#     mock_dependencies["embedding_manager"].generate_embeddings_for_chunks.return_value = [[0.1, 0.2]]
#     mock_dependencies["embedding_manager"].prepare_document_chunks_for_vector_db.return_value = [
#         {"id": "1", "text_chunk": "contextualized_chunk1", "embedding": [0.1,0.2], "metadata": {}}
#     ]
#     mock_dependencies["pgvector_db"].upsert_chunks.return_value = True
#     mock_dependencies["pgvector_db"].mark_file_as_processed.return_value = True
#     mock_dependencies["path_instance"].unlink.return_value = True


#     # 2. Act
#     result = process_moodle_file_task(
#         mock_celery_task_instance,
#         course_id=1,
#         course_name_for_pgvector="test_course_1",
#         moodle_file_info=SAMPLE_MOODLE_FILE_INFO,
#         download_dir_str="test_data/downloads/1",
#         ai_provider_config=SAMPLE_AI_PROVIDER_CONFIG_OLLAMA,
#         pgvector_config_dict=SAMPLE_PGVECTOR_CONFIG_DICT,
#         moodle_config_dict=SAMPLE_MOODLE_CONFIG_DICT,
#         base_config_dict=SAMPLE_BASE_CONFIG_DICT,
#     )

#     # 3. Assert
#     assert result["status"] == "success"
#     assert result["filename"] == SAMPLE_MOODLE_FILE_INFO["filename"]
#     assert result["chunks_upserted"] == 1
#     mock_dependencies["pgvector_db"].close_connection.assert_called_once()
#     mock_dependencies["path_instance"].unlink.assert_called_once()
#     # Add more assertions: e.g. check calls to mocks with specific arguments
#     mock_dependencies["ollama_wrapper"].format_to_markdown.assert_called_once_with("Raw text", save_path=mock_dependencies["path_instance"])


# def test_process_moodle_file_download_failure(mock_celery_task_instance, mock_dependencies):
#     # 1. Arrange
#     mock_dependencies["moodle_client"].download_file.side_effect = Exception("Network Error")

#     # 2. Act
#     result = process_moodle_file_task(
#         mock_celery_task_instance,
#         course_id=1,
#         course_name_for_pgvector="test_course_1",
#         moodle_file_info=SAMPLE_MOODLE_FILE_INFO,
#         download_dir_str="test_data/downloads/1",
#         ai_provider_config=SAMPLE_AI_PROVIDER_CONFIG_OLLAMA,
#         pgvector_config_dict=SAMPLE_PGVECTOR_CONFIG_DICT,
#         moodle_config_dict=SAMPLE_MOODLE_CONFIG_DICT,
#         base_config_dict=SAMPLE_BASE_CONFIG_DICT,
#     )

#     # 3. Assert
#     assert result["status"] == "error"
#     assert "Network Error" in result["error_message"]
#     mock_dependencies["pgvector_db"].close_connection.assert_called_once()

# NOTE: For real implementation, each of these outlined tests would be a separate function.
# The example test function provides a template.
# Remember to also create __init__.py files in tests/unit and tests/unit/core if they don't exist.
pass  # Placeholder to make the file valid Python if no tests are uncommented initially
