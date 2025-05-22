import logging
from pathlib import Path
import traceback # For detailed error logging

from src.entrenai.celery_app import app # Import the Celery app instance
from src.entrenai.core.ai_wrapper_ollama import OllamaWrapper
from src.entrenai.core.ai_wrapper_gemini import GeminiWrapper
from src.entrenai.core.moodle_client import MoodleClient
from src.entrenai.core.file_processor import FileProcessor
from src.entrenai.core.embedding_manager import EmbeddingManager
from src.entrenai.db.pgvector_wrapper import PgvectorWrapper
from src.entrenai.config.config import (
    MoodleConfig,
    PgvectorConfig,
    OllamaConfig,
    GeminiConfig,
    BaseConfig,
)
from src.entrenai.db.models import MoodleFile # For type hinting if reconstructing

logger = logging.getLogger(__name__)


@app.task(bind=True, name="entrenai.core.tasks.process_moodle_file_task")
def process_moodle_file_task(
    self, # Bound task instance
    course_id: int,
    course_name_for_pgvector: str,
    moodle_file_info: dict, # MoodleFile.model_dump()
    download_dir_str: str,
    ai_provider_config: dict,
    pgvector_config_dict: dict,
    moodle_config_dict: dict,
    base_config_dict: dict, # Added for data_dir access
):
    """
    Celery task to download, process, and store a Moodle file and its embeddings.
    """
    filename = moodle_file_info.get("filename")
    file_url = moodle_file_info.get("fileurl")
    timemodified = moodle_file_info.get("timemodified")

    logger.info(
        f"Task ID: {self.request.id} - Starting processing for file: {filename} from course_id: {course_id}"
    )

    pgvector_db = None  # Initialize to None

    try:
        # 1. Reconstruct MoodleFile (optional, can use dict directly)
        # moodle_file = MoodleFile(**moodle_file_info)

        # 2. Instantiate MoodleClient
        m_config = MoodleConfig(**moodle_config_dict)
        moodle_client = MoodleClient(config=m_config) # HTTP client, typically no explicit close needed per task

        # 3. Instantiate PgvectorWrapper
        pv_config = PgvectorConfig(**pgvector_config_dict)
        pgvector_db = PgvectorWrapper(config=pv_config) # This is the one we need to close

        # 4. Instantiate FileProcessor
        file_processor = FileProcessor() # No explicit close needed

        # 5. Instantiate AI Wrapper
        # BaseConfig is needed for data_dir which might be used by AI wrappers for saving intermediate files
        b_config = BaseConfig(**base_config_dict)
        
        ai_provider = ai_provider_config.get("selected_provider", "ollama") # Default to ollama if not specified
        if ai_provider == "gemini":
            g_config = GeminiConfig(**ai_provider_config.get("gemini", {}))
            # Ensure base_config.data_dir is available if GeminiWrapper needs it
            g_config.data_dir = b_config.data_dir 
            ai_client = GeminiWrapper(config=g_config)
        else: # Default to Ollama
            o_config = OllamaConfig(**ai_provider_config.get("ollama", {}))
            # Ensure base_config.data_dir is available if OllamaWrapper needs it
            o_config.data_dir = b_config.data_dir
            ai_client = OllamaWrapper(config=o_config)


        # 6. Instantiate EmbeddingManager
        embedding_manager = EmbeddingManager(ai_wrapper=ai_client)

        # 7. Create Path and ensure it exists
        download_dir_path = Path(download_dir_str)
        download_dir_path.mkdir(parents=True, exist_ok=True)

        # 8. Log start (already done)

        # 9. Download file
        logger.info(f"Task ID: {self.request.id} - Downloading file: {filename} from {file_url}")
        downloaded_path = moodle_client.download_file(
            file_url, download_dir_path, filename
        )
        if not downloaded_path:
            raise Exception(f"Failed to download file: {filename}")
        logger.info(f"Task ID: {self.request.id} - File downloaded to: {downloaded_path}")

        # 10. Extract text
        logger.info(f"Task ID: {self.request.id} - Processing file: {downloaded_path}")
        raw_text, _ = file_processor.process_file(downloaded_path) # Assuming error handling inside or returns None
        if raw_text is None:
            raise Exception(f"Failed to extract text from file: {filename}")
        logger.info(f"Task ID: {self.request.id} - Text extracted successfully from: {filename}")

        # 11. Format to Markdown
        # Define save_path for markdown file based on base_config.data_dir or a sub-directory
        markdown_save_dir = Path(b_config.data_dir) / "markdown_files" / str(course_id)
        markdown_save_dir.mkdir(parents=True, exist_ok=True)
        markdown_file_path = markdown_save_dir / f"{Path(filename).stem}.md"

        logger.info(f"Task ID: {self.request.id} - Formatting text to Markdown for: {filename}")
        markdown_text = ai_client.format_to_markdown(raw_text, save_path=markdown_file_path)
        if not markdown_text:
            raise Exception(f"Failed to format text to markdown for: {filename}")
        logger.info(f"Task ID: {self.request.id} - Markdown generated and saved to: {markdown_file_path}")

        # 12. Split text
        logger.info(f"Task ID: {self.request.id} - Splitting Markdown text for: {filename}")
        chunks = embedding_manager.split_text_into_chunks(markdown_text)
        if not chunks:
            logger.warning(f"Task ID: {self.request.id} - No chunks were generated for file: {filename}. Skipping embedding.")
            # Mark as processed even if no chunks, to avoid reprocessing empty/irrelevant files
            pgvector_db.mark_file_as_processed(course_id, filename, timemodified)
            return {"filename": filename, "status": "success_no_chunks", "chunks_upserted": 0}

        logger.info(f"Task ID: {self.request.id} - Text split into {len(chunks)} chunks for: {filename}")

        # 13. Contextualize Chunks
        logger.info(f"Task ID: {self.request.id} - Contextualizing {len(chunks)} chunks for: {filename}")
        contextualized_chunks = []
        for i, chunk_text in enumerate(chunks):
            # TODO: Determine if a more specific chunk_id or reference is needed
            contextualized_text = embedding_manager.contextualize_chunk(
                text_chunk=chunk_text,
                file_name=filename,
                # chunk_id=f"chunk_{i+1}" # Optional: if your method uses it
            )
            contextualized_chunks.append(contextualized_text)
        logger.info(f"Task ID: {self.request.id} - Contextualized {len(contextualized_chunks)} chunks for: {filename}")

        # 14. Generate Embeddings
        logger.info(f"Task ID: {self.request.id} - Generating embeddings for {len(contextualized_chunks)} chunks for: {filename}")
        chunk_embeddings = embedding_manager.generate_embeddings_for_chunks(
            contextualized_chunks
        )
        logger.info(f"Task ID: {self.request.id} - Embeddings generated for {len(chunk_embeddings)} chunks for: {filename}")

        # 15. Prepare Chunks for DB
        # Assuming MoodleFile object might be needed here, or its relevant fields
        # For simplicity, passing filename and other details directly.
        # The MoodleFile model itself is not passed to avoid serialization issues with Pydantic models in Celery.
        file_metadata_for_chunks = {
            "file_name": filename,
            "file_path": str(downloaded_path), # Or a more persistent URL if applicable
            "course_id": str(course_id), # Ensure type consistency if DB expects string
            "last_modified": str(timemodified), # Ensure type consistency
            # Add any other relevant metadata from moodle_file_info
        }
        logger.info(f"Task ID: {self.request.id} - Preparing document chunks for DB for: {filename}")
        db_chunks = embedding_manager.prepare_document_chunks_for_vector_db(
            course_id=course_id, # course_id is int
            file_info=moodle_file_info, # Pass the original dict
            chunks_text=contextualized_chunks,
            embeddings_vectors=chunk_embeddings,
        )
        logger.info(f"Task ID: {self.request.id} - Prepared {len(db_chunks)} chunks for DB for: {filename}")

        # 16. Upsert Chunks
        if db_chunks:
            logger.info(f"Task ID: {self.request.id} - Upserting {len(db_chunks)} chunks to Pgvector for: {filename}")
            pgvector_db.upsert_chunks(course_name_for_pgvector, db_chunks)
            logger.info(f"Task ID: {self.request.id} - Successfully upserted chunks for: {filename}")
        else:
            logger.warning(f"Task ID: {self.request.id} - No document chunks to upsert for file: {filename}")


        # 17. Mark as Processed
        logger.info(f"Task ID: {self.request.id} - Marking file as processed: {filename}")
        pgvector_db.mark_file_as_processed(course_id, filename, timemodified)
        logger.info(f"Task ID: {self.request.id} - File marked as processed: {filename}")

        # 18. Cleanup (Optional: Delete downloaded file)
        try:
            downloaded_path.unlink(missing_ok=True) # missing_ok=True for Python 3.8+
            logger.info(f"Task ID: {self.request.id} - Cleaned up downloaded file: {downloaded_path}")
        except Exception as e_cleanup:
            logger.warning(
                f"Task ID: {self.request.id} - Could not delete file {downloaded_path}. Error: {e_cleanup}"
            )
        
        return {
            "filename": filename,
            "status": "success",
            "chunks_upserted": len(db_chunks) if db_chunks else 0,
            "task_id": self.request.id,
        }

    except Exception as e:
        logger.error(
            f"Task ID: {self.request.id} - Error processing file {filename} in course {course_id}: {e}\n{traceback.format_exc()}"
        )
        # Optionally, you could try to mark as error in DB, but avoid complex DB logic in error path
        return {
            "filename": filename,
            "status": "error",
            "error_message": str(e),
            "task_id": self.request.id,
        }
    finally:
        if pgvector_db:
            try:
                logger.info(f"Task ID: {self.request.id} - Closing Pgvector connection for file: {filename}")
                pgvector_db.close_connection()
                logger.info(f"Task ID: {self.request.id} - Pgvector connection closed for file: {filename}")
            except Exception as e_close:
                logger.error(
                    f"Task ID: {self.request.id} - Error closing Pgvector connection for file: {filename}. Error: {e_close}",
                    exc_info=True
                )
        # MoodleClient and AI Wrappers using requests/aiohttp typically don't need explicit close here
        # as their sessions are managed by the instance lifecycle or underlying libraries.
