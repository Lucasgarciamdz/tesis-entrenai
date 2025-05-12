import pytest
import sqlite3
import time
from pathlib import Path
from unittest.mock import patch
from typing import Iterator  # Corrected import for fixture type hint

from src.entrenai.core.file_tracker import FileTracker, FileTrackerError


@pytest.fixture
def memory_file_tracker() -> Iterator[FileTracker]:  # Corrected type hint
    """Returns a FileTracker instance using a temporary SQLite database file."""
    temp_db_file = Path(f"test_file_tracker_{time.time_ns()}.sqlite")
    tracker = FileTracker(db_path=temp_db_file)
    yield tracker
    if temp_db_file.exists():
        try:
            temp_db_file.unlink()
        except OSError as e:
            print(f"Warning: Could not remove temporary test DB {temp_db_file}: {e}")


def test_file_tracker_initialization(memory_file_tracker: FileTracker):
    tracker = memory_file_tracker
    try:
        with tracker._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                f"SELECT name FROM sqlite_master WHERE type='table' AND name='{tracker.TABLE_NAME}'"
            )
            assert cursor.fetchone() is not None, "Table was not created"
    except sqlite3.Error as e:
        pytest.fail(f"Database check failed: {e}")


def test_is_file_new(memory_file_tracker: FileTracker):
    tracker = memory_file_tracker
    course_id = 1
    file_id = "new_file.pdf"
    moodle_ts = int(time.time())
    assert tracker.is_file_new_or_modified(course_id, file_id, moodle_ts) is True


def test_mark_file_as_processed_and_check_not_new(memory_file_tracker: FileTracker):
    tracker = memory_file_tracker
    course_id = 1
    file_id = "processed_file.pdf"
    moodle_ts = int(time.time())
    tracker.mark_file_as_processed(course_id, file_id, moodle_ts)
    assert tracker.is_file_new_or_modified(course_id, file_id, moodle_ts) is False


def test_is_file_modified(memory_file_tracker: FileTracker):
    tracker = memory_file_tracker
    course_id = 1
    file_id = "modified_file.pdf"
    old_moodle_ts = int(time.time()) - 3600
    new_moodle_ts = int(time.time())
    tracker.mark_file_as_processed(course_id, file_id, old_moodle_ts)
    assert tracker.is_file_new_or_modified(course_id, file_id, new_moodle_ts) is True


def test_is_file_not_modified_older_timestamp(memory_file_tracker: FileTracker):
    tracker = memory_file_tracker
    course_id = 1
    file_id = "stale_file.pdf"
    current_moodle_ts = int(time.time())
    tracker.mark_file_as_processed(course_id, file_id, current_moodle_ts)
    assert (
        tracker.is_file_new_or_modified(course_id, file_id, current_moodle_ts) is False
    )
    older_moodle_ts = current_moodle_ts - 3600
    assert tracker.is_file_new_or_modified(course_id, file_id, older_moodle_ts) is False


def test_get_processed_files_timestamps(memory_file_tracker: FileTracker):
    tracker = memory_file_tracker
    course_id = 2
    file1_id = "doc1.pdf"
    file1_ts = int(time.time()) - 100
    file2_id = "doc2.txt"
    file2_ts = int(time.time()) - 50
    tracker.mark_file_as_processed(course_id, file1_id, file1_ts)
    tracker.mark_file_as_processed(course_id, file2_id, file2_ts)
    tracker.mark_file_as_processed(
        course_id + 1, "other_course_file.pdf", int(time.time())
    )
    timestamps = tracker.get_processed_files_timestamps(course_id)
    assert len(timestamps) == 2
    assert timestamps.get(file1_id) == file1_ts
    assert timestamps.get(file2_id) == file2_ts


# def test_replace_processed_file_record(memory_file_tracker: FileTracker):
#     tracker = memory_file_tracker
#     course_id = 3
#     file_id = "replaceable.pdf"
#     ts1 = int(time.time()) - 1000
#     ts2 = int(time.time()) - 500
#     tracker.mark_file_as_processed(course_id, file_id, ts1)
#     processed_at1 = tracker._get_connection().execute(
#         f"SELECT processed_at FROM {tracker.TABLE_NAME} WHERE course_id=? AND file_identifier=?",
#         (course_id, file_id)
#     ).fetchone()[0]
#     time.sleep(0.01)
#     tracker.mark_file_as_processed(course_id, file_id, ts2)
#     with tracker._get_connection() as conn:
#         cursor = conn.cursor()
#         cursor.execute(
#             f"SELECT moodle_timemodified, processed_at FROM {tracker.TABLE_NAME} WHERE course_id=? AND file_identifier=?",
#             (course_id, file_id)
#         )
#         row = cursor.fetchone()
#         assert row is not None
#         assert row[0] == ts2
#         assert row[1] > processed_at1


@patch.object(FileTracker, "_get_connection")
def test_is_file_new_or_modified_db_error(mock_get_connection, caplog):
    mock_conn = mock_get_connection.return_value.__enter__.return_value
    mock_conn.cursor.side_effect = sqlite3.Error("Simulated DB error")
    # Pass a dummy path that won't be used due to the mock.
    # The FileTracker's __init__ might still try to create the table if _ensure_db_and_table isn't also mocked
    # or if the mock isn't active during __init__.
    # For this test, we assume the tracker object is created and we're testing a method call.
    with patch.object(
        FileTracker, "_ensure_db_and_table", return_value=None
    ):  # Mock _ensure_db_and_table
        tracker = FileTracker(db_path=Path("dummy_error_check.sqlite"))
    assert (
        tracker.is_file_new_or_modified(1, "error_file.pdf", int(time.time())) is True
    )
    assert "Error checking file" in caplog.text


@patch.object(FileTracker, "_get_connection")
def test_mark_file_as_processed_db_error(mock_get_connection, caplog):
    mock_conn = mock_get_connection.return_value.__enter__.return_value
    mock_conn.cursor.side_effect = sqlite3.Error("Simulated DB error for mark")
    with patch.object(FileTracker, "_ensure_db_and_table", return_value=None):
        tracker = FileTracker(db_path=Path("dummy_error_mark.sqlite"))
    with pytest.raises(FileTrackerError, match="Failed to mark file as processed"):
        tracker.mark_file_as_processed(1, "error_mark.pdf", int(time.time()))
    assert "Error marking file" in caplog.text
