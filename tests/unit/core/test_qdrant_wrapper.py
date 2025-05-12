import pytest
from unittest.mock import patch, MagicMock
from qdrant_client.http.models import Distance, VectorParams, PointStruct, UpdateStatus

from src.entrenai.core.qdrant_wrapper import QdrantWrapper, QdrantWrapperError
from src.entrenai.core.models import DocumentChunk  # For creating test data
from src.entrenai.config import QdrantConfig


@pytest.fixture
def mock_qdrant_config() -> QdrantConfig:
    config = MagicMock(spec=QdrantConfig)
    config.host = "mock_qdrant_host"
    config.port = 6333
    config.api_key = "mock_api_key"  # Can be None
    config.collection_prefix = "test_course_"
    config.default_vector_size = 384
    return config


@pytest.fixture
@patch("qdrant_client.QdrantClient")  # Mock the actual QdrantClient
def qdrant_wrapper_with_mock_client(
    MockQdrantClient, mock_qdrant_config: QdrantConfig
) -> tuple[QdrantWrapper, MagicMock]:
    mock_client_instance = MockQdrantClient.return_value
    # Simulate successful connection for __init__ check
    mock_client_instance.get_collections.return_value = MagicMock(collections=[])

    wrapper = QdrantWrapper(config=mock_qdrant_config)
    return wrapper, mock_client_instance


def test_qdrant_wrapper_initialization_success(
    qdrant_wrapper_with_mock_client: tuple[QdrantWrapper, MagicMock],
    mock_qdrant_config: QdrantConfig,
):
    wrapper, mock_client = qdrant_wrapper_with_mock_client
    assert wrapper.client == mock_client
    assert wrapper.config == mock_qdrant_config
    mock_client.get_collections.assert_called_once()  # From the __init__ health check


@patch("qdrant_client.QdrantClient")
def test_qdrant_wrapper_initialization_connection_error(
    MockQdrantClient, mock_qdrant_config: QdrantConfig, caplog
):
    MockQdrantClient.side_effect = Exception("Connection failed")
    wrapper = QdrantWrapper(
        config=mock_qdrant_config
    )  # Catches error, sets client to None
    assert wrapper.client is None
    assert "Failed to connect or initialize Qdrant client" in caplog.text


def test_get_collection_name(
    qdrant_wrapper_with_mock_client: tuple[QdrantWrapper, MagicMock],
):
    wrapper, _ = qdrant_wrapper_with_mock_client
    course_id = 123
    expected_name = f"{wrapper.config.collection_prefix}{course_id}"
    assert wrapper.get_collection_name(course_id) == expected_name


# --- Tests for ensure_collection ---
def test_ensure_collection_creates_if_not_exists(
    qdrant_wrapper_with_mock_client: tuple[QdrantWrapper, MagicMock],
):
    wrapper, mock_client = qdrant_wrapper_with_mock_client
    course_id = 101
    collection_name = wrapper.get_collection_name(course_id)
    vector_size = 384

    # Simulate collection does not exist
    mock_client.get_collections.return_value = MagicMock(collections=[])
    # Simulate successful creation
    mock_client.recreate_collection.return_value = True

    assert wrapper.ensure_collection(course_id, vector_size) is True
    mock_client.recreate_collection.assert_called_once_with(
        collection_name=collection_name,
        vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
    )


def test_ensure_collection_exists_with_correct_config(
    qdrant_wrapper_with_mock_client: tuple[QdrantWrapper, MagicMock],
):
    wrapper, mock_client = qdrant_wrapper_with_mock_client
    course_id = 102
    collection_name = wrapper.get_collection_name(course_id)
    vector_size = 384

    # Simulate collection exists and has correct config
    mock_collection_info = MagicMock()
    mock_collection_info.config.params.size = vector_size
    mock_collection_info.config.params.distance = Distance.COSINE

    # Mock get_collections to indicate it exists (though not strictly needed if get_collection is primary)
    mock_existing_collection_desc = MagicMock()
    mock_existing_collection_desc.name = collection_name
    mock_client.get_collections.return_value = MagicMock(
        collections=[mock_existing_collection_desc]
    )

    mock_client.get_collection.return_value = mock_collection_info

    assert wrapper.ensure_collection(course_id, vector_size) is True
    mock_client.get_collection.assert_called_with(collection_name=collection_name)
    mock_client.recreate_collection.assert_not_called()


