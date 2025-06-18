import re
import time  # Added for timestamping
from typing import List, Dict, Any, Optional  # Ensure Dict and Any are imported

import psycopg2  # Or psycopg if using version 3+
from pgvector.psycopg2 import register_vector  # Or equivalent for psycopg3
from psycopg2.extras import (
    RealDictCursor,
    execute_values,
)  # Or appropriate cursor for dict results

from src.entrenai.api.models import (
    DocumentChunk,
)  # Assuming this model is still relevant
from src.entrenai.config import PgvectorConfig  # Use the new config
from src.entrenai.config.logger import get_logger

logger = get_logger(__name__)


class PgvectorWrapperError(Exception):
    """Custom exception for PgvectorWrapper errors."""

    pass


class PgvectorWrapper:
    """Wrapper to interact with PostgreSQL with pgvector extension."""

    FILE_TRACKER_TABLE_NAME = "file_tracker"

    def __init__(self, config: PgvectorConfig):
        self.config = config
        self.conn = None
        self.cursor = None
        try:
            if not all(
                [config.host, config.port, config.user, config.password, config.db_name]
            ):
                logger.error("Pgvector connection details missing in configuration.")
                raise PgvectorWrapperError("Pgvector connection details missing.")

            self.conn = psycopg2.connect(
                host=config.host,
                port=config.port,
                user=config.user,
                password=config.password,
                dbname=config.db_name,
            )
            self.cursor = self.conn.cursor(cursor_factory=RealDictCursor)
            register_vector(self.conn)  # Register the vector type
            self.cursor.execute("CREATE EXTENSION IF NOT EXISTS vector;")
            self.conn.commit()
            logger.info(
                f"PgvectorWrapper initialized and connected to {config.host}:{config.port}/{config.db_name}"
            )

            self.ensure_file_tracker_table()  # Ensure the file tracker table exists

        except psycopg2.Error as e:
            logger.error(
                f"Failed to connect to PostgreSQL/pgvector at {config.host}:{config.port}: {e}"
            )
            self.conn = None  # Ensure conn is None if connection failed
            self.cursor = None
            # Do not raise here, allow for attempts to reconnect or handle gracefully
        except Exception as e:  # Catch other potential errors during init
            logger.error(
                f"An unexpected error occurred during PgvectorWrapper initialization: {e}"
            )
            self.conn = None
            self.cursor = None

    @staticmethod
    def _normalize_name_for_table(name: str) -> str:
        """Normalizes a name for use as a PostgreSQL table name."""
        if not name:
            logger.error("Attempted to normalize an empty name for the table.")
            raise ValueError("Course name cannot be empty for generating table name.")

        name_lower = name.lower()
        name_processed = re.sub(r"\s+", "_", name_lower)
        name_processed = re.sub(
            r"[^a-z0-9_]", "", name_processed
        )  # PostgreSQL allows only alphanumeric and underscore
        name_processed = name_processed[
            :50
        ]  # Max table name length is typically 63, give some room for prefix

        if not name_processed:
            logger.error(
                f"Normalized name for '{name}' resulted in empty string. Using fallback."
            )
            raise ValueError(
                f"Course name '{name}' resulted in an empty normalized table name."
            )
        return name_processed

    def get_table_name(self, course_name: str) -> str:
        """Generates the table name for a given course name using the configured prefix."""
        normalized_name = self._normalize_name_for_table(course_name)
        return f"{self.config.collection_prefix}{normalized_name}"  # collection_prefix is now table_prefix

    def ensure_table(self, course_name: str, vector_size: int) -> bool:
        """
        Ensures a table exists for the given course_name. If not, creates it.
        The table will have columns: id (TEXT PRIMARY KEY), document_id (TEXT), text (TEXT), metadata (JSONB), embedding (vector(vector_size)).
        Returns True if the table exists or was created successfully, False otherwise.
        """
        if not self.conn or not self.cursor:
            logger.error("No database connection. Cannot ensure table.")
            return False

        table_name = self.get_table_name(course_name)
        try:
            # Check if table exists
            self.cursor.execute(
                "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = %s);",
                (table_name,),
            )
            if self.cursor.fetchone()["exists"]:
                # Check the dimension of the existing 'embedding' column
                dimension_check_sql = """
                SELECT atttypmod FROM pg_attribute
                WHERE attrelid = %s::regclass
                  AND attname = 'embedding'
                  AND NOT attisdropped;
                """
                self.cursor.execute(dimension_check_sql, (table_name,))
                result = self.cursor.fetchone()
                if result:
                    retrieved_dimension = result.get("atttypmod")
                    if (
                        retrieved_dimension is not None
                        and retrieved_dimension != -1
                        and retrieved_dimension != vector_size
                    ):
                        logger.warning(
                            f"Table '{table_name}' exists but its 'embedding' column dimension ({retrieved_dimension}) "
                            f"does not match the expected dimension ({vector_size}). This may cause issues."
                        )
                else:
                    # This case should ideally not happen if the table exists and has an 'embedding' column
                    logger.warning(
                        f"Could not retrieve dimension for 'embedding' column in existing table '{table_name}'."
                    )

                logger.info(f"Table '{table_name}' already exists.")
                return True

            # Create table
            # Using HNSW index as an example, cosine distance is specified in the query operation.
            create_table_sql = f"""
            CREATE TABLE {table_name} (
                id TEXT PRIMARY KEY,
                course_id TEXT, 
                document_id TEXT,
                text TEXT,
                metadata JSONB,
                embedding vector({vector_size})
            );
            """
            # Note: The 'course_id' field was in DocumentChunk, might be useful to store it explicitly.
            # The original DocumentChunk had 'id', 'course_id', 'document_id', 'text', 'embedding', 'metadata'.
            # Ensure these are mapped correctly.

            self.cursor.execute(create_table_sql)

            # Create an index for approximate nearest neighbor search
            # For cosine distance, use vector_cosine_ops. For L2, vector_l2_ops. For inner product, vector_ip_ops.
            # HNSW index has a limitation of 2000 dimensions, so use halfvec for larger vectors
            # Create an index for approximate nearest neighbor search
            # For cosine distance, use vector_cosine_ops. For L2, vector_l2_ops. For inner product, vector_ip_ops.
            # HNSW index has a limitation of 2000 dimensions, so use halfvec for larger vectors
            # The 'halfvec' type is used within the HNSW index for larger dimensions.
            if vector_size <= 2000:
                create_index_sql = f"CREATE INDEX ON {table_name} USING hnsw (embedding vector_cosine_ops);"
                self.cursor.execute(create_index_sql)
                logger.info(
                    f"Created HNSW index for table '{table_name}' with vector size {vector_size}."
                )
            else:
                # For vectors with more than 2000 dimensions, use halfvec type with HNSW index
                # The syntax is ((embedding::halfvec(vector_size)) halfvec_cosine_ops)
                create_index_sql = f"CREATE INDEX ON {table_name} USING hnsw ((embedding::halfvec({vector_size})) halfvec_cosine_ops);"
                self.cursor.execute(create_index_sql)
                logger.info(
                    f"Created HNSW index with halfvec type for table '{table_name}' with vector size {vector_size}."
                )

            self.conn.commit()
            logger.info(
                f"Table '{table_name}' created successfully with vector size {vector_size}."
            )
            return True
        except psycopg2.Error as e:
            logger.error(f"Error ensuring table '{table_name}': {e}")
            if self.conn:
                self.conn.rollback()  # Rollback on error
            return False
        except Exception as e:
            logger.error(f"Unexpected error ensuring table '{table_name}': {e}")
            if self.conn:
                self.conn.rollback()
            return False

    def delete_file_chunks(self, course_name: str, document_id: str) -> bool:
        """
        Deletes all chunks associated with a specific document_id from the course's table.
        Returns True on success or if no matching rows were found, False on error.
        """
        if not self.conn or not self.cursor:
            logger.error("No database connection. Cannot delete file chunks.")
            return False

        table_name = self.get_table_name(course_name)
        try:
            # Check if table exists to prevent errors on deletion from non-existent table
            self.cursor.execute(
                "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = %s);",
                (table_name,),
            )
            if not self.cursor.fetchone()["exists"]:
                logger.warning(
                    f"Table '{table_name}' does not exist. Cannot delete chunks for document_id '{document_id}'."
                )
                return True  # Or False, depending on desired behavior for non-existent table. True seems more idempotent.

            delete_sql = f"DELETE FROM {table_name} WHERE document_id = %s;"
            self.cursor.execute(delete_sql, (document_id,))
            deleted_rows = self.cursor.rowcount  # Number of rows affected
            self.conn.commit()

            if deleted_rows > 0:
                logger.info(
                    f"Successfully deleted {deleted_rows} chunks for document_id '{document_id}' from table '{table_name}'."
                )
            else:
                logger.info(
                    f"No chunks found for document_id '{document_id}' in table '{table_name}'. Nothing to delete."
                )
            return True
        except psycopg2.Error as e:
            logger.error(
                f"Error deleting chunks for document_id '{document_id}' from table '{table_name}': {e}"
            )
            if self.conn:
                self.conn.rollback()
            return False
        except Exception as e:  # Catch any other unexpected errors
            logger.error(
                f"Unexpected error deleting chunks for document_id '{document_id}' from table '{table_name}': {e}"
            )
            if self.conn:
                self.conn.rollback()
            return False

    def delete_file_from_tracker(self, course_id: int, file_identifier: str) -> bool:
        """
        Deletes a file's record from the file_tracker table.
        Returns True on success or if no matching row was found, False on error.
        """
        if not self.conn or not self.cursor:
            logger.error("No database connection. Cannot delete file from tracker.")
            return False

        try:
            delete_sql = f"""
            DELETE FROM {self.FILE_TRACKER_TABLE_NAME}
            WHERE course_id = %s AND file_identifier = %s;
            """
            self.cursor.execute(delete_sql, (course_id, file_identifier))
            deleted_rows = self.cursor.rowcount
            self.conn.commit()

            if deleted_rows > 0:
                logger.info(
                    f"Successfully deleted file '{file_identifier}' (course_id: {course_id}) from {self.FILE_TRACKER_TABLE_NAME}."
                )
            else:
                logger.info(
                    f"No record found for file '{file_identifier}' (course_id: {course_id}) in {self.FILE_TRACKER_TABLE_NAME}. Nothing to delete."
                )
            return True
        except psycopg2.Error as e:
            logger.error(
                f"Error deleting file '{file_identifier}' (course_id: {course_id}) from {self.FILE_TRACKER_TABLE_NAME}: {e}"
            )
            if self.conn:
                self.conn.rollback()
            return False
        except Exception as e:  # Catch any other unexpected errors
            logger.error(
                f"Unexpected error deleting file '{file_identifier}' (course_id: {course_id}) from {self.FILE_TRACKER_TABLE_NAME}: {e}"
            )
            if self.conn:
                self.conn.rollback()
            return False

    def get_processed_files_timestamps(self, course_id: int) -> Dict[str, int]:
        """
        Retrieves a dictionary of processed file identifiers and their moodle_timemodified timestamps for a given course.
        Returns an empty dictionary on error or if no files are found.
        """
        if not self.conn or not self.cursor:
            logger.error(
                "No database connection. Cannot get processed files timestamps."
            )
            return {}

        try:
            query = f"""
            SELECT file_identifier, moodle_timemodified
            FROM {self.FILE_TRACKER_TABLE_NAME}
            WHERE course_id = %s;
            """
            self.cursor.execute(query, (course_id,))
            results = self.cursor.fetchall()  # List of RealDictRow

            timestamps_map = {
                row["file_identifier"]: row["moodle_timemodified"] for row in results
            }

            if not timestamps_map:
                logger.info(
                    f"No processed files found for course '{course_id}' in tracker."
                )
            else:
                logger.info(
                    f"Retrieved {len(timestamps_map)} processed file timestamps for course '{course_id}'."
                )
            return timestamps_map
        except psycopg2.Error as e:
            logger.error(
                f"Error retrieving processed files timestamps for course '{course_id}': {e}"
            )
            if self.conn:
                self.conn.rollback()
            return {}
        except Exception as e:
            logger.error(
                f"Unexpected error retrieving processed files timestamps for course '{course_id}': {e}"
            )
            if self.conn:
                self.conn.rollback()
            return {}

    def upsert_chunks(self, course_name: str, chunks: List[DocumentChunk]) -> bool:
        """
        Inserts or updates (upserts) document chunks into the specified course's table.
        Assumes DocumentChunk has 'id', 'course_id', 'document_id', 'text', 'embedding', 'metadata'.
        """
        if not self.conn or not self.cursor:
            logger.error("No database connection. Cannot upsert chunks.")
            return False
        if not chunks:
            logger.info("No chunks provided for upsert.")
            return True

        table_name = self.get_table_name(course_name)

        first_valid_embedding_size = self.config.default_vector_size
        valid_chunks_data = []
        for chunk in chunks:
            if chunk.embedding is None:
                logger.warning(
                    f"Chunk with ID '{chunk.id}' (course: {chunk.course_id}, doc: {chunk.document_id}) has no embedding. Skipping."
                )
                continue

            if (
                first_valid_embedding_size == self.config.default_vector_size
            ):  # Try to set it from the first valid chunk
                first_valid_embedding_size = len(chunk.embedding)

            metadata_to_insert = chunk.metadata
            if isinstance(chunk.metadata, dict):
                import json

                metadata_to_insert = json.dumps(chunk.metadata)

            valid_chunks_data.append(
                (
                    chunk.id,
                    str(chunk.course_id),
                    chunk.document_id,
                    chunk.text,
                    metadata_to_insert,
                    chunk.embedding,
                )
            )

        if not valid_chunks_data:
            logger.info(
                f"No valid chunks with embeddings found to upsert into '{table_name}'."
            )
            return True

        if not self.ensure_table(course_name, first_valid_embedding_size):
            logger.error(f"Failed to ensure table '{table_name}' for upserting chunks.")
            return False

        try:
            sql_template = f"""
            INSERT INTO {table_name} (id, course_id, document_id, text, metadata, embedding)
            VALUES %s
            ON CONFLICT (id) DO UPDATE SET
                course_id = EXCLUDED.course_id,
                document_id = EXCLUDED.document_id,
                text = EXCLUDED.text,
                metadata = EXCLUDED.metadata,
                embedding = EXCLUDED.embedding;
            """

            execute_values(self.cursor, sql_template, valid_chunks_data)
            self.conn.commit()

            logger.info(
                f"Successfully batch upserted {len(valid_chunks_data)} chunks into table '{table_name}'."
            )
            return True
        except psycopg2.Error as e:
            logger.error(f"Error batch upserting chunks into table '{table_name}': {e}")
            if self.conn:
                self.conn.rollback()
            return False
        except Exception as e:
            logger.error(
                f"Unexpected error batch upserting chunks into table '{table_name}': {e}"
            )
            if self.conn:
                self.conn.rollback()
            return False

    def search_chunks(
        self,
        course_name: str,
        query_embedding: List[float],
        limit: int = 5,
        ef_search_value: Optional[int] = None,
        # score_threshold: Optional[float] = None, # pgvector uses distance, not score; 0 is perfect match for cosine
    ) -> List[
        Dict[str, Any]
    ]:  # Return type matches Qdrant's ScoredPoint-like structure
        """
        Searches for relevant chunks in the course's table using vector similarity.
        Returns a list of dictionaries, each representing a chunk and including a 'score' (distance).
        For cosine similarity with pgvector: embedding <-> query_embedding gives cosine distance (0=identical, 2=opposite).
        Smaller distance is better.
        """
        if not self.conn or not self.cursor:
            logger.error("No database connection. Cannot search chunks.")
            return []

        table_name = self.get_table_name(course_name)
        try:
            if ef_search_value is not None:
                self.cursor.execute(
                    "SET LOCAL hnsw.ef_search = %s;", (ef_search_value,)
                )
                logger.info(
                    f"Setting hnsw.ef_search = {ef_search_value} for current query in table '{table_name}'."
                )

            # <=> is the cosine distance operator in pgvector
            # For L2 distance, use <->. For inner product, use <#>.
            # Ensure the vector size matches, or this query might fail/be slow.
            # The result of 'embedding <=> %s' is the distance.
            # We select 1 - (embedding <=> %s) to get a similarity score (0 to 1, higher is better for cosine similarity)
            # However, the original Qdrant returned a score where higher was better.
            # Cosine distance (what <=> gives for vector_cosine_ops) is 0 for perfect match, 1 for orthogonal, 2 for opposite.
            # To make it behave like Qdrant's score (higher = better similarity), we can use (1 - cosine_distance).
            # Or, if the original Qdrant score was also a distance, then use it directly. Assuming Qdrant `Distance.COSINE` implies higher score = more similar.
            # pgvector's cosine distance is 1 - cosine_similarity. So distance 0 means similarity 1.
            # We will return the raw distance and let the caller interpret or transform if needed, or transform to similarity here.
            # Let's return 'score' as cosine similarity: (1 - (embedding <=> query_embedding))

            # For cosine similarity with pgvector: embedding <-> query_embedding gives cosine distance (0=identical, 2=opposite).
            # To make it behave like Qdrant's score (higher = better similarity), we can use (1 - cosine_distance).
            # When using halfvec, the casting is required for the comparison.
            query_sql = f"""
            SELECT id, course_id, document_id, text, metadata, (1 - (embedding <=> %s::vector({len(query_embedding)}))) AS score 
            FROM {table_name}
            ORDER BY embedding::halfvec({len(query_embedding)}) <=> %s::halfvec({len(query_embedding)})
            LIMIT %s;
            """
            # query_sql = f"SELECT id, course_id, document_id, text, metadata, embedding <=> %s AS distance FROM {table_name} ORDER BY distance LIMIT %s;"

            self.cursor.execute(query_sql, (query_embedding, query_embedding, limit))
            results = self.cursor.fetchall()  # Returns list of RealDictRow objects

            # Convert RealDictRow to plain dict and adjust structure if needed
            # The original Qdrant `ScoredPoint` had `id`, `score`, `payload`.
            # Here, payload is effectively the 'metadata' column, plus other columns.
            # We should structure the output to be as compatible as possible.

            formatted_results = []
            for row in results:
                formatted_results.append(
                    {
                        "id": row["id"],
                        "score": row["score"],  # This is now cosine similarity (0 to 1)
                        "payload": {  # Reconstruct a payload similar to Qdrant's
                            "course_id": row.get("course_id"),
                            "document_id": row.get("document_id"),
                            "text": row.get("text"),
                            **(
                                row.get("metadata")
                                if isinstance(row.get("metadata"), dict)
                                else {}
                            ),  # Spread metadata if it's a dict
                        },
                    }
                )

            logger.info(
                f"Search in table '{table_name}' found {len(formatted_results)} results."
            )
            return formatted_results
        except psycopg2.Error as e:
            logger.error(f"Error searching in table '{table_name}': {e}")
            if self.conn:
                self.conn.rollback()
            return []
        except Exception as e:
            logger.error(f"Unexpected error searching in table '{table_name}': {e}")
            if self.conn:
                self.conn.rollback()
            return []

    def close_connection(self):
        """Closes the database connection."""
        if self.cursor:
            self.cursor.close()
            self.cursor = None
        if self.conn:
            self.conn.close()
            self.conn = None
            logger.info("PostgreSQL connection closed.")

    def __del__(self):
        """Ensure connection is closed when the object is destroyed."""
        self.close_connection()

    def ensure_file_tracker_table(self):
        """
        Ensures the file_tracker table exists. If not, creates it.
        Schema: course_id (INTEGER), file_identifier (TEXT), moodle_timemodified (BIGINT), 
                content_hash (TEXT), processed_at (BIGINT)
        Primary Key: (course_id, file_identifier)
        """
        if not self.conn or not self.cursor:
            logger.error("No database connection. Cannot ensure file_tracker table.")
            return

        try:
            self.cursor.execute(
                f"SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = '{self.FILE_TRACKER_TABLE_NAME}');"
            )
            table_exists = self.cursor.fetchone()["exists"]
            
            if table_exists:
                # Check if content_hash column exists
                self.cursor.execute(
                    f"""
                    SELECT column_name FROM information_schema.columns 
                    WHERE table_name = '{self.FILE_TRACKER_TABLE_NAME}' 
                    AND column_name = 'content_hash';
                    """
                )
                has_content_hash = bool(self.cursor.fetchone())
                
                if not has_content_hash:
                    # Add content_hash column to existing table
                    alter_sql = f"ALTER TABLE {self.FILE_TRACKER_TABLE_NAME} ADD COLUMN content_hash TEXT;"
                    self.cursor.execute(alter_sql)
                    self.conn.commit()
                    logger.info(f"Added content_hash column to existing '{self.FILE_TRACKER_TABLE_NAME}' table.")
                else:
                    logger.info(f"Table '{self.FILE_TRACKER_TABLE_NAME}' already exists with content_hash column.")
                return

            # Create new table with content_hash column
            create_table_sql = f"""
            CREATE TABLE {self.FILE_TRACKER_TABLE_NAME} (
                course_id INTEGER NOT NULL,
                file_identifier TEXT NOT NULL,
                moodle_timemodified BIGINT NOT NULL,
                content_hash TEXT,
                processed_at BIGINT NOT NULL,
                PRIMARY KEY (course_id, file_identifier)
            );
            """
            self.cursor.execute(create_table_sql)
            self.conn.commit()
            logger.info(f"Table '{self.FILE_TRACKER_TABLE_NAME}' created successfully with content_hash column.")
        except psycopg2.Error as e:
            logger.error(f"Error ensuring table '{self.FILE_TRACKER_TABLE_NAME}': {e}")
            if self.conn:
                self.conn.rollback()
        except Exception as e:
            logger.error(
                f"Unexpected error ensuring table '{self.FILE_TRACKER_TABLE_NAME}': {e}"
            )
            if self.conn:
                self.conn.rollback()

    def is_file_new_or_modified(
        self, course_id: int, file_identifier: str, moodle_timemodified: int, 
        content_hash: Optional[str] = None
    ) -> bool:
        """
        Checks if the file is new or modified compared to the entry in file_tracker.
        If content_hash is provided, also checks if the content has changed.
        Returns True if the file is new, modified, or if an error occurs (conservative).
        """
        if not self.conn or not self.cursor:
            logger.error("No database connection. Cannot check file status.")
            return True  # Conservative: assume new/modified if DB is not available

        try:
            query = f"""
            SELECT moodle_timemodified, content_hash
            FROM {self.FILE_TRACKER_TABLE_NAME}
            WHERE course_id = %s AND file_identifier = %s;
            """
            self.cursor.execute(query, (course_id, file_identifier))
            result = self.cursor.fetchone()

            if result is None:
                logger.info(
                    f"File '{file_identifier}' for course '{course_id}' not found in tracker. Assuming new."
                )
                return True  # File not found, so it's new

            stored_timemodified = result["moodle_timemodified"]
            stored_content_hash = result.get("content_hash")

            # Check if timemodified has changed
            if moodle_timemodified > stored_timemodified:
                logger.info(
                    f"File '{file_identifier}' for course '{course_id}' is modified (new: {moodle_timemodified}, stored: {stored_timemodified})."
                )
                return True  # File is modified

            # If content_hash is provided and stored, compare them
            if content_hash and stored_content_hash:
                if content_hash != stored_content_hash:
                    logger.info(
                        f"File '{file_identifier}' for course '{course_id}' has different content hash. Needs reprocessing."
                    )
                    return True  # Content has changed
                else:
                    logger.info(
                        f"File '{file_identifier}' for course '{course_id}' has same content hash. Skipping reprocessing."
                    )
                    return False  # Content is identical

            logger.info(
                f"File '{file_identifier}' for course '{course_id}' is up-to-date (timestamp: {moodle_timemodified})."
            )
            return False  # File is not modified
        except psycopg2.Error as e:
            logger.error(
                f"Error checking file status for '{file_identifier}' in course '{course_id}': {e}"
            )
            if self.conn:
                self.conn.rollback()
            return True  # Conservative: assume new/modified on error
        except Exception as e:
            logger.error(
                f"Unexpected error checking file status for '{file_identifier}' in course '{course_id}': {e}"
            )
            if self.conn:
                self.conn.rollback()
            return True  # Conservative approach

    def mark_file_as_processed(
        self, course_id: int, file_identifier: str, moodle_timemodified: int,
        content_hash: Optional[str] = None
    ):
        """
        Marks the file as processed by inserting or updating its record in file_tracker.
        """
        if not self.conn or not self.cursor:
            logger.error("No database connection. Cannot mark file as processed.")
            return False

        processed_at_ts = int(time.time())
        try:
            upsert_sql = f"""
            INSERT INTO {self.FILE_TRACKER_TABLE_NAME} (course_id, file_identifier, moodle_timemodified, content_hash, processed_at)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (course_id, file_identifier) DO UPDATE SET
                moodle_timemodified = EXCLUDED.moodle_timemodified,
                content_hash = EXCLUDED.content_hash,
                processed_at = EXCLUDED.processed_at;
            """
            self.cursor.execute(
                upsert_sql,
                (course_id, file_identifier, moodle_timemodified, content_hash, processed_at_ts),
            )
            self.conn.commit()
            logger.info(
                f"Successfully marked file '{file_identifier}' for course '{course_id}' as processed at {processed_at_ts} with moodle_timemodified {moodle_timemodified}."
            )
            return True
        except psycopg2.Error as e:
            logger.error(
                f"Error marking file '{file_identifier}' for course '{course_id}' as processed: {e}"
            )
            if self.conn:
                self.conn.rollback()
            return False
        except Exception as e:
            logger.error(
                f"Unexpected error marking file '{file_identifier}' for course '{course_id}' as processed: {e}"
            )
            if self.conn:
                self.conn.rollback()
            return False
