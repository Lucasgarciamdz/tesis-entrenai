from qdrant_client import QdrantClient as QC, models

from qdrant_client.models import (
    VectorParams,
    HnswConfigDiff,
    OptimizersConfigDiff,
    ScalarType,
)

from qdrant_client.http.exceptions import UnexpectedResponse
from typing import List, Optional

from src.entrenai.config import QdrantConfig
from src.entrenai.core.models import DocumentChunk
from src.entrenai.utils.logger import get_logger

logger = get_logger(__name__)


class QdrantWrapperError(Exception):
    """Custom exception for QdrantWrapper errors."""

    pass


class QdrantWrapper:
    """
    Wrapper for interacting with Qdrant vector database.
    """

    def __init__(self, config: QdrantConfig):
        self.config = config
        self.client: Optional[QC] = None
        try:
            if config.host and config.port:
                self.client = QC(
                    host=config.host,
                    port=config.port,  # This is http_port
                    grpc_port=config.grpc_port
                    if config.grpc_port is not None
                    else 6334,  # Default gRPC port
                    api_key=config.api_key,
                    https=False,  # Disable SSL for local development
                    # prefer_grpc=True, # Can be enabled for performance
                )
                # Test connection by getting cluster info
                self.client.get_collections()  # This will raise if connection fails
                logger.info(
                    f"Qdrant client initialized and connected to {config.host}:{config.port}"
                )
            else:
                logger.error(
                    "Qdrant host or port not configured. QdrantWrapper will not be functional."
                )
                raise QdrantWrapperError("Qdrant host or port not configured.")
        except Exception as e:
            logger.error(
                f"Failed to connect to Qdrant at {config.host}:{config.port}: {e}"
            )
            self.client = None  # Ensure client is None if connection failed
            # Depending on policy, could re-raise or just log
            # raise QdrantWrapperError(f"Failed to connect to Qdrant: {e}") from e

    def get_collection_name(self, course_id: int) -> str:
        """Generates the collection name for a given course ID."""
        return f"{self.config.collection_prefix}{course_id}"

    def ensure_collection(
        self,
        course_id: int,
        vector_size: int,
        distance_metric: models.Distance = models.Distance.COSINE,
    ) -> bool:
        """
        Ensures a collection for the given course_id exists. If not, creates it.
        Returns True if the collection exists or was created successfully, False otherwise.
        """
        if not self.client:
            logger.error("Qdrant client not initialized. Cannot ensure collection.")
            return False

        collection_name = self.get_collection_name(course_id)
        try:
            # Check if collection exists
            try:
                self.client.get_collection(collection_name=collection_name)
                logger.info(f"Collection '{collection_name}' already exists.")
                return True
            except (
                UnexpectedResponse,
                ValueError,
            ) as e:  # ValueError for 404 in older client, UnexpectedResponse in newer
                if (isinstance(e, UnexpectedResponse) and e.status_code == 404) or (
                    isinstance(e, ValueError) and "Not found" in str(e)
                ):
                    logger.info(
                        f"Collection '{collection_name}' does not exist. Attempting to create."
                    )
                else:
                    raise  # Re-raise if it's another error

            # If it doesn't exist, create it
            self.client.create_collection(
                collection_name=collection_name,
                vectors_config=VectorParams(
                    size=vector_size,
                    distance=distance_metric,
                    hnsw_config=HnswConfigDiff(m=64, ef_construct=200),
                    quantization_config=models.ScalarQuantization(
                        scalar=models.ScalarQuantizationConfig(
                            type=ScalarType.INT8, quantile=0.99, always_ram=True
                        )
                    ),
                ),
                optimizers_config=OptimizersConfigDiff(
                    indexing_threshold=20000,
                    memmap_threshold=50000,
                    default_segment_number=2,
                ),
            )
            logger.info(
                f"Successfully created collection '{collection_name}' with vector size {vector_size} and distance {distance_metric}."
            )
            return True
        except Exception as e:
            logger.error(f"Error ensuring collection '{collection_name}': {e}")
            return False

    def upsert_chunks(self, course_id: int, chunks: List[DocumentChunk]) -> bool:
        """
        Upserts (inserts or updates) document chunks into the specified course collection.
        """
        if not self.client:
            logger.error("Qdrant client not initialized. Cannot upsert chunks.")
            return False
        if not chunks:
            logger.info("No chunks provided to upsert.")
            return True  # Or False, depending on desired behavior for empty list

        collection_name = self.get_collection_name(course_id)

        points_to_upsert = []
        for chunk in chunks:
            if chunk.embedding is None:
                logger.warning(
                    f"Chunk with ID '{chunk.id}' has no embedding. Skipping."
                )
                continue
            points_to_upsert.append(
                models.PointStruct(
                    id=chunk.id,
                    vector=chunk.embedding,
                    payload=chunk.metadata,  # Store text and other metadata in payload
                )
            )

        if not points_to_upsert:
            logger.info("No valid chunks with embeddings found to upsert.")
            return True

        try:
            self.client.upsert(
                collection_name=collection_name,
                points=points_to_upsert,
                wait=True,  # Wait for operation to complete
            )
            logger.info(
                f"Successfully upserted {len(points_to_upsert)} chunks into collection '{collection_name}'."
            )
            return True
        except Exception as e:
            logger.error(
                f"Error upserting chunks into collection '{collection_name}': {e}"
            )
            return False

    def search_chunks(
        self,
        course_id: int,
        query_embedding: List[float],
        limit: int = 5,
        score_threshold: Optional[float] = None,
    ) -> List[models.ScoredPoint]:
        """
        Searches for relevant chunks in the specified course collection based on a query embedding.
        """
        if not self.client:
            logger.error("Qdrant client not initialized. Cannot search chunks.")
            return []

        collection_name = self.get_collection_name(course_id)
        try:
            search_result = self.client.search(
                collection_name=collection_name,
                query_vector=query_embedding,
                limit=limit,
                score_threshold=score_threshold,
                with_payload=True,  # To retrieve metadata
            )
            logger.info(
                f"Search in '{collection_name}' found {len(search_result)} results."
            )
            return search_result
        except Exception as e:
            logger.error(f"Error searching in collection '{collection_name}': {e}")
            return []

    # Add other methods as needed: delete_collection, delete_points, etc.


