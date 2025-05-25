import pytest
import psycopg2  # For mocking errors
from unittest.mock import (
    patch,
    MagicMock,
    ANY,
)  # ANY and call for more flexible assertions
# Removed Qdrant specific imports like Distance, VectorParams, PointStruct, UpdateStatus

from src.entrenai.core.db.pgvector_wrapper import PgvectorWrapper  # Updated imports
from src.entrenai.api.models import DocumentChunk  # For creating test data
from src.entrenai.config import PgvectorConfig  # Updated import


@pytest.fixture
def mock_pgvector_config() -> PgvectorConfig:  # Renamed fixture and type hint
    config = MagicMock(spec=PgvectorConfig)
    config.host = "mock_pg_host"
    config.port = 5432
    config.user = "mock_user"
    config.password = "mock_password"
    config.db_name = "mock_db"
    config.collection_prefix = "test_course_"  # This is now a table prefix
    config.default_vector_size = 384
    return config


@pytest.fixture
@patch("psycopg2.connect")  # Mock the actual psycopg2.connect
@patch("src.entrenai.core.db.pgvector_wrapper.register_vector")  # Mock register_vector
def pgvector_wrapper_with_mock_connection(
    mock_register_vector, mock_psycopg2_connect, mock_pgvector_config: PgvectorConfig
) -> tuple[
    PgvectorWrapper, MagicMock, MagicMock
]:  # Return wrapper, mock_conn, mock_cursor
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_psycopg2_connect.return_value = mock_conn
    mock_conn.cursor.return_value = mock_cursor

    # Simulate successful connection and extension creation for __init__
    mock_cursor.fetchone.return_value = {
        "exists": True
    }  # For potential table checks during init if any

    wrapper = PgvectorWrapper(config=mock_pgvector_config)
    return wrapper, mock_conn, mock_cursor


def test_pgvector_wrapper_initialization_success(
    pgvector_wrapper_with_mock_connection: tuple[PgvectorWrapper, MagicMock, MagicMock],
    mock_pgvector_config: PgvectorConfig,
    # Patches are now in the fixture
):
    wrapper, mock_conn, mock_cursor = pgvector_wrapper_with_mock_connection

    assert wrapper.conn == mock_conn
    assert wrapper.cursor == mock_cursor
    assert wrapper.config == mock_pgvector_config

    # psycopg2.connect call is mocked in the fixture
    # Check if register_vector was called
    # register_vector_path.assert_called_once_with(mock_conn) # No, this is mocked in fixture now

    # Check if "CREATE EXTENSION IF NOT EXISTS vector;" was called
    mock_cursor.execute.assert_any_call("CREATE EXTENSION IF NOT EXISTS vector;")
    mock_conn.commit.assert_called()  # From CREATE EXTENSION


@patch("psycopg2.connect")
@patch("src.entrenai.core.db.pgvector_wrapper.register_vector")
def test_pgvector_wrapper_initialization_connection_error(
    mock_register_vector,
    mock_psycopg2_connect,
    mock_pgvector_config: PgvectorConfig,
    caplog,
):
    mock_psycopg2_connect.side_effect = psycopg2.Error("Connection failed")
    wrapper = PgvectorWrapper(config=mock_pgvector_config)
    assert wrapper.conn is None
    assert wrapper.cursor is None
    assert (
        f"Failed to connect to PostgreSQL/pgvector at {mock_pgvector_config.host}:{mock_pgvector_config.port}: Connection failed"
        in caplog.text
    )


def test_get_table_name(  # Renamed test
    pgvector_wrapper_with_mock_connection: tuple[PgvectorWrapper, MagicMock, MagicMock],
):
    wrapper, _, _ = pgvector_wrapper_with_mock_connection
    course_name = "My Sample Course 101"  # Test with a string name
    # _normalize_name_for_table will convert "My Sample Course 101" to "my_sample_course_101"
    # Then prefix will be added.
    expected_normalized_name = "my_sample_course_101"
    expected_table_name = (
        f"{wrapper.config.collection_prefix}{expected_normalized_name}"
    )
    assert wrapper.get_table_name(course_name) == expected_table_name

    course_name_short = "short"
    expected_table_name_short = f"{wrapper.config.collection_prefix}short"
    assert wrapper.get_table_name(course_name_short) == expected_table_name_short

    course_name_with_special_chars = "Course!@#$Name With Spaces"
    expected_normalized_chars = "coursename_with_spaces"
    expected_table_name_chars = (
        f"{wrapper.config.collection_prefix}{expected_normalized_chars}"
    )
    assert (
        wrapper.get_table_name(course_name_with_special_chars)
        == expected_table_name_chars
    )


