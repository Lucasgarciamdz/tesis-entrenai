import pytest
import time
from unittest.mock import patch, MagicMock, PropertyMock

# Imports to be tested
from src.entrenai.core.db.pgvector_wrapper import PgvectorWrapper
from src.entrenai.config import PgvectorConfig

# Import for mocking database errors
import psycopg2 # Keep this for psycopg2.Error


@pytest.fixture
def mock_pgvector_config() -> PgvectorConfig:
    """Returns a MagicMock instance of PgvectorConfig."""
    config = MagicMock(spec=PgvectorConfig)
    config.host = "mock_host"
    config.port = 1234
    config.user = "mock_user"
    config.password = "mock_password"
    config.db_name = "mock_db"
    # Add other attributes if PgvectorWrapper's __init__ uses them and they are not part of the above
    config.collection_prefix = "mock_prefix_" 
    config.default_vector_size = 384 
    return config


@pytest.fixture
def mocked_pgvector_wrapper(mock_pgvector_config: PgvectorConfig) -> PgvectorWrapper:
    """
    Yields a PgvectorWrapper instance with a mocked database connection and cursor.
    The psycopg2.connect call itself is mocked to prevent actual DB operations
    during PgvectorWrapper.__init__ (which calls ensure_file_tracker_table).
    """
    mock_conn = MagicMock(spec=psycopg2.extensions.connection)
    mock_cursor = MagicMock(spec=psycopg2.extensions.cursor)
    
    # Mock the __enter__ and __exit__ methods for context management
    mock_conn.cursor.return_value = mock_cursor
    
    with patch('psycopg2.connect', return_value=mock_conn) as mock_connect:
        # Patch 'register_vector' as it's called during init
        with patch('src.entrenai.core.db.pgvector_wrapper.register_vector', MagicMock()) as mock_register_vector:
            wrapper = PgvectorWrapper(config=mock_pgvector_config)
            # Ensure the mock cursor is directly usable by the wrapper instance
            wrapper.conn = mock_conn
            wrapper.cursor = mock_cursor 
            yield wrapper # Test will run here
    # No explicit cleanup needed for mocks unless specific side effects were started


def test_pgvector_wrapper_initialization(mocked_pgvector_wrapper: PgvectorWrapper, mock_pgvector_config: PgvectorConfig, caplog):
    """Test that PgvectorWrapper initializes and attempts to create the file_tracker table."""
    wrapper = mocked_pgvector_wrapper
    
    # Check if ensure_file_tracker_table was called (indirectly via __init__)
    # The mock_cursor should have been called by ensure_file_tracker_table
    # First call is to check if table exists, second (if not exists) is to create it.
    # We are asserting that the __init__ sequence which calls ensure_file_tracker_table tried to use the cursor.
    assert wrapper.cursor.execute.called, "cursor.execute was not called during initialization (for file_tracker table)"
    
    # Example: check one of the expected queries from ensure_file_tracker_table
    # This depends on the exact SQL in ensure_file_tracker_table
    found_table_check_call = False
    for call_args in wrapper.cursor.execute.call_args_list:
        sql = call_args[0][0] # First argument of the first call
        if f"SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = '{wrapper.FILE_TRACKER_TABLE_NAME}')" in sql:
            found_table_check_call = True
            break
    assert found_table_check_call, f"Did not find expected table existence check for {wrapper.FILE_TRACKER_TABLE_NAME}"
    
    # Check connection log message
    assert f"PgvectorWrapper initialized and connected to {mock_pgvector_config.host}:{mock_pgvector_config.port}/{mock_pgvector_config.db_name}" in caplog.text
    # Check file tracker table log message (assuming it's created or already exists)
    # This log comes from ensure_file_tracker_table
    assert f"Table '{wrapper.FILE_TRACKER_TABLE_NAME}'" in caplog.text # Could be "already exists" or "created"


def test_is_file_new(mocked_pgvector_wrapper: PgvectorWrapper):
    wrapper = mocked_pgvector_wrapper
    wrapper.cursor.fetchone.return_value = None  # Simulate file not found in DB
    
    course_id = 1
    file_identifier = "new_file.pdf"
    moodle_timemodified = int(time.time())
    
    assert wrapper.is_file_new_or_modified(course_id, file_identifier, moodle_timemodified) is True
    wrapper.cursor.execute.assert_called_once_with(
        f"\n            SELECT moodle_timemodified\n            FROM {wrapper.FILE_TRACKER_TABLE_NAME}\n            WHERE course_id = %s AND file_identifier = %s;\n            ",
        (course_id, file_identifier)
    )


