import logging
import os
import traceback
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

# Assuming your models are in src.entrenai.api.models
from src.entrenai.api.models import FileProcessingRequest, FileProcessingResponse, MoodleFile

# Configurations - these will be loaded by the FastAPI app, typically via environment variables
# For now, we'll assume they are available or passed correctly.
# Direct config imports might be tricky if they rely on global state not set up at import time in this model.
# Instead, we'll rely on them being passed in the request or accessed via app state/dependencies.
from src.entrenai.config.config import (
    MoodleConfig,
    PgvectorConfig,
    OllamaConfig,
    GeminiConfig,
    BaseConfig,
)
from src.entrenai.core.ai.embedding_manager import EmbeddingManager
from src.entrenai.core.ai.gemini_wrapper import GeminiWrapper
from src.entrenai.core.ai.ollama_wrapper import OllamaWrapper
from src.entrenai.core.clients.moodle_client import MoodleClient
from src.entrenai.core.db.pgvector_wrapper import PgvectorWrapper
from src.entrenai.core.files.file_processor import FileProcessor

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/processing",
    tags=["File Processing"],
    responses={404: {"description": "Not found"}},
)

# This is where the core logic of 'process_moodle_file_task' will be adapted.
# For now, it's a placeholder.
@router.post("/process_file", response_model=FileProcessingResponse)
async def process_file_endpoint(request: FileProcessingRequest):
    # The actual processing logic will be implemented here.
    # This will involve:
    # 1. Reconstructing config objects from dictionaries in the request.
    # 2. Instantiating clients (Moodle, Pgvector, AI).
    # 3. Downloading the file.
    # 4. Processing the file (text extraction, markdown conversion).
    # 5. Generating embeddings.
    # 6. Storing chunks in Pgvector.
    # 7. Handling errors and returning an appropriate response.

    filename = request.moodle_file_info.filename
    logger.info(f"Received request to process file: {filename} for course_id: {request.course_id}")

    # Placeholder response:
    # return FileProcessingResponse(
    #     filename=filename,
    #     status="pending",
    #     message="Processing not yet implemented in API endpoint."
    # )

    # The following is the adapted logic from the original Celery task:
    # process_moodle_file_task

    pgvector_db = None  # Initialize to None

    try:
        # 1. Reconstruct Config objects from dictionaries
        m_config = MoodleConfig(**request.moodle_config_dict)
        pv_config = PgvectorConfig(**request.pgvector_config_dict)
        b_config = BaseConfig(**request.base_config_dict) # Crucial for DATA_DIR

        # 2. Instantiate MoodleClient
        moodle_client = MoodleClient(config=m_config)

        # 3. Instantiate PgvectorWrapper
        pgvector_db = PgvectorWrapper(config=pv_config)

        # 4. Instantiate FileProcessor
        file_processor = FileProcessor()

        # 5. Instantiate AI Wrapper
        ai_provider = request.ai_provider_config.get("selected_provider", "ollama")
        if ai_provider == "gemini":
            g_config_dict = request.ai_provider_config.get("gemini", {})
            g_config = GeminiConfig(**g_config_dict)
            g_config.data_dir = b_config.data_dir # Ensure data_dir is set
            ai_client = GeminiWrapper(config=g_config)
        else:  # Default to Ollama
            o_config_dict = request.ai_provider_config.get("ollama", {})
            o_config = OllamaConfig(**o_config_dict)
            o_config.data_dir = b_config.data_dir # Ensure data_dir is set
            ai_client = OllamaWrapper(config=o_config)

        # 6. Instantiate EmbeddingManager
        embedding_manager = EmbeddingManager(ollama_wrapper=ai_client) # Assuming ollama_wrapper can be any AI client

        # 7. Determine absolute download path using BaseConfig.data_dir from Fastapi app
        # request.download_dir_str is relative to DATA_DIR
        # DATA_DIR for Fastapi app will be /app/data as configured in its Dockerfile and docker-compose
        download_dir_path = Path(b_config.data_dir) / request.download_dir_str

        logger.info(f"API Endpoint - Creating download directory at: {download_dir_path}")
        download_dir_path.mkdir(parents=True, exist_ok=True)

        # 8. Download file
        file_url = request.moodle_file_info.fileurl
        timemodified = request.moodle_file_info.timemodified
        logger.info(f"API Endpoint - Downloading file: {filename} from {file_url}")
        downloaded_path = moodle_client.download_file(
            str(file_url), download_dir_path, filename # Ensure file_url is string
        )
        if not downloaded_path:
            raise FileNotFoundError(f"API Endpoint - No se pudo descargar el archivo: {filename}")
        logger.info(f"API Endpoint - File downloaded to: {downloaded_path}")

        # 9. Extract text
        logger.info(f"API Endpoint - Processing file: {downloaded_path}")
        raw_text = file_processor.process_file(downloaded_path)
        if raw_text is None:
            raise ValueError(f"API Endpoint - No se pudo extraer texto del archivo: {filename}")
        logger.info(f"API Endpoint - Text extracted successfully from: {filename}")

        # 10. Format to Markdown
        markdown_save_dir = Path(b_config.data_dir) / "markdown_files" / str(request.course_id)
        markdown_save_dir.mkdir(parents=True, exist_ok=True)
        markdown_file_path = markdown_save_dir / f"{Path(filename).stem}.md"
        logger.info(f"API Endpoint - Formatting text to Markdown for: {filename}")
        markdown_text = ai_client.format_to_markdown(raw_text, save_path=markdown_file_path)
        if not markdown_text:
            raise RuntimeError(f"API Endpoint - No se pudo formatear el texto a markdown para: {filename}")
        logger.info(f"API Endpoint - Markdown generated and saved to: {markdown_file_path}")

        # 11. Split text
        logger.info(f"API Endpoint - Splitting Markdown text for: {filename}")
        chunks = embedding_manager.split_text_into_chunks(markdown_text)
        if not chunks:
            logger.warning(f"API Endpoint - No chunks were generated for file: {filename}. Skipping embedding.")
            pgvector_db.mark_file_as_processed(request.course_id, filename, timemodified)
            # Cleanup downloaded file
            try:
                downloaded_path.unlink(missing_ok=True)
                logger.info(f"API Endpoint - Cleaned up downloaded file: {downloaded_path}")
            except Exception as e_cleanup:
                logger.warning(f"API Endpoint - Could not delete file {downloaded_path}. Error: {e_cleanup}")
            return FileProcessingResponse(
                filename=filename,
                status="success_no_chunks",
                message="File processed, but no text chunks were generated.",
                chunks_upserted=0,
            )
        logger.info(f"API Endpoint - Text split into {len(chunks)} chunks for: {filename}")

        # 12. Contextualize Chunks
        logger.info(f"API Endpoint - Contextualizing {len(chunks)} chunks for: {filename}")
        contextualized_chunks = []
        for i, chunk_text in enumerate(chunks):
            contextualized_text = embedding_manager.contextualize_chunk(
                chunk_text, filename, f"chunk_{i + 1}"
            )
            contextualized_chunks.append(contextualized_text)
        logger.info(f"API Endpoint - Contextualized {len(contextualized_chunks)} chunks for: {filename}")

        # 13. Generate Embeddings
        logger.info(f"API Endpoint - Generating embeddings for {len(contextualized_chunks)} chunks for: {filename}")
        chunk_embeddings = embedding_manager.generate_embeddings_for_chunks(contextualized_chunks)
        logger.info(f"API Endpoint - Embeddings generated for {len(chunk_embeddings)} chunks for: {filename}")

        # 14. Prepare Chunks for DB
        logger.info(f"API Endpoint - Preparing document chunks for DB for: {filename}")
        db_chunks = embedding_manager.prepare_document_chunks_for_vector_db(
            document_id=f"{request.course_id}_{filename}",
            document_title=filename,
            source_filename=filename,
            chunks_text=contextualized_chunks,
            embeddings=chunk_embeddings,
            course_id=request.course_id,
        )
        logger.info(f"API Endpoint - Prepared {len(db_chunks)} chunks for DB for: {filename}")

        # 15. Upsert Chunks
        if db_chunks:
            logger.info(f"API Endpoint - Upserting {len(db_chunks)} chunks to Pgvector for: {filename}")
            pgvector_db.upsert_chunks(request.course_name_for_pgvector, db_chunks)
            logger.info(f"API Endpoint - Successfully upserted chunks for: {filename}")
        else:
            logger.warning(f"API Endpoint - No document chunks to upsert for file: {filename}")

        # 16. Mark as Processed
        logger.info(f"API Endpoint - Marking file as processed: {filename}")
        pgvector_db.mark_file_as_processed(request.course_id, filename, timemodified)
        logger.info(f"API Endpoint - File marked as processed: {filename}")

        # 17. Cleanup downloaded file
        try:
            downloaded_path.unlink(missing_ok=True)
            logger.info(f"API Endpoint - Cleaned up downloaded file: {downloaded_path}")
        except Exception as e_cleanup:
            logger.warning(f"API Endpoint - Could not delete file {downloaded_path}. Error: {e_cleanup}")

        return FileProcessingResponse(
            filename=filename,
            status="success",
            message="File processed successfully.",
            chunks_upserted=len(db_chunks) if db_chunks else 0,
        )

    except FileNotFoundError as e:
        logger.error(f"API Endpoint - File not found error for {filename}: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        logger.error(f"API Endpoint - Value error processing {filename}: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        logger.error(f"API Endpoint - Runtime error processing {filename}: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.error(
            f"API Endpoint - Unexpected error processing file {filename} in course {request.course_id}: {e}\n{traceback.format_exc()}"
        )
        # Return a generic error response
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {str(e)}")
    finally:
        if pgvector_db:
            try:
                logger.info(f"API Endpoint - Closing Pgvector connection for file: {filename}")
                pgvector_db.close_connection()
                logger.info(f"API Endpoint - Pgvector connection closed for file: {filename}")
            except Exception as e_close:
                logger.error(
                    f"API Endpoint - Error closing Pgvector connection for file: {filename}. Error: {e_close}",
                    exc_info=True,
                )