def test_ensure_collection_exists_recreates_if_config_mismatch(
    qdrant_wrapper_with_mock_client: tuple[QdrantWrapper, MagicMock], caplog
):
    wrapper, mock_client = qdrant_wrapper_with_mock_client
    course_id = 103
    collection_name = wrapper.get_collection_name(course_id)
    correct_vector_size = 384
    wrong_vector_size = 128  # Mismatched size

    # Simulate collection exists but with wrong config
    mock_collection_info_wrong = MagicMock()
    mock_collection_info_wrong.config.params.size = wrong_vector_size  # Wrong size
    mock_collection_info_wrong.config.params.distance = Distance.COSINE
    mock_client.get_collection.return_value = mock_collection_info_wrong

    mock_existing_collection_desc = MagicMock()
    mock_existing_collection_desc.name = collection_name
    mock_client.get_collections.return_value = MagicMock(
        collections=[mock_existing_collection_desc]
    )

    mock_client.recreate_collection.return_value = (
        True  # Simulate successful recreation
    )

    assert wrapper.ensure_collection(course_id, correct_vector_size) is True
    assert (
        f"Collection '{collection_name}' exists but with different configuration. Recreating."
        in caplog.text
    )
    mock_client.recreate_collection.assert_called_once_with(
        collection_name=collection_name,
        vectors_config=VectorParams(size=correct_vector_size, distance=Distance.COSINE),
    )


def test_ensure_collection_handles_qdrant_error(
    qdrant_wrapper_with_mock_client: tuple[QdrantWrapper, MagicMock],
):
    wrapper, mock_client = qdrant_wrapper_with_mock_client
    mock_client.get_collections.side_effect = Exception("Qdrant API Error")

    with pytest.raises(QdrantWrapperError, match="Failed to ensure collection"):
        wrapper.ensure_collection(104, 384)


# --- Tests for upsert_chunks ---
def test_upsert_chunks_success(
    qdrant_wrapper_with_mock_client: tuple[QdrantWrapper, MagicMock],
):
    wrapper, mock_client = qdrant_wrapper_with_mock_client
    course_id = 201
    collection_name = wrapper.get_collection_name(course_id)

    chunks_to_upsert = [
        DocumentChunk(
            id="id1",
            course_id=course_id,
            document_id="doc1",
            text="text1",
            embedding=[0.1] * 384,
            metadata={"key": "val1"},
        ),
        DocumentChunk(
            id="id2",
            course_id=course_id,
            document_id="doc1",
            text="text2",
            embedding=[0.2] * 384,
            metadata={"key": "val2"},
        ),
    ]
    # Filter out chunks with None embeddings before creating PointStructs
    valid_chunks = [c for c in chunks_to_upsert if c.embedding is not None]
    expected_points = [
        PointStruct(id=chunk.id, vector=chunk.embedding, payload=chunk.metadata)
        for chunk in valid_chunks
    ]

    mock_client.upsert.return_value = MagicMock(status=UpdateStatus.COMPLETED)

    assert wrapper.upsert_chunks(course_id, chunks_to_upsert) is True
    mock_client.upsert.assert_called_once_with(
        collection_name=collection_name, points=expected_points, wait=True
    )


def test_upsert_chunks_empty_list(
    qdrant_wrapper_with_mock_client: tuple[QdrantWrapper, MagicMock],
):
    wrapper, mock_client = qdrant_wrapper_with_mock_client
    assert wrapper.upsert_chunks(202, []) is True  # Should succeed vacuously
    mock_client.upsert.assert_not_called()