def test_mark_file_as_processed_and_check_not_new(mocked_pgvector_wrapper: PgvectorWrapper):
    wrapper = mocked_pgvector_wrapper
    course_id = 1
    file_id = "processed_file.pdf"
    moodle_ts = int(time.time())

    # Simulate marking as processed
    wrapper.cursor.execute.return_value = None # For the UPSERT
    result = wrapper.mark_file_as_processed(course_id, file_id, moodle_ts)
    assert result is True
    wrapper.conn.commit.assert_called_once() # Ensure commit was called

    # Reset mock for the next call (is_file_new_or_modified)
    wrapper.cursor.reset_mock() 
    wrapper.cursor.fetchone.return_value = {'moodle_timemodified': moodle_ts} # Simulate file found with same timestamp
    
    assert wrapper.is_file_new_or_modified(course_id, file_id, moodle_ts) is False
    # Check the SQL for is_file_new_or_modified
    wrapper.cursor.execute.assert_called_once_with(
        f"\n            SELECT moodle_timemodified\n            FROM {wrapper.FILE_TRACKER_TABLE_NAME}\n            WHERE course_id = %s AND file_identifier = %s;\n            ",
        (course_id, file_id)
    )


def test_is_file_modified(mocked_pgvector_wrapper: PgvectorWrapper):
    wrapper = mocked_pgvector_wrapper
    course_id = 1
    file_id = "modified_file.pdf"
    old_moodle_ts = int(time.time()) - 3600
    new_moodle_ts = int(time.time())

    # Simulate already processed with old_moodle_ts for the is_file_new_or_modified check
    wrapper.cursor.fetchone.return_value = {'moodle_timemodified': old_moodle_ts}
    
    assert wrapper.is_file_new_or_modified(course_id, file_id, new_moodle_ts) is True
    wrapper.cursor.execute.assert_called_once_with(
        f"\n            SELECT moodle_timemodified\n            FROM {wrapper.FILE_TRACKER_TABLE_NAME}\n            WHERE course_id = %s AND file_identifier = %s;\n            ",
        (course_id, file_id)
    )


def test_is_file_not_modified_older_timestamp(mocked_pgvector_wrapper: PgvectorWrapper):
    wrapper = mocked_pgvector_wrapper
    course_id = 1
    file_id = "stale_file.pdf"
    current_moodle_ts = int(time.time())
    older_moodle_ts = current_moodle_ts - 3600

    # Simulate processed with current_moodle_ts
    wrapper.cursor.fetchone.return_value = {'moodle_timemodified': current_moodle_ts}
    assert wrapper.is_file_new_or_modified(course_id, file_id, current_moodle_ts) is False
    
    # Reset mock for the next call with older timestamp
    wrapper.cursor.reset_mock() # Reset call count for execute
    wrapper.cursor.fetchone.return_value = {'moodle_timemodified': current_moodle_ts} # Still returns the stored current_ts
    assert wrapper.is_file_new_or_modified(course_id, file_id, older_moodle_ts) is False


def test_get_processed_files_timestamps(mocked_pgvector_wrapper: PgvectorWrapper):
    wrapper = mocked_pgvector_wrapper
    course_id = 2
    file1_id = "doc1.pdf"
    file1_ts = int(time.time()) - 100
    file2_id = "doc2.txt"
    file2_ts = int(time.time()) - 50

    # Simulate DB response for get_processed_files_timestamps
    db_results = [
        {'file_identifier': file1_id, 'moodle_timemodified': file1_ts},
        {'file_identifier': file2_id, 'moodle_timemodified': file2_ts},
    ]
    wrapper.cursor.fetchall.return_value = db_results
    
    timestamps = wrapper.get_processed_files_timestamps(course_id)
    
    assert len(timestamps) == 2
    assert timestamps.get(file1_id) == file1_ts
    assert timestamps.get(file2_id) == file2_ts
    wrapper.cursor.execute.assert_called_once_with(
        f"\n            SELECT file_identifier, moodle_timemodified\n            FROM {wrapper.FILE_TRACKER_TABLE_NAME}\n            WHERE course_id = %s;\n            ",
        (course_id,)
    )


def test_is_file_new_or_modified_db_error(mocked_pgvector_wrapper: PgvectorWrapper, caplog):
    wrapper = mocked_pgvector_wrapper
    wrapper.cursor.execute.side_effect = psycopg2.Error("Simulated DB error for is_file_new_or_modified")
    
    assert wrapper.is_file_new_or_modified(1, "error_file.pdf", int(time.time())) is True # Conservative return
    assert "Error checking file status" in caplog.text
    wrapper.conn.rollback.assert_called_once()


