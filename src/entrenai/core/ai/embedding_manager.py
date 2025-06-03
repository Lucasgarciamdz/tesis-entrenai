import uuid
from typing import List, Optional, Dict, Any, Union

from src.entrenai.api.models import DocumentChunk
from src.entrenai.config.logger import get_logger
from src.entrenai.core.ai.gemini_wrapper import GeminiWrapper
from src.entrenai.core.ai.ollama_wrapper import OllamaWrapper

logger = get_logger(__name__)


class EmbeddingManagerError(Exception):
    """Excepción personalizada para errores de EmbeddingManager."""

    pass


class EmbeddingManager:
    """
    Gestiona la división de texto, chunking, contextualización y generación de embeddings.
    """

    def __init__(
        self,
        ai_wrapper: Union[OllamaWrapper, GeminiWrapper], # Changed parameter name
        default_chunk_size: int = 1000,  # Caracteres
        default_chunk_overlap: int = 200,  # Caracteres
    ):
        self.ai_wrapper = ai_wrapper # Use the new parameter name
        self.default_chunk_size = default_chunk_size
        self.default_chunk_overlap = default_chunk_overlap
        logger.info(
            f"EmbeddingManager inicializado con wrapper tipo: {type(ai_wrapper).__name__}, " # Added type logging
            f"tamaño de chunk {default_chunk_size} "
            f"y solapamiento {default_chunk_overlap}."
        )

    def split_text_into_chunks(
        self,
        text: str,
        chunk_size: Optional[int] = None,
        chunk_overlap: Optional[int] = None,
    ) -> List[str]:
        """
        Divide un texto largo en chunks más pequeños.
        Utiliza una lógica simple de división basada en caracteres por ahora.
        """
        cs = chunk_size or self.default_chunk_size
        co = chunk_overlap or self.default_chunk_overlap

        if co >= cs:
            raise ValueError(
                "El solapamiento del chunk debe ser menor que el tamaño del chunk."
            )

        logger.info(
            f"Dividiendo texto (longitud: {len(text)}) en chunks (tamaño: {cs}, solapamiento: {co})."
        )

        chunks: List[str] = []
        start_index = 0
        text_len = len(text)

        if text_len == 0:
            return []
        if text_len <= cs:
            return [text]

        while start_index < text_len:
            end_index = min(start_index + cs, text_len)
            chunks.append(text[start_index:end_index])

            if end_index == text_len:
                break

            start_index += cs - co
            if start_index >= text_len:
                break

        logger.info(f"Texto dividido en {len(chunks)} chunks.")
        return chunks

    @staticmethod
    def contextualize_chunk(
        chunk_text: str,
        document_title: Optional[str] = None,
        source_filename: Optional[str] = None,
        extra_metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Añade contexto simple a un chunk de texto usando metadatos.
        Esta versión antepone el nombre del archivo fuente y el título del documento.
        """
        context_parts = []
        if source_filename:
            context_parts.append(f"Fuente del Archivo: {source_filename}")
        if document_title:
            context_parts.append(f"Título del Documento: {document_title}")

        context_prefix = "\n".join(context_parts)
        if context_prefix:
            return f"{context_prefix}\n\nContenido del Chunk:\n{chunk_text}"
        else:
            return chunk_text

    def generate_embeddings_for_chunks(
        self, contextualized_chunks: List[str], embedding_model: Optional[str] = None
    ) -> List[List[float]]:
        """
        Genera embeddings para una lista de chunks de texto (contextualizados).
        """
        if not contextualized_chunks:
            return []

        logger.info(f"Generando embeddings para {len(contextualized_chunks)} chunks...")
        embeddings: List[List[float]] = []
        for i, chunk_text in enumerate(contextualized_chunks):
            try:
                logger.debug(
                    f"Generando embedding para chunk {i + 1}/{len(contextualized_chunks)} (longitud: {len(chunk_text)} caracteres)"
                )
                emb = self.ai_wrapper.generate_embedding(
                    text=chunk_text, model=embedding_model
                )
                embeddings.append(emb)
            except Exception as e:
                logger.error(
                    f"Falló la generación de embedding para el chunk {i + 1}: {e}. Omitiendo este chunk."
                )
                embeddings.append([])
        logger.info(
            f"Embeddings generados exitosamente para {sum(1 for emb in embeddings if emb)} chunks."
        )
        return embeddings

    @staticmethod
    def prepare_document_chunks_for_vector_db(
        course_id: int,
        # TODO: Consider if course_name should be passed here directly
        document_id: str,
        source_filename: str,
        document_title: Optional[str],
        chunks_text: List[str],
        embeddings: List[List[float]],
        additional_metadatas: Optional[List[Optional[Dict[str, Any]]]] = None,
    ) -> List[DocumentChunk]:
        """
        Prepara objetos DocumentChunk listos para el Vector DB, incluyendo IDs únicos y metadatos.
        """
        if len(chunks_text) != len(embeddings):
            raise ValueError(
                "El número de chunks de texto y embeddings debe coincidir."
            )
        if additional_metadatas and len(chunks_text) != len(additional_metadatas):
            raise ValueError(
                "El número de chunks de texto y additional_metadatas debe coincidir si se proveen metadatos."
            )

        document_chunks: List[DocumentChunk] = []
        for i, text_chunk in enumerate(chunks_text):
            chunk_id = str(uuid.uuid4())
            metadata = {
                "course_id": course_id,
                "document_id": document_id,
                "source_filename": source_filename,
                "original_text": text_chunk,
            }
            if document_title:
                metadata["document_title"] = document_title

            if additional_metadatas and additional_metadatas[i]:
                metadata.update(additional_metadatas[i])  # type: ignore

            document_chunks.append(
                DocumentChunk(
                    id=chunk_id,
                    course_id=course_id,
                    document_id=document_id,
                    text=text_chunk,
                    embedding=embeddings[i] if embeddings[i] else None,
                    metadata=metadata,
                )
            )
        logger.info(
            f"Preparados {len(document_chunks)} objetos DocumentChunk para el Vector DB."
        )
        return document_chunks
