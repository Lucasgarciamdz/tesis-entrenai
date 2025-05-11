import uuid
from typing import List, Optional, Dict, Any

from src.entrenai.core.ollama_wrapper import OllamaWrapper

# QdrantWrapper might not be directly needed here if this class only prepares data,
# but it's good to have if it orchestrates upsertion later.
# from src.entrenai.core.qdrant_wrapper import QdrantWrapper
from src.entrenai.core.models import DocumentChunk
from src.entrenai.utils.logger import get_logger

# Consider using a text splitter library, e.g., from langchain, or implement a robust one.
# from langchain.text_splitter import RecursiveCharacterTextSplitter (Example)

logger = get_logger(__name__)


class EmbeddingManagerError(Exception):
    """Custom exception for EmbeddingManager errors."""

    pass


class EmbeddingManager:
    """
    Manages text splitting, chunking, contextualization, and embedding generation.
    """

    def __init__(
        self,
        ollama_wrapper: OllamaWrapper,
        # qdrant_wrapper: QdrantWrapper, # Not strictly needed for generation, but for direct upsert
        default_chunk_size: int = 1000,  # Characters
        default_chunk_overlap: int = 200,  # Characters
    ):
        self.ollama_wrapper = ollama_wrapper
        # self.qdrant_wrapper = qdrant_wrapper
        self.default_chunk_size = default_chunk_size
        self.default_chunk_overlap = default_chunk_overlap

        # Placeholder for a more sophisticated text splitter
        # self.text_splitter = RecursiveCharacterTextSplitter(
        #     chunk_size=default_chunk_size,
        #     chunk_overlap=default_chunk_overlap,
        #     length_function=len,
        # )
        logger.info(
            f"EmbeddingManager initialized with chunk size {default_chunk_size} "
            f"and overlap {default_chunk_overlap}."
        )

    def split_text_into_chunks(
        self,
        text: str,
        chunk_size: Optional[int] = None,
        chunk_overlap: Optional[int] = None,
    ) -> List[str]:
        """
        Splits a long text into smaller chunks.
        Uses a simple character-based splitting logic for now.
        A more robust implementation would use RecursiveCharacterTextSplitter or similar.
        """
        cs = chunk_size or self.default_chunk_size
        co = chunk_overlap or self.default_chunk_overlap

        if co >= cs:
            raise ValueError("Chunk overlap must be smaller than chunk size.")

        logger.info(
            f"Splitting text (length: {len(text)}) into chunks (size: {cs}, overlap: {co})."
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
                break  # Reached the end of the text

            start_index += cs - co  # Move start_index forward, considering overlap
            if (
                start_index >= text_len
            ):  # Should not happen if logic is correct, but as a safeguard
                break

        logger.info(f"Text split into {len(chunks)} chunks.")
        return chunks

    def contextualize_chunk(
        self,
        chunk_text: str,
        document_title: Optional[str] = None,
        source_filename: Optional[str] = None,
        # headings: Optional[List[str]] = None, # Could be added later
        extra_metadata: Optional[Dict[str, Any]] = None,  # For page numbers, etc.
    ) -> str:
        """
        Adds simple context to a text chunk using metadata.
        This version prepends source filename and document title.
        """
        context_parts = []
        if source_filename:
            context_parts.append(f"Fuente del Archivo: {source_filename}")
        if document_title:  # Document title might be different from filename
            context_parts.append(f"Título del Documento: {document_title}")
        # if headings:
        #     context_parts.append(f"Sección/Encabezados: {' > '.join(headings)}")

        context_prefix = "\n".join(context_parts)
        if context_prefix:
            return f"{context_prefix}\n\nContenido del Chunk:\n{chunk_text}"
        else:
            return chunk_text  # No context to add, return original chunk

    def generate_embeddings_for_chunks(
        self, contextualized_chunks: List[str], embedding_model: Optional[str] = None
    ) -> List[List[float]]:
        """
        Generates embeddings for a list of (contextualized) text chunks.
        """
        if not contextualized_chunks:
            return []

        logger.info(f"Generating embeddings for {len(contextualized_chunks)} chunks...")
        embeddings: List[List[float]] = []
        for i, chunk_text in enumerate(contextualized_chunks):
            try:
                logger.debug(
                    f"Generating embedding for chunk {i + 1}/{len(contextualized_chunks)} (length: {len(chunk_text)} chars)"
                )
                emb = self.ollama_wrapper.generate_embedding(
                    text=chunk_text, model=embedding_model
                )
                embeddings.append(emb)
            except Exception as e:
                logger.error(
                    f"Failed to generate embedding for chunk {i + 1}: {e}. Skipping this chunk."
                )
                # Optionally, append a placeholder or handle differently
                embeddings.append([])  # Or some default error vector / skip

        logger.info(
            f"Successfully generated embeddings for {sum(1 for emb in embeddings if emb)} chunks."
        )
        return embeddings

    def prepare_document_chunks_for_qdrant(
        self,
        course_id: int,
        document_id: str,  # A unique ID for the source document (e.g., Moodle file ID or hash)
        source_filename: str,
        document_title: Optional[str],  # Optional title from metadata
        chunks_text: List[str],  # Original, non-contextualized chunks
        embeddings: List[List[float]],
        # original_texts_md: Optional[List[str]] = None, # If Markdown version is stored separately
        additional_metadatas: Optional[
            List[Optional[Dict[str, Any]]]
        ] = None,  # e.g., page numbers
    ) -> List[DocumentChunk]:
        """
        Prepares DocumentChunk objects ready for Qdrant, including unique IDs and metadata.
        """
        if len(chunks_text) != len(embeddings):
            raise ValueError("Number of text chunks and embeddings must match.")
        if additional_metadatas and len(chunks_text) != len(additional_metadatas):
            raise ValueError(
                "Number of text chunks and additional_metadatas must match if metadata is provided."
            )

        document_chunks: List[DocumentChunk] = []
        for i, text_chunk in enumerate(chunks_text):
            chunk_id = str(uuid.uuid4())
            metadata = {
                "course_id": course_id,
                "document_id": document_id,
                "source_filename": source_filename,
                "original_text": text_chunk,  # Store the original chunk text
                # "markdown_text": original_texts_md[i] if original_texts_md else None,
            }
            if document_title:
                metadata["document_title"] = document_title

            if additional_metadatas and additional_metadatas[i]:
                metadata.update(additional_metadatas[i])  # type: ignore

            document_chunks.append(
                DocumentChunk(
                    id=chunk_id,
                    course_id=course_id,  # Redundant? Already in metadata. Kept for direct model field.
                    document_id=document_id,  # Redundant?
                    text=text_chunk,  # This is the text that was embedded (could be contextualized one)
                    # Or, store original chunk here and contextualized one in payload?
                    # For now, 'text' is what was embedded.
                    embedding=embeddings[i]
                    if embeddings[i]
                    else None,  # Handle failed embeddings
                    metadata=metadata,
                )
            )
        logger.info(
            f"Prepared {len(document_chunks)} DocumentChunk objects for Qdrant."
        )
        return document_chunks


if __name__ == "__main__":
    from src.entrenai.config import ollama_config  # For OllamaWrapper

    # Mock OllamaWrapper for testing EmbeddingManager independently
    class MockOllamaWrapper:
        def __init__(self, config):
            self.config = config
            logger.info("MockOllamaWrapper initialized.")

        def generate_embedding(
            self, text: str, model: Optional[str] = None
        ) -> List[float]:
            logger.info(
                f"Mock generating embedding for text (len: {len(text)}) with model: {model or self.config.embedding_model}"
            )
            # Return a dummy embedding of the configured size or a default
            # vector_size = getattr(self.config, 'default_vector_size', 384) # Assuming this exists
            return [0.1] * 384  # Fixed size for mock

    mock_ollama_wrapper = MockOllamaWrapper(config=ollama_config)
    manager = EmbeddingManager(
        ollama_wrapper=mock_ollama_wrapper,
        default_chunk_size=100,
        default_chunk_overlap=20,
    )  # type: ignore

    sample_text = "Este es un texto de ejemplo largo que necesita ser dividido en varios chunks más pequeños para su procesamiento. Cada chunk tendrá un tamaño y un solapamiento definidos. La idea es que el solapamiento ayude a mantener el contexto entre chunks adyacentes. Este es el final de la primera parte. Aquí comienza la segunda parte del texto que también es importante. Y una tercera frase para asegurar más chunks."

    print("\n--- Testing split_text_into_chunks ---")
    chunks = manager.split_text_into_chunks(sample_text)
    for i, chunk in enumerate(chunks):
        print(f"Chunk {i + 1} (len {len(chunk)}): '{chunk}'")

    print("\n--- Testing contextualize_chunk ---")
    contextualized_chunks = [
        manager.contextualize_chunk(
            chunk,
            document_title="Documento de Prueba",
            source_filename="prueba.txt",
            extra_metadata={"page_number": i // 2 + 1},  # Example metadata
        )
        for i, chunk in enumerate(chunks)
    ]
    for i, c_chunk in enumerate(contextualized_chunks):
        print(
            f"Contextualized Chunk {i + 1} (len {len(c_chunk)}): '{c_chunk[:150]}...'"
        )

    print("\n--- Testing generate_embeddings_for_chunks ---")
    embeddings = manager.generate_embeddings_for_chunks(contextualized_chunks)
    print(f"Generated {len(embeddings)} embeddings.")
    if embeddings and embeddings[0]:
        print(
            f"First embedding (first 5 dims): {embeddings[0][:5]}... (Length: {len(embeddings[0])})"
        )

    print("\n--- Testing prepare_document_chunks_for_qdrant ---")
    # For prepare_document_chunks_for_qdrant, 'chunks_text' should be the original, non-contextualized chunks
    # if the 'text' field in DocumentChunk is meant to be the text that was embedded (i.e., contextualized).
    # If 'text' in DocumentChunk should be the original chunk, then pass original chunks here.
    # Let's assume 'text' in DocumentChunk is the text that was *actually embedded*.

    # Re-generate embeddings on contextualized chunks for this test step
    # (In a real flow, embeddings would be generated on the contextualized text)

    # We need original chunks and their corresponding contextualized versions for this test.
    # Let's assume the embeddings were generated for 'contextualized_chunks'.
    # The 'text' field in DocumentChunk should store what was embedded.
    # The 'original_text' is stored in metadata.

    prepared_qdrant_chunks = manager.prepare_document_chunks_for_qdrant(
        course_id=101,
        document_id="doc_test_001",
        source_filename="prueba.txt",
        document_title="Documento de Prueba",
        chunks_text=contextualized_chunks,  # Text that was embedded
        embeddings=embeddings,
        additional_metadatas=[
            {"page_number": i // 2 + 1, "original_chunk_for_debug": chunks[i]}
            for i in range(len(chunks))
        ],
    )

    for i, q_chunk in enumerate(prepared_qdrant_chunks):
        print(f"\nQdrant Chunk {i + 1}:")
        print(f"  ID: {q_chunk.id}")
        print(f"  Text (embedded, first 50 chars): {q_chunk.text[:50]}...")
        print(f"  Embedding (present): {bool(q_chunk.embedding)}")
        print(f"  Metadata: {q_chunk.metadata}")

    print("\nEmbeddingManager tests complete.")