def test_mark_file_as_processed_db_error(mocked_pgvector_wrapper: PgvectorWrapper, caplog):
    wrapper = mocked_pgvector_wrapper
    wrapper.cursor.execute.side_effect = psycopg2.Error("Simulated DB error for mark_file_as_processed")
    
    result = wrapper.mark_file_as_processed(1, "error_mark.pdf", int(time.time()))
    assert result is False # Method should return False on error
    assert "Error marking file" in caplog.text
    wrapper.conn.rollback.assert_called_once()


def test_get_processed_files_timestamps_db_error(mocked_pgvector_wrapper: PgvectorWrapper, caplog):
    wrapper = mocked_pgvector_wrapper
    wrapper.cursor.execute.side_effect = psycopg2.Error("Simulated DB error for get_processed_files_timestamps")

    timestamps = wrapper.get_processed_files_timestamps(1)
    assert timestamps == {} # Should return empty dict on error
    assert "Error retrieving processed files timestamps" in caplog.text
    wrapper.conn.rollback.assert_called_once()

def test_ensure_file_tracker_table_db_error_during_init_check(mock_pgvector_config, caplog):
    """
    Tests that if ensure_file_tracker_table (called in __init__) encounters a DB error,
    it's logged and handled.
    """
    mock_conn = MagicMock(spec=psycopg2.extensions.connection)
    mock_cursor = MagicMock(spec=psycopg2.extensions.cursor)
    mock_conn.cursor.return_value = mock_cursor
    
    # Simulate error only on the first execute call (checking table existence)
    mock_cursor.execute.side_effect = psycopg2.Error("Simulated DB error during table check")

    with patch('psycopg2.connect', return_value=mock_conn):
        with patch('src.entrenai.core.db.pgvector_wrapper.register_vector', MagicMock()):
            # Initialization will call ensure_file_tracker_table
            PgvectorWrapper(config=mock_pgvector_config) 
    
    assert f"Error ensuring table '{PgvectorWrapper.FILE_TRACKER_TABLE_NAME}'" in caplog.text
    mock_conn.rollback.assert_called_once()

def test_ensure_file_tracker_table_already_exists(mocked_pgvector_wrapper: PgvectorWrapper, caplog):
    """
    Tests that if ensure_file_tracker_table finds the table already exists, it logs and returns.
    This is tricky because the fixture already runs __init__ (and thus ensure_file_tracker_table).
    We need to inspect the calls made *during the fixture's setup of this specific test*.
    Alternatively, we can call ensure_file_tracker_table() again and check the logs.
    """
    wrapper = mocked_pgvector_wrapper
    # Reset mocks to clear calls from __init__ in the fixture
    wrapper.cursor.reset_mock()
    caplog.clear()

    # Simulate table exists
    wrapper.cursor.fetchone.return_value = {'exists': True} 
    
    wrapper.ensure_file_tracker_table() # Call it again
    
    # Check that it logged "already exists"
    assert f"Table '{wrapper.FILE_TRACKER_TABLE_NAME}' already exists." in caplog.text
    # And it should not have tried to create it again
    create_call_found = False
    for call_args in wrapper.cursor.execute.call_args_list:
        sql = call_args[0][0]
        if "CREATE TABLE" in sql:
            create_call_found = True
            break
    assert not create_call_found, "Should not have attempted to CREATE TABLE if it already exists."

def test_no_db_connection_scenario_for_methods(mock_pgvector_config, caplog):
    """
    Tests how methods behave if self.conn or self.cursor is None (e.g., initial connection failed).
    """
    # This time, let psycopg2.connect actually fail in the __init__
    with patch('psycopg2.connect', side_effect=psycopg2.OperationalError("Simulated connection failure")):
        with patch('src.entrenai.core.db.pgvector_wrapper.register_vector', MagicMock()):
            wrapper = PgvectorWrapper(config=mock_pgvector_config)

    assert wrapper.conn is None
    assert wrapper.cursor is None
    
    caplog.clear() # Clear logs from init
    
    # Test is_file_new_or_modified
    assert wrapper.is_file_new_or_modified(1, "file.txt", 123) is True # Conservative return
    assert "No database connection. Cannot check file status." in caplog.text
    caplog.clear()

    # Test mark_file_as_processed
    assert wrapper.mark_file_as_processed(1, "file.txt", 123) is False
    assert "No database connection. Cannot mark file as processed." in caplog.text
    caplog.clear()

    # Test get_processed_files_timestamps
    assert wrapper.get_processed_files_timestamps(1) == {}
    assert "No database connection. Cannot get processed files timestamps." in caplog.text
    caplog.clear()
    
    # Test ensure_file_tracker_table (if called directly)
    wrapper.ensure_file_tracker_table()
    assert "No database connection. Cannot ensure file_tracker table." in caplog.text
