import pytest
import uuid
from typing import List, Optional, Dict, Any
from unittest.mock import MagicMock

from src.entrenai.core.embedding_manager import EmbeddingManager
from src.entrenai.core.ollama_wrapper import OllamaWrapperError
from src.entrenai.core.models import DocumentChunk
from src.entrenai.config import OllamaConfig  # For MockOllamaWrapper config


# --- Mock OllamaWrapper ---
class MockOllamaWrapper:
    def __init__(self, config: Optional[OllamaConfig] = None):
        self.config = config or MagicMock(spec=OllamaConfig)
        # Simulate default embedding model if needed by EmbeddingManager's OllamaWrapper calls
        if (
            not hasattr(self.config, "embedding_model")
            or not self.config.embedding_model
        ):
            self.config.embedding_model = "mock_embedding_model"
        self.generate_embedding_call_count = 0

    def generate_embedding(self, text: str, model: Optional[str] = None) -> List[float]:
        self.generate_embedding_call_count += 1
        # Return a dummy embedding of a fixed size, e.g., 384
        # The actual content of the embedding doesn't matter for most unit tests here.
        if "error_in_text" in text:  # Simulate an error for a specific chunk
            raise OllamaWrapperError("Simulated embedding generation error")
        return [0.1] * 384

    def format_to_markdown(self, text_content: str, model: Optional[str] = None) -> str:
        # Not directly used by EmbeddingManager in current design, but good to have for completeness
        return f"MARKDOWN: {text_content}"


@pytest.fixture
def mock_ollama_wrapper() -> MockOllamaWrapper:
    return MockOllamaWrapper()


@pytest.fixture
def embedding_manager(mock_ollama_wrapper: MockOllamaWrapper) -> EmbeddingManager:
    return EmbeddingManager(
        ollama_wrapper=mock_ollama_wrapper,
        default_chunk_size=100,
        default_chunk_overlap=20,
    )  # type: ignore


# --- Tests for split_text_into_chunks ---
def test_split_text_empty(embedding_manager: EmbeddingManager):
    assert embedding_manager.split_text_into_chunks("") == []


def test_split_text_shorter_than_chunk_size(embedding_manager: EmbeddingManager):
    text = "Short text."
    chunks = embedding_manager.split_text_into_chunks(text, chunk_size=100)
    assert chunks == [text]


def test_split_text_exact_chunk_size(embedding_manager: EmbeddingManager):
    text = "a" * 100
    chunks = embedding_manager.split_text_into_chunks(
        text, chunk_size=100, chunk_overlap=0
    )
    assert chunks == [text]


def test_split_text_multiple_chunks_no_overlap(embedding_manager: EmbeddingManager):
    text = "a" * 250
    chunks = embedding_manager.split_text_into_chunks(
        text, chunk_size=100, chunk_overlap=0
    )
    assert len(chunks) == 3
    assert chunks[0] == "a" * 100
    assert chunks[1] == "a" * 100
    assert chunks[2] == "a" * 50


def test_split_text_multiple_chunks_with_overlap(embedding_manager: EmbeddingManager):
    # chunk_size=100, chunk_overlap=20. Effective step is 80.
    # Text length 180:
    # Chunk 1: text[0:100]
    # Next start: 80. Chunk 2: text[80:180] (length 100)
    text = "0123456789" * 18  # Length 180
    chunks = embedding_manager.split_text_into_chunks(
        text, chunk_size=100, chunk_overlap=20
    )
    assert len(chunks) == 2
    assert chunks[0] == text[0:100]
    assert chunks[1] == text[80:180]


def test_split_text_overlap_greater_than_size_raises_error(
    embedding_manager: EmbeddingManager,
):
    with pytest.raises(
        ValueError, match="Chunk overlap must be smaller than chunk size"
    ):
        embedding_manager.split_text_into_chunks(
            "some text", chunk_size=50, chunk_overlap=50
        )

    with pytest.raises(
        ValueError, match="Chunk overlap must be smaller than chunk size"
    ):
        embedding_manager.split_text_into_chunks(
            "some text", chunk_size=50, chunk_overlap=60
        )


# --- Tests for contextualize_chunk ---
def test_contextualize_chunk_all_metadata(embedding_manager: EmbeddingManager):
    chunk_text = "This is the core content."
    title = "Test Document"
    filename = "test.pdf"
    contextualized = embedding_manager.contextualize_chunk(
        chunk_text, document_title=title, source_filename=filename
    )
    assert f"Fuente del Archivo: {filename}" in contextualized
    assert f"Título del Documento: {title}" in contextualized
    assert f"Contenido del Chunk:\n{chunk_text}" in contextualized


def test_contextualize_chunk_some_metadata(embedding_manager: EmbeddingManager):
    chunk_text = "Core content."
    filename = "source.txt"
    contextualized = embedding_manager.contextualize_chunk(
        chunk_text, source_filename=filename
    )
    assert f"Fuente del Archivo: {filename}" in contextualized
    assert "Título del Documento:" not in contextualized
    assert f"Contenido del Chunk:\n{chunk_text}" in contextualized


