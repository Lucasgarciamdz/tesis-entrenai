import logging
import os
import traceback
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

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
    prefix="/api/v1/internal",
    tags=["Internal Processing"],
)


class ProcessFileRequest(BaseModel):
    task_id: str
    course_id: int
    course_name_for_pgvector: str
    moodle_file_info: dict
    download_dir_str: str
    ai_provider_config: dict
    pgvector_config_dict: dict
    moodle_config_dict: dict
    base_config_dict: dict


@router.post("/process-file")
async def process_file_endpoint(request: ProcessFileRequest):
    """
    Endpoint interno para procesar archivos de Moodle.
    Este endpoint recibe requests de Celery y hace todo el procesamiento real.
    """
    filename = request.moodle_file_info.get("filename")
    file_url = request.moodle_file_info.get("fileurl")
    timemodified = request.moodle_file_info.get("timemodified")
    task_id = request.task_id

    logger.info(f"Task ID: {task_id} - Starting processing for file: {filename} from course_id: {request.course_id}")

    pgvector_db = None

    try:
        # 1. Instantiate MoodleClient
        m_config = MoodleConfig(**request.moodle_config_dict)
        moodle_client = MoodleClient(config=m_config)

        # 2. Instantiate PgvectorWrapper
        pv_config = PgvectorConfig(**request.pgvector_config_dict)
        pgvector_db = PgvectorWrapper(config=pv_config)

        # 3. Instantiate FileProcessor
        file_processor = FileProcessor()

        # 4. Instantiate AI Wrapper
        b_config = BaseConfig(**request.base_config_dict)

        ai_provider = request.ai_provider_config.get("selected_provider", "ollama")
        if ai_provider == "gemini":
            g_config = GeminiConfig(**request.ai_provider_config.get("gemini", {}))
            g_config.data_dir = b_config.data_dir
            ai_client = GeminiWrapper(config=g_config)
        else:
            o_config = OllamaConfig(**request.ai_provider_config.get("ollama", {}))
            o_config.data_dir = b_config.data_dir
            ai_client = OllamaWrapper(config=o_config)

        # 5. Instantiate EmbeddingManager
        embedding_manager = EmbeddingManager(ai_wrapper=ai_client)

        # 6. Create Path and ensure it exists
        if not os.path.isabs(request.download_dir_str):
            download_dir_path = Path(os.path.join(b_config.data_dir, request.download_dir_str))
        else:
            download_dir_path = Path(request.download_dir_str)

        logger.info(f"Task ID: {task_id} - Creating download directory at: {download_dir_path}")
        download_dir_path.mkdir(parents=True, exist_ok=True)

        # 7. Download file
        logger.info(f"Task ID: {task_id} - Downloading file: {filename} from {file_url}")
        downloaded_path = moodle_client.download_file(file_url, download_dir_path, filename)
        if not downloaded_path:
            raise FileNotFoundError(f"No se pudo descargar el archivo: {filename}")
        logger.info(f"Task ID: {task_id} - File downloaded to: {downloaded_path}")

        # 8. Extract text
        logger.info(f"Task ID: {task_id} - Processing file: {downloaded_path}")
        raw_text = file_processor.process_file(downloaded_path)
        if raw_text is None:
            raise ValueError(f"No se pudo extraer texto del archivo: {filename}")
        logger.info(f"Task ID: {task_id} - Text extracted successfully from: {filename}")

        # 9. Format to Markdown
        markdown_save_dir = Path(b_config.data_dir) / "markdown_files" / str(request.course_id)
        markdown_save_dir.mkdir(parents=True, exist_ok=True)
        markdown_file_path = markdown_save_dir / f"{Path(filename).stem}.md"

        logger.info(f"Task ID: {task_id} - Formatting text to Markdown for: {filename}")
        markdown_text = ai_client.format_to_markdown(raw_text, save_path=markdown_file_path)
        if not markdown_text:
            raise RuntimeError(f"No se pudo formatear el texto a markdown para: {filename}")
        logger.info(f"Task ID: {task_id} - Markdown generated and saved to: {markdown_file_path}")

        # 10. Split text
        logger.info(f"Task ID: {task_id} - Splitting Markdown text for: {filename}")
        chunks = embedding_manager.split_text_into_chunks(markdown_text)
        if not chunks:
            logger.warning(f"Task ID: {task_id} - No chunks were generated for file: {filename}. Skipping embedding.")
            pgvector_db.mark_file_as_processed(request.course_id, filename, timemodified)
            return {
                "filename": filename,
                "status": "success_no_chunks",
                "chunks_upserted": 0,
                "task_id": task_id,
            }

        logger.info(f"Task ID: {task_id} - Text split into {len(chunks)} chunks for: {filename}")

        # 11. Contextualize Chunks
        logger.info(f"Task ID: {task_id} - Contextualizing {len(chunks)} chunks for: {filename}")
        contextualized_chunks = []
        for i, chunk_text in enumerate(chunks):
            contextualized_text = embedding_manager.contextualize_chunk(
                chunk_text, filename, f"chunk_{i + 1}"
            )
            contextualized_chunks.append(contextualized_text)
        logger.info(f"Task ID: {task_id} - Contextualized {len(contextualized_chunks)} chunks for: {filename}")

        # 12. Generate Embeddings
        logger.info(f"Task ID: {task_id} - Generating embeddings for {len(contextualized_chunks)} chunks for: {filename}")
        chunk_embeddings = embedding_manager.generate_embeddings_for_chunks(contextualized_chunks)
        logger.info(f"Task ID: {task_id} - Embeddings generated for {len(chunk_embeddings)} chunks for: {filename}")

        # 13. Prepare Chunks for DB
        logger.info(f"Task ID: {task_id} - Preparing document chunks for DB for: {filename}")
        db_chunks = embedding_manager.prepare_document_chunks_for_vector_db(
            document_id=f"{request.course_id}_{filename}",
            document_title=filename,
            source_filename=filename,
            chunks_text=contextualized_chunks,
            embeddings=chunk_embeddings,
            course_id=request.course_id,
        )
        logger.info(f"Task ID: {task_id} - Prepared {len(db_chunks)} chunks for DB for: {filename}")

        # 14. Upsert Chunks
        if db_chunks:
            logger.info(f"Task ID: {task_id} - Upserting {len(db_chunks)} chunks to Pgvector for: {filename}")
            pgvector_db.upsert_chunks(request.course_name_for_pgvector, db_chunks)
            logger.info(f"Task ID: {task_id} - Successfully upserted chunks for: {filename}")
        else:
            logger.warning(f"Task ID: {task_id} - No document chunks to upsert for file: {filename}")

        # 15. Mark as Processed
        logger.info(f"Task ID: {task_id} - Marking file as processed: {filename}")
        pgvector_db.mark_file_as_processed(request.course_id, filename, timemodified)
        logger.info(f"Task ID: {task_id} - File marked as processed: {filename}")

        # 16. Cleanup (Optional: Delete downloaded file)
        try:
            downloaded_path.unlink(missing_ok=True)
            logger.info(f"Task ID: {task_id} - Cleaned up downloaded file: {downloaded_path}")
        except Exception as e_cleanup:
            logger.warning(f"Task ID: {task_id} - Could not delete file {downloaded_path}. Error: {e_cleanup}")

        return {
            "filename": filename,
            "status": "success",
            "chunks_upserted": len(db_chunks) if db_chunks else 0,
            "task_id": task_id,
        }

    except Exception as e:
        logger.error(f"Task ID: {task_id} - Error processing file {filename} in course {request.course_id}: {e}\n{traceback.format_exc()}")
        raise HTTPException(
            status_code=500,
            detail={
                "filename": filename,
                "status": "error",
                "error_message": str(e),
                "task_id": task_id,
            }
        )
    finally:
        if pgvector_db:
            try:
                logger.info(f"Task ID: {task_id} - Closing Pgvector connection for file: {filename}")
                pgvector_db.close_connection()
                logger.info(f"Task ID: {task_id} - Pgvector connection closed for file: {filename}")
            except Exception as e_close:
                logger.error(f"Task ID: {task_id} - Error closing Pgvector connection for file: {filename}. Error: {e_close}", exc_info=True)