def test_upsert_chunks_with_none_embeddings(
    qdrant_wrapper_with_mock_client: tuple[QdrantWrapper, MagicMock],
):
    wrapper, mock_client = qdrant_wrapper_with_mock_client
    course_id = 203
    collection_name = wrapper.get_collection_name(course_id)
    chunks_with_none_emb = [
        DocumentChunk(
            id="id1",
            course_id=course_id,
            document_id="doc1",
            text="text1",
            embedding=[0.1] * 384,
            metadata={},
        ),
        DocumentChunk(
            id="id2",
            course_id=course_id,
            document_id="doc1",
            text="text2",
            embedding=None,
            metadata={},
        ),  # None embedding
        DocumentChunk(
            id="id3",
            course_id=course_id,
            document_id="doc1",
            text="text3",
            embedding=[0.3] * 384,
            metadata={},
        ),
    ]

    valid_chunks = [c for c in chunks_with_none_emb if c.embedding is not None]
    expected_points = [
        PointStruct(id=chunk.id, vector=chunk.embedding, payload=chunk.metadata)
        for chunk in valid_chunks
    ]
    mock_client.upsert.return_value = MagicMock(status=UpdateStatus.COMPLETED)

    assert wrapper.upsert_chunks(course_id, chunks_with_none_emb) is True
    mock_client.upsert.assert_called_once_with(
        collection_name=collection_name,
        points=expected_points,  # Only valid points should be sent
        wait=True,
    )
    assert len(expected_points) == 2


def test_upsert_chunks_qdrant_api_error(
    qdrant_wrapper_with_mock_client: tuple[QdrantWrapper, MagicMock],
):
    wrapper, mock_client = qdrant_wrapper_with_mock_client
    mock_client.upsert.side_effect = Exception("Qdrant Upsert Error")
    chunks = [
        DocumentChunk(
            id="id1",
            course_id=1,
            document_id="d1",
            text="t1",
            embedding=[0.1] * 384,
            metadata={},
        )
    ]

    assert wrapper.upsert_chunks(1, chunks) is False  # Should return False on error


# --- Tests for search_chunks (basic) ---
def test_search_chunks_success(
    qdrant_wrapper_with_mock_client: tuple[QdrantWrapper, MagicMock],
):
    wrapper, mock_client = qdrant_wrapper_with_mock_client
    course_id = 301
    collection_name = wrapper.get_collection_name(course_id)
    query_embedding = [0.5] * 384
    top_k = 5

    # Simulate Qdrant search response
    mock_hit1 = MagicMock(
        id="hit1_id",
        score=0.9,
        payload={"text": "found text 1", "source_filename": "file1.pdf"},
    )
    mock_hit2 = MagicMock(
        id="hit2_id",
        score=0.8,
        payload={"text": "found text 2", "source_filename": "file2.pdf"},
    )
    mock_client.search.return_value = [mock_hit1, mock_hit2]

    results = wrapper.search_chunks(course_id, query_embedding, top_k=top_k)

    assert len(results) == 2
    assert results[0]["id"] == "hit1_id"
    assert results[0]["score"] == 0.9
    assert results[0]["payload"]["text"] == "found text 1"

    mock_client.search.assert_called_once_with(
        collection_name=collection_name,
        query_vector=query_embedding,
        query_filter=None,  # Assuming default for this test case
        limit=top_k,
        with_payload=True,
        with_vectors=False,
    )


def test_search_chunks_qdrant_api_error(
    qdrant_wrapper_with_mock_client: tuple[QdrantWrapper, MagicMock],
):
    wrapper, mock_client = qdrant_wrapper_with_mock_client
    mock_client.search.side_effect = Exception("Qdrant Search Error")

    with pytest.raises(QdrantWrapperError, match="Failed to search in collection"):
        wrapper.search_chunks(302, [0.1] * 384)