if __name__ == "__main__":
    from src.entrenai.config import qdrant_config

    if not qdrant_config.host:
        print("QDRANT_HOST must be set in .env for this test.")
    else:
        print(
            f"Attempting to connect to Qdrant at {qdrant_config.host}:{qdrant_config.port}..."
        )
        try:
            qdrant_wrapper = QdrantWrapper(config=qdrant_config)
            if qdrant_wrapper.client:
                print("Qdrant client initialized successfully.")

                # Example: Ensure collection exists
                test_course_id = 999
                test_vector_size = 384  # Example size, adjust to your embedding model
                collection_created = qdrant_wrapper.ensure_collection(
                    test_course_id, test_vector_size
                )
                if collection_created:
                    print(
                        f"Collection '{qdrant_wrapper.get_collection_name(test_course_id)}' ensured."
                    )

                    # Example: Upsert dummy chunks
                    dummy_chunks = [
                        DocumentChunk(
                            id="chunk1_test",
                            course_id=test_course_id,
                            document_id="doc1",
                            text="Hello world",
                            embedding=[0.1] * test_vector_size,
                            metadata={"source": "test.txt"},
                        ),
                        DocumentChunk(
                            id="chunk2_test",
                            course_id=test_course_id,
                            document_id="doc1",
                            text="Qdrant is cool",
                            embedding=[0.2] * test_vector_size,
                            metadata={"source": "test.txt"},
                        ),
                    ]
                    upsert_success = qdrant_wrapper.upsert_chunks(
                        test_course_id, dummy_chunks
                    )
                    print(f"Upsert successful: {upsert_success}")

                    if upsert_success:
                        # Example: Search
                        print("Searching for 'hello' related content...")
                        # In a real scenario, you'd get this embedding from your OllamaWrapper
                        query_emb = [0.11] * test_vector_size
                        search_results = qdrant_wrapper.search_chunks(
                            test_course_id, query_emb, limit=1
                        )
                        print(f"Search results: {len(search_results)}")
                        for hit in search_results:
                            print(
                                f"  ID: {hit.id}, Score: {hit.score}, Payload: {hit.payload}"
                            )
                else:
                    print(f"Failed to ensure collection for course {test_course_id}.")
            else:
                print("Failed to initialize Qdrant client.")
        except QdrantWrapperError as e:
            print(f"QdrantWrapperError: {e}")
        except Exception as e:
            print(f"An unexpected error occurred during QdrantWrapper test: {e}")