# --- Tests for ensure_table ---
def test_ensure_table_creates_if_not_exists(
    pgvector_wrapper_with_mock_connection: tuple[PgvectorWrapper, MagicMock, MagicMock],
):
    wrapper, mock_conn, mock_cursor = pgvector_wrapper_with_mock_connection
    course_name = "New Course"
    table_name = wrapper.get_table_name(course_name)
    vector_size = 384

    # Simulate table does not exist
    mock_cursor.fetchone.return_value = {"exists": False}

    assert wrapper.ensure_table(course_name, vector_size) is True

    # Check for table existence query
    mock_cursor.execute.assert_any_call(
        "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = %s);",
        (table_name,),
    )

    # Check for CREATE TABLE statement
    expected_create_table_sql = f"""
            CREATE TABLE {table_name} (
                id TEXT PRIMARY KEY,
                course_id TEXT, 
                document_id TEXT,
                text TEXT,
                metadata JSONB,
                embedding vector({vector_size})
            );
            """
    # Normalize whitespace for comparison if necessary, or use ANY with regex if complex
    mock_cursor.execute.assert_any_call(
        ANY
    )  # First call is existence check, then CREATE TABLE
    # Find the create table call more robustly
    executed_sqls = [
        call_args[0][0] for call_args in mock_cursor.execute.call_args_list
    ]

    # Normalize SQL for comparison (basic whitespace normalization)
    def normalize_sql(sql):
        return " ".join(sql.strip().split())

    assert any(
        normalize_sql(expected_create_table_sql) == normalize_sql(sql)
        for sql in executed_sqls
    )

    # Check for CREATE INDEX statement
    expected_create_index_sql = (
        f"CREATE INDEX ON {table_name} USING hnsw (embedding vector_cosine_ops);"
    )
    assert any(
        normalize_sql(expected_create_index_sql) == normalize_sql(sql)
        for sql in executed_sqls
    )

    mock_conn.commit.assert_called()  # Should be called after successful creation


def test_ensure_table_exists(  # Renamed and simplified
    pgvector_wrapper_with_mock_connection: tuple[PgvectorWrapper, MagicMock, MagicMock],
):
    wrapper, mock_conn, mock_cursor = pgvector_wrapper_with_mock_connection
    course_name = "Existing Course"
    table_name = wrapper.get_table_name(course_name)
    vector_size = 384

    # Simulate table exists
    mock_cursor.fetchone.return_value = {"exists": True}

    # Reset call counts for execute before calling ensure_table
    mock_cursor.execute.reset_mock()
    mock_conn.commit.reset_mock()

    assert wrapper.ensure_table(course_name, vector_size) is True
    # Check that existence query was made
    mock_cursor.execute.assert_called_once_with(
        "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = %s);",
        (table_name,),
    )

    # Ensure no CREATE TABLE or CREATE INDEX calls were made
    executed_sqls = [
        call_args[0][0].upper() for call_args in mock_cursor.execute.call_args_list
    ]
    assert not any(
        "CREATE TABLE" in sql
        for sql in executed_sqls
        if sql
        != "SELECT EXISTS (SELECT FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME = %S);"
    )
    assert not any("CREATE INDEX" in sql for sql in executed_sqls)
    mock_conn.commit.assert_not_called()  # No changes, so no commit


# test_ensure_collection_exists_recreates_if_config_mismatch is removed as pgvector logic is different.


def test_ensure_table_handles_db_error(  # Renamed
    pgvector_wrapper_with_mock_connection: tuple[PgvectorWrapper, MagicMock, MagicMock],
    caplog,
):
    wrapper, mock_conn, mock_cursor = pgvector_wrapper_with_mock_connection
    course_name = "Error Course"
    vector_size = 384
    table_name = wrapper.get_table_name(course_name)

    # Simulate error during table existence check or creation
    mock_cursor.execute.side_effect = psycopg2.Error("DB API Error")

    assert wrapper.ensure_table(course_name, vector_size) is False
    assert f"Error ensuring table '{table_name}': DB API Error" in caplog.text
    mock_conn.rollback.assert_called_once()


