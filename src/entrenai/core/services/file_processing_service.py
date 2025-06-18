import hashlib
from pathlib import Path
from typing import Tuple, Union

from src.entrenai.api.models import FileProcessingResponse
from src.entrenai.config import BaseConfig
from src.entrenai.config.logger import get_logger
from src.entrenai.core.ai.embedding_manager import EmbeddingManager
from src.entrenai.core.ai.gemini_wrapper import GeminiWrapper
from src.entrenai.core.ai.ollama_wrapper import OllamaWrapper
from src.entrenai.core.clients.moodle_client import MoodleClient
from src.entrenai.core.db.pgvector_wrapper import PgvectorWrapper
from src.entrenai.core.files.file_processor import FileProcessor

logger = get_logger(__name__)


class FileProcessingService:
    """Service for processing individual files through the complete pipeline."""
    
    def __init__(
        self,
        moodle_client: MoodleClient,
        pgvector_wrapper: PgvectorWrapper,
        file_processor: FileProcessor,
        ai_wrapper: Union[OllamaWrapper, GeminiWrapper],
        embedding_manager: EmbeddingManager,
        config: BaseConfig
    ):
        self.moodle = moodle_client
        self.pgvector_db = pgvector_wrapper
        self.file_processor = file_processor
        self.ai_wrapper = ai_wrapper
        self.embedding_manager = embedding_manager
        self.config = config

    def process_single_file(
        self,
        course_id: int,
        course_name_for_pgvector: str,
        moodle_file_info: dict,
        download_dir_str: str
    ) -> FileProcessingResponse:
        """
        Process a single file through the complete pipeline.
        """
        filename = moodle_file_info.get("filename", "unknown_file")
        file_url = moodle_file_info.get("fileurl")
        timemodified = moodle_file_info.get("timemodified")
        
        logger.info(f"Processing file '{filename}' for course {course_id}")
        
        try:
            # Create download directory
            download_dir_path = Path(self.config.data_dir) / download_dir_str
            download_dir_path.mkdir(parents=True, exist_ok=True)
            
            # Download file and calculate content hash
            downloaded_path, content_hash = self._download_and_hash_file(
                file_url, download_dir_path, filename
            )
            
            # Check if file needs processing based on content hash
            if not self.pgvector_db.is_file_new_or_modified(
                course_id, filename, timemodified, content_hash
            ):
                logger.info(f"File '{filename}' already processed with same content. Skipping.")
                self._cleanup_downloaded_file(downloaded_path)
                return FileProcessingResponse(
                    filename=filename,
                    status="already_processed",
                    message="File already processed with same content hash.",
                    chunks_upserted=0,
                )
            
            # Extract text and convert to markdown
            markdown_text = self._extract_and_format_to_markdown(downloaded_path)
            if not markdown_text:
                logger.warning(f"No markdown text generated for file '{filename}'. Skipping.")
                self.pgvector_db.mark_file_as_processed(course_id, filename, timemodified, content_hash)
                self._cleanup_downloaded_file(downloaded_path)
                return FileProcessingResponse(
                    filename=filename,
                    status="success_no_content",
                    message="File processed but no content extracted.",
                    chunks_upserted=0,
                )
            
            # Generate and store embeddings
            chunks_upserted = self._generate_and_store_embeddings(
                course_id, course_name_for_pgvector, filename, markdown_text
            )
            
            # Mark file as processed
            self.pgvector_db.mark_file_as_processed(course_id, filename, timemodified, content_hash)
            
            # Cleanup
            self._cleanup_downloaded_file(downloaded_path)
            
            logger.info(f"File '{filename}' processed successfully with {chunks_upserted} chunks")
            return FileProcessingResponse(
                filename=filename,
                status="success",
                message="File processed successfully.",
                chunks_upserted=chunks_upserted,
            )
            
        except Exception as e:
            logger.error(f"Error processing file '{filename}': {e}")
            # Try to cleanup on error
            try:
                downloaded_path = download_dir_path / filename
                self._cleanup_downloaded_file(downloaded_path)
            except:
                pass
            raise

    def _download_and_hash_file(
        self, 
        file_url: str, 
        download_path: Path, 
        filename: str
    ) -> Tuple[Path, str]:
        """Download file and calculate its content hash."""
        logger.info(f"Downloading file '{filename}' from Moodle")
        
        downloaded_path = self.moodle.download_file(
            str(file_url), download_path, filename
        )
        
        # Calculate content hash
        content_hash = self._calculate_file_hash(downloaded_path)
        logger.debug(f"File '{filename}' downloaded with hash: {content_hash[:16]}...")
        
        return downloaded_path, content_hash

    def _calculate_file_hash(self, file_path: Path) -> str:
        """Calculate SHA256 hash of file content."""
        hash_sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_sha256.update(chunk)
        return hash_sha256.hexdigest()

    def _extract_and_format_to_markdown(self, file_path: Path) -> str:
        """Extract text from file and format to markdown (without saving to disk)."""
        logger.info(f"Extracting text from file: {file_path}")
        
        # Extract raw text
        raw_text = self.file_processor.process_file(file_path)
        if not raw_text:
            logger.warning(f"No text extracted from file: {file_path}")
            return ""
        
        # Format to markdown (without saving)
        logger.info(f"Converting text to markdown for file: {file_path.name}")
        markdown_text = self.ai_wrapper.format_to_markdown(
            raw_text, save_path=None  # Don't save to disk
        )
        
        if not markdown_text:
            logger.warning(f"No markdown generated for file: {file_path.name}")
            return ""
        
        logger.info(f"Markdown generated successfully for file: {file_path.name}")
        return markdown_text

    def _generate_and_store_embeddings(
        self,
        course_id: int,
        course_name_for_pgvector: str,
        filename: str,
        markdown_text: str
    ) -> int:
        """Generate embeddings and store in vector database."""
        logger.info(f"Generating embeddings for file '{filename}'")
        
        # Split into chunks using configured sizes
        chunks = self.embedding_manager.split_text_into_chunks(
            markdown_text,
            chunk_size=self.config.chunk_size,
            chunk_overlap=self.config.chunk_overlap
        )
        
        if not chunks:
            logger.warning(f"No chunks generated for file '{filename}'")
            return 0
        
        # Contextualize chunks
        contextualized_chunks = []
        for i, chunk_text in enumerate(chunks):
            contextualized_text = self.embedding_manager.contextualize_chunk(
                chunk_text, filename, f"chunk_{i + 1}"
            )
            contextualized_chunks.append(contextualized_text)
        
        # Generate embeddings
        chunk_embeddings = self.embedding_manager.generate_embeddings_for_chunks(
            contextualized_chunks
        )
        
        # Prepare chunks for database
        db_chunks = self.embedding_manager.prepare_document_chunks_for_vector_db(
            document_id=f"{course_id}_{filename}",
            document_title=filename,
            source_filename=filename,
            chunks_text=contextualized_chunks,
            embeddings=chunk_embeddings,
            course_id=course_id,
        )
        
        # Store in vector database
        if db_chunks:
            self.pgvector_db.upsert_chunks(course_name_for_pgvector, db_chunks)
            logger.info(f"Stored {len(db_chunks)} chunks for file '{filename}'")
            return len(db_chunks)
        
        logger.warning(f"No chunks to store for file '{filename}'")
        return 0

    def _cleanup_downloaded_file(self, file_path: Path):
        """Remove downloaded file from local storage."""
        try:
            if file_path.exists():
                file_path.unlink(missing_ok=True)
                logger.debug(f"Cleaned up downloaded file: {file_path}")
        except Exception as e:
            logger.warning(f"Could not delete file {file_path}: {e}")
