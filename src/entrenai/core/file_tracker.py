import sqlite3
import time
from pathlib import Path
from typing import Optional, Dict

from src.entrenai.utils.logger import get_logger

# Import base_config to get db_path, assuming it's added to BaseConfig or a specific FileConfig
from src.entrenai.config import base_config

logger = get_logger(__name__)


class FileTrackerError(Exception):
    """Custom exception for FileTracker errors."""

    pass


class FileTracker:
    """
    Tracks processed files and their modification timestamps using an SQLite database.
    """

    TABLE_NAME = "processed_files"

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = Path(db_path or base_config.file_tracker_db_path)
        self._ensure_db_and_table()
        logger.info(f"FileTracker initialized with database: {self.db_path}")

    def _get_connection(self) -> sqlite3.Connection:
        """Establishes and returns a database connection."""
        try:
            # The directory for the SQLite DB file must exist.
            # os.makedirs(self.db_path.parent, exist_ok=True) # Done in config.py now
            conn = sqlite3.connect(self.db_path)
            return conn
        except sqlite3.Error as e:
            logger.error(
                f"Error connecting to FileTracker database at {self.db_path}: {e}"
            )
            raise FileTrackerError(f"Could not connect to database: {e}") from e

    def _ensure_db_and_table(self):
        """Ensures the database and the necessary table exist."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(f"""
                    CREATE TABLE IF NOT EXISTS {self.TABLE_NAME} (
                        course_id INTEGER NOT NULL,
                        file_identifier TEXT NOT NULL, -- e.g., filename or unique Moodle file ID
                        moodle_timemodified INTEGER NOT NULL,
                        processed_at INTEGER NOT NULL,
                        PRIMARY KEY (course_id, file_identifier)
                    )
                """)
                conn.commit()
        except sqlite3.Error as e:
            logger.error(f"Error ensuring FileTracker table exists: {e}")
            raise FileTrackerError(f"Database table setup failed: {e}") from e

    def is_file_new_or_modified(
        self, course_id: int, file_identifier: str, moodle_timemodified: int
    ) -> bool:
        """
        Checks if a file is new or has been modified since the last processing.
        'file_identifier' can be a filename or a more stable Moodle file ID if available.
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    f"""
                    SELECT moodle_timemodified FROM {self.TABLE_NAME}
                    WHERE course_id = ? AND file_identifier = ?
                    """,
                    (course_id, file_identifier),
                )
                row = cursor.fetchone()
                if row is None:
                    logger.debug(
                        f"File '{file_identifier}' in course {course_id} is new."
                    )
                    return True  # File not found in tracker, so it's new

                last_processed_moodle_ts = row[0]
                if moodle_timemodified > last_processed_moodle_ts:
                    logger.debug(
                        f"File '{file_identifier}' in course {course_id} modified "
                        f"(Moodle ts: {moodle_timemodified} > Tracked ts: {last_processed_moodle_ts})."
                    )
                    return True  # File has been modified in Moodle

                logger.debug(
                    f"File '{file_identifier}' in course {course_id} is unchanged."
                )
                return False  # File is not new and not modified
        except sqlite3.Error as e:
            logger.error(
                f"Error checking file '{file_identifier}' in course {course_id}: {e}"
            )
            # In case of DB error, conservatively assume file needs processing
            return True
        except Exception as e:
            logger.exception(
                f"Unexpected error checking file '{file_identifier}' in course {course_id}: {e}"
            )
            return True

    def mark_file_as_processed(
        self, course_id: int, file_identifier: str, moodle_timemodified: int
    ):
        """Marks a file as processed with its current Moodle modification timestamp."""
        processed_at_ts = int(time.time())
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    f"""
                    INSERT OR REPLACE INTO {self.TABLE_NAME} 
                    (course_id, file_identifier, moodle_timemodified, processed_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (course_id, file_identifier, moodle_timemodified, processed_at_ts),
                )
                conn.commit()
                logger.info(
                    f"Marked file '{file_identifier}' in course {course_id} as processed "
                    f"(Moodle ts: {moodle_timemodified}, Processed at: {processed_at_ts})."
                )
        except sqlite3.Error as e:
            logger.error(
                f"Error marking file '{file_identifier}' in course {course_id} as processed: {e}"
            )
            raise FileTrackerError(f"Failed to mark file as processed: {e}") from e

    def get_processed_files_timestamps(self, course_id: int) -> Dict[str, int]:
        """
        Retrieves a dictionary of processed file identifiers and their Moodle timemodified
        for a given course.
        """
        timestamps: Dict[str, int] = {}
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    f"""
                    SELECT file_identifier, moodle_timemodified FROM {self.TABLE_NAME}
                    WHERE course_id = ?
                    """,
                    (course_id,),
                )
                for row in cursor.fetchall():
                    timestamps[row[0]] = row[1]
            return timestamps
        except sqlite3.Error as e:
            logger.error(
                f"Error retrieving processed files for course {course_id}: {e}"
            )
            return {}  # Return empty dict on error
        except Exception as e:
            logger.exception(
                f"Unexpected error retrieving processed files for course {course_id}: {e}"
            )
            return {}


if __name__ == "__main__":
    # Ensure data directory exists for the test DB
    # This is now handled in BaseConfig, but good for standalone testing.
    # test_db_path = Path(base_config.data_dir) / "test_file_tracker.sqlite"
    # os.makedirs(test_db_path.parent, exist_ok=True)

    print(f"Using FileTracker DB at: {base_config.file_tracker_db_path}")
    # Ensure the path is Path object for the constructor if passing explicitly,
    # though the constructor handles string conversion.
    # For the test, it's good practice to match the type hint if possible.
    test_db_concrete_path = Path(base_config.file_tracker_db_path)
    if test_db_concrete_path.exists():
        test_db_concrete_path.unlink()  # Clean up before test

    tracker = FileTracker(
        db_path=test_db_concrete_path
    )  # Use configured path for testing

    course_id_test = 101
    file1 = "document1.pdf"
    file2 = "document2.docx"

    # Test new file
    print(
        f"\nIs '{file1}' new/modified? {tracker.is_file_new_or_modified(course_id_test, file1, 1678886400)}"
    )
    tracker.mark_file_as_processed(course_id_test, file1, 1678886400)
    print(
        f"Is '{file1}' new/modified after marking? {tracker.is_file_new_or_modified(course_id_test, file1, 1678886400)}"
    )

    # Test modified file
    print(
        f"Is '{file1}' new/modified with new timestamp? {tracker.is_file_new_or_modified(course_id_test, file1, 1678887400)}"
    )
    tracker.mark_file_as_processed(
        course_id_test, file1, 1678887400
    )  # Mark with new timestamp

    # Test another file
    print(
        f"\nIs '{file2}' new/modified? {tracker.is_file_new_or_modified(course_id_test, file2, 1678888000)}"
    )
    tracker.mark_file_as_processed(course_id_test, file2, 1678888000)

    # Get all processed files for the course
    processed = tracker.get_processed_files_timestamps(course_id_test)
    print(f"\nProcessed files for course {course_id_test}: {processed}")

    # Clean up test db file
    # if test_db_path.exists():
    #     test_db_path.unlink()
    # print(f"\nTest DB {test_db_path} removed (if it was created specifically for test).")
    print(f"\nTest complete. Check DB at {base_config.file_tracker_db_path}")