# --- Tests for upsert_chunks ---
def test_upsert_chunks_success(
    pgvector_wrapper_with_mock_connection: tuple[PgvectorWrapper, MagicMock, MagicMock],
):
    wrapper, mock_conn, mock_cursor = pgvector_wrapper_with_mock_connection
    course_name = "Upsert Course"
    table_name = wrapper.get_table_name(course_name)
    # Mock ensure_table to return True
    wrapper.ensure_table = MagicMock(return_value=True)

    chunks_to_upsert = [
        DocumentChunk(
            id="id1",
            course_id=course_name,  # Assuming course_id in DocumentChunk can be course_name for consistency
            document_id="doc1",
            text="text1",
            embedding=[0.1] * 384,
            metadata={"key": "val1"},
        ),
        DocumentChunk(
            id="id2",
            course_id=course_name,
            document_id="doc1",
            text="text2",
            embedding=[0.2] * 384,
            metadata={
                "key": "val2",
                "another_key": {"nested": "value"},
            },  # Test with nested metadata
        ),
    ]

    assert wrapper.upsert_chunks(course_name, chunks_to_upsert) is True

    wrapper.ensure_table.assert_called_once_with(
        course_name, 384
    )  # Assuming default_vector_size or derived

    for chunk in chunks_to_upsert:
        # Check that chunk has necessary attributes for upsert
        import json  # For comparing metadata
        # Use a flexible way to check calls, as order of execute calls might include ensure_table's calls if not perfectly mocked
        # For now, checking that commit was called once (at the end of upsert)
        # And that execute was called with appropriate SQL for each chunk

        # This check is a bit tricky due to SQL formatting.
        # A simpler check is to see if execute was called N times (N = number of chunks)
        # and then check if commit was called.

        # Let's check the parameters of the calls to execute more carefully.
        # This requires iterating through mock_cursor.execute.call_args_list

    assert mock_cursor.execute.call_count >= len(
        chunks_to_upsert
    )  # At least one execute per chunk

    # More precise check for the SQL and params for each chunk
    actual_upsert_calls = [
        c for c in mock_cursor.execute.call_args_list if "INSERT INTO" in c.args[0]
    ]
    assert len(actual_upsert_calls) == len(chunks_to_upsert)

    for i, chunk in enumerate(chunks_to_upsert):
        executed_sql, executed_params = actual_upsert_calls[i].args
        assert f"INSERT INTO {table_name}" in executed_sql
        assert executed_params[0] == chunk.id
        assert executed_params[1] == str(chunk.course_id)
        assert executed_params[2] == chunk.document_id
        assert executed_params[3] == chunk.text
        # Metadata comparison needs care if it's JSON
        if isinstance(chunk.metadata, dict):
            assert json.loads(executed_params[4]) == chunk.metadata
        else:
            assert executed_params[4] == chunk.metadata
        assert executed_params[5] == chunk.embedding

    mock_conn.commit.assert_called_once()


def test_upsert_chunks_empty_list(
    pgvector_wrapper_with_mock_connection: tuple[PgvectorWrapper, MagicMock, MagicMock],
):
    wrapper, mock_conn, mock_cursor = pgvector_wrapper_with_mock_connection
    # Mock ensure_table
    wrapper.ensure_table = MagicMock(return_value=True)
    assert wrapper.upsert_chunks("EmptyListCourse", []) is True

    # Check that execute was not called for any chunk insertion
    insert_calls = [
        c for c in mock_cursor.execute.call_args_list if "INSERT INTO" in c.args[0]
    ]
    assert len(insert_calls) == 0
    # mock_conn.commit might be called by ensure_table if it created a table, so don't assert not_called() here
    # Or, ensure ensure_table is mocked not to commit if it doesn't create.
    # For this test, if ensure_table is truly mocked, then commit shouldn't be from upsert_chunks.
    # If upsert_chunks does nothing, it shouldn't commit.
    # However, the current code calls ensure_table which might commit.
    # Let's assume for an empty list, ensure_table is called, but no actual upsert SQLs are run.
    # And if no upserts, no specific commit from the upsert loop itself.

    # If we want to test only upsert_chunks's commit behavior:
    mock_conn.commit.reset_mock()  # Reset after ensure_table might have been called
    wrapper.upsert_chunks("EmptyListCourse", [])
    # mock_conn.commit.assert_not_called() # This depends on whether ensure_table is part of the unit or mocked out.
    # Given the current wrapper.ensure_table mock, this should hold.