def test_contextualize_chunk_no_metadata(embedding_manager: EmbeddingManager):
    chunk_text = "Just the chunk."
    contextualized = embedding_manager.contextualize_chunk(chunk_text)
    assert contextualized == chunk_text  # No prefix if no metadata


# --- Tests for generate_embeddings_for_chunks ---
def test_generate_embeddings_empty_list(
    embedding_manager: EmbeddingManager, mock_ollama_wrapper: MockOllamaWrapper
):
    assert embedding_manager.generate_embeddings_for_chunks([]) == []
    assert mock_ollama_wrapper.generate_embedding_call_count == 0


def test_generate_embeddings_success(
    embedding_manager: EmbeddingManager, mock_ollama_wrapper: MockOllamaWrapper
):
    chunks = ["chunk1", "chunk2"]
    embeddings = embedding_manager.generate_embeddings_for_chunks(chunks)
    assert len(embeddings) == 2
    assert len(embeddings[0]) == 384  # Mock embedding size
    assert len(embeddings[1]) == 384
    assert mock_ollama_wrapper.generate_embedding_call_count == 2


def test_generate_embeddings_one_fails(
    embedding_manager: EmbeddingManager, mock_ollama_wrapper: MockOllamaWrapper, caplog
):
    chunks = ["good_chunk", "error_in_text_chunk", "another_good_chunk"]
    embeddings = embedding_manager.generate_embeddings_for_chunks(chunks)
    assert len(embeddings) == 3
    assert embeddings[0] is not None and len(embeddings[0]) == 384
    assert embeddings[1] == []  # Placeholder for failed embedding
    assert embeddings[2] is not None and len(embeddings[2]) == 384
    assert mock_ollama_wrapper.generate_embedding_call_count == 3  # Called for all
    assert "Failed to generate embedding for chunk 2" in caplog.text


# --- Tests for prepare_document_chunks_for_qdrant ---
def test_prepare_document_chunks_valid_input(embedding_manager: EmbeddingManager):
    course_id = 1
    doc_id = "doc1"
    filename = "file1.pdf"
    title = "File 1 Title"
    chunks_text = ["text1", "text2"]
    embeddings = [[0.1] * 384, [0.2] * 384]

    qdrant_chunks = embedding_manager.prepare_document_chunks_for_qdrant(
        course_id, doc_id, filename, title, chunks_text, embeddings
    )
    assert len(qdrant_chunks) == 2
    for i, qc in enumerate(qdrant_chunks):
        assert isinstance(qc, DocumentChunk)
        assert isinstance(uuid.UUID(qc.id), uuid.UUID)  # Check valid UUID
        assert qc.course_id == course_id
        assert qc.document_id == doc_id
        assert qc.text == chunks_text[i]
        assert qc.embedding == embeddings[i]
        assert qc.metadata["source_filename"] == filename
        assert qc.metadata["document_title"] == title
        assert (
            qc.metadata["original_text"] == chunks_text[i]
        )  # As per current implementation


def test_prepare_document_chunks_with_additional_metadata(
    embedding_manager: EmbeddingManager,
):
    course_id = 1
    doc_id = "doc_meta"
    filename = "meta.txt"
    chunks_text = ["chunk with meta"]
    embeddings = [[0.3] * 384]
    # Explicitly type additional_metadatas to match the expected signature component
    additional_metadatas: List[Optional[Dict[str, Any]]] = [
        {"page_number": 5, "custom_key": "value"}
    ]

    qdrant_chunks = embedding_manager.prepare_document_chunks_for_qdrant(
        course_id, doc_id, filename, None, chunks_text, embeddings, additional_metadatas
    )
    assert len(qdrant_chunks) == 1
    qc = qdrant_chunks[0]
    assert qc.metadata["page_number"] == 5
    assert qc.metadata["custom_key"] == "value"


def test_prepare_document_chunks_mismatched_lengths_raises_error(
    embedding_manager: EmbeddingManager,
):
    with pytest.raises(
        ValueError, match="Number of text chunks and embeddings must match"
    ):
        embedding_manager.prepare_document_chunks_for_qdrant(
            1, "d", "f", "t", ["t1"], []
        )

    with pytest.raises(
        ValueError, match="Number of text chunks and additional_metadatas must match"
    ):
        embedding_manager.prepare_document_chunks_for_qdrant(
            1, "d", "f", "t", ["t1"], [[0.1] * 384], [{}, {}]
        )


def test_prepare_document_chunks_handles_failed_embedding(
    embedding_manager: EmbeddingManager,
):
    chunks_text = ["good_text", "text_for_failed_emb"]
    embeddings = [[0.1] * 384, []]  # Second embedding failed (empty list)

    qdrant_chunks = embedding_manager.prepare_document_chunks_for_qdrant(
        1, "doc_fail", "fail.pdf", "Fail Doc", chunks_text, embeddings
    )
    assert len(qdrant_chunks) == 2
    assert qdrant_chunks[0].embedding is not None
    assert qdrant_chunks[1].embedding is None  # Should be None for the failed one
    assert qdrant_chunks[1].text == chunks_text[1]
