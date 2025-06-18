import logging
from typing import Union

from fastapi import APIRouter, HTTPException

from src.entrenai.api.models import FileProcessingRequest, FileProcessingResponse
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
from src.entrenai.core.services.file_processing_service import FileProcessingService

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/processing",
    tags=["File Processing"],
    responses={404: {"description": "Not found"}},
)

@router.post("/process_file", response_model=FileProcessingResponse)
async def process_file_endpoint(request: FileProcessingRequest):
    """
    Process a single file through the complete AI pipeline.
    This endpoint is called by Celery tasks to perform the heavy processing.
    """
    filename = request.moodle_file_info.filename
    logger.info(f"Processing file: {filename} for course {request.course_id}")

    pgvector_db = None
    try:
        # Reconstruct config objects from request
        base_config = BaseConfig(**request.base_config_dict)
        moodle_config = MoodleConfig(**request.moodle_config_dict)
        pgvector_config = PgvectorConfig(**request.pgvector_config_dict)
        
        # Initialize clients
        moodle_client = MoodleClient(config=moodle_config)
        pgvector_db = PgvectorWrapper(config=pgvector_config)
        file_processor = FileProcessor()
        
        # Initialize AI wrapper based on provider
        ai_provider = request.ai_provider_config.get("selected_provider", "ollama")
        ai_client: Union[OllamaWrapper, GeminiWrapper]
        
        if ai_provider == "gemini":
            gemini_config = GeminiConfig(**request.ai_provider_config.get("gemini", {}))
            gemini_config.data_dir = base_config.data_dir
            ai_client = GeminiWrapper(config=gemini_config)
        else:
            ollama_config = OllamaConfig(**request.ai_provider_config.get("ollama", {}))
            ollama_config.data_dir = base_config.data_dir
            ai_client = OllamaWrapper(config=ollama_config)
        
        # Initialize embedding manager with configured chunk sizes
        embedding_manager = EmbeddingManager(
            ollama_wrapper=ai_client,
            default_chunk_size=base_config.chunk_size,
            default_chunk_overlap=base_config.chunk_overlap
        )
        
        # Create and use file processing service
        processing_service = FileProcessingService(
            moodle_client=moodle_client,
            pgvector_wrapper=pgvector_db,
            file_processor=file_processor,
            ai_wrapper=ai_client,
            embedding_manager=embedding_manager,
            config=base_config
        )
        
        # Process the file
        result = processing_service.process_single_file(
            course_id=request.course_id,
            course_name_for_pgvector=request.course_name_for_pgvector,
            moodle_file_info=request.moodle_file_info.model_dump(),
            download_dir_str=request.download_dir_str
        )
        
        logger.info(f"File {filename} processed successfully")
        return result
        
    except Exception as e:
        logger.error(f"Error processing file {filename}: {e}")
        raise HTTPException(status_code=500, detail=f"Error processing file: {str(e)}")
    finally:
        if pgvector_db:
            try:
                pgvector_db.close_connection()
            except Exception as e_close:
                logger.error(f"Error closing database connection: {e_close}")