def test_upsert_chunks_with_none_embeddings(
    pgvector_wrapper_with_mock_connection: tuple[PgvectorWrapper, MagicMock, MagicMock],
    caplog,
):
    wrapper, mock_conn, mock_cursor = pgvector_wrapper_with_mock_connection
    course_name = "NoneEmbCourse"
    # Mock ensure_table
    wrapper.ensure_table = MagicMock(return_value=True)

    chunks_with_none_emb = [
        DocumentChunk(
            id="id1",
            course_id=course_name,
            document_id="doc1",
            text="text1",
            embedding=[0.1] * 384,
            metadata={},
        ),
        DocumentChunk(  # This one will be skipped
            id="id2",
            course_id=course_name,
            document_id="doc1",
            text="text2",
            embedding=None,
            metadata={},
        ),
        DocumentChunk(
            id="id3",
            course_id=course_name,
            document_id="doc1",
            text="text3",
            embedding=[0.3] * 384,
            metadata={},
        ),
    ]

    assert wrapper.upsert_chunks(course_name, chunks_with_none_emb) is True

    insert_calls = [
        c for c in mock_cursor.execute.call_args_list if "INSERT INTO" in c.args[0]
    ]
    assert len(insert_calls) == 2  # Only two chunks are valid
    assert (
        "Chunk with ID 'id2' (course: NoneEmbCourse, doc: doc1) has no embedding. Skipping."
        in caplog.text
    )
    mock_conn.commit.assert_called_once()


def test_upsert_chunks_db_error(  # Renamed
    pgvector_wrapper_with_mock_connection: tuple[PgvectorWrapper, MagicMock, MagicMock],
    caplog,
):
    wrapper, mock_conn, mock_cursor = pgvector_wrapper_with_mock_connection
    course_name = "UpsertFailCourse"
    table_name = wrapper.get_table_name(course_name)
    # Mock ensure_table to return True
    wrapper.ensure_table = MagicMock(return_value=True)

    mock_cursor.execute.side_effect = psycopg2.Error("DB Upsert Error")
    chunks = [
        DocumentChunk(
            id="id1",
            course_id=course_name,
            document_id="d1",
            text="t1",
            embedding=[0.1] * 384,
            metadata={},
        )
    ]

    # The first call to execute inside upsert_chunks will raise the error
    assert wrapper.upsert_chunks(course_name, chunks) is False
    assert (
        f"Error upserting chunks into table '{table_name}': DB Upsert Error"
        in caplog.text
    )
    mock_conn.rollback.assert_called_once()


# --- Tests for search_chunks (basic) ---
def test_search_chunks_success(
    pgvector_wrapper_with_mock_connection: tuple[PgvectorWrapper, MagicMock, MagicMock],
):
    wrapper, mock_conn, mock_cursor = pgvector_wrapper_with_mock_connection
    course_name = "SearchCourse"
    table_name = wrapper.get_table_name(course_name)
    query_embedding = [0.5] * 384
    limit = 5

    # Simulate pgvector search response (list of dictionaries)
    mock_db_results = [
        {
            "id": "hit1_id",
            "score": 0.9,
            "course_id": course_name,
            "document_id": "doc1",
            "text": "found text 1",
            "metadata": {"source": "file1.pdf"},
        },
        {
            "id": "hit2_id",
            "score": 0.8,
            "course_id": course_name,
            "document_id": "doc2",
            "text": "found text 2",
            "metadata": {"source": "file2.pdf"},
        },
    ]
    mock_cursor.fetchall.return_value = mock_db_results

    results = wrapper.search_chunks(course_name, query_embedding, limit=limit)

    assert len(results) == 2
    assert results[0]["id"] == "hit1_id"
    assert results[0]["score"] == 0.9
    # Check payload reconstruction
    assert results[0]["payload"]["text"] == "found text 1"
    assert results[0]["payload"]["document_id"] == "doc1"
    assert results[0]["payload"]["metadata"] == {"source": "file1.pdf"}

    expected_query_sql = f"""
            SELECT id, course_id, document_id, text, metadata, (1 - (embedding <=> %s)) AS score 
            FROM {table_name}
            ORDER BY embedding <=> %s
            LIMIT %s;
            """
    # Normalize SQL for comparison as it might have slightly different whitespace
    executed_sql, params = mock_cursor.execute.call_args.args
    assert normalize_sql(executed_sql) == normalize_sql(expected_query_sql)
    assert params == (query_embedding, query_embedding, limit)


def test_search_chunks_db_error(  # Renamed
    pgvector_wrapper_with_mock_connection: tuple[PgvectorWrapper, MagicMock, MagicMock],
    caplog,
):
    wrapper, mock_conn, mock_cursor = pgvector_wrapper_with_mock_connection
    course_name = "SearchFailCourse"
    table_name = wrapper.get_table_name(course_name)
    mock_cursor.execute.side_effect = psycopg2.Error("DB Search Error")

    results = wrapper.search_chunks(course_name, [0.1] * 384)
    assert results == []  # Should return empty list on error
    assert f"Error searching in table '{table_name}': DB Search Error" in caplog.text
    mock_conn.rollback.assert_called_once()


# Helper function for SQL normalization (if not already present)
def normalize_sql(sql):
    return " ".join(sql.strip().split())
