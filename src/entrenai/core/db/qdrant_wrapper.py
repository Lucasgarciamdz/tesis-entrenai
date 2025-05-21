import re  # For normalizing names
from qdrant_client import QdrantClient as QC, models
from qdrant_client.models import (
    VectorParams,
    HnswConfigDiff,
    OptimizersConfigDiff,
    ScalarType,
)
from qdrant_client.http.exceptions import UnexpectedResponse
from typing import List, Optional  # Added Dict, Any

from src.entrenai.config import QdrantConfig
from src.entrenai.api.models import DocumentChunk
from src.entrenai.config.logger import get_logger

logger = get_logger(__name__)


class QdrantWrapperError(Exception):
    """Excepción personalizada para errores de QdrantWrapper."""

    pass


class QdrantWrapper:
    """Wrapper para interactuar con la base de datos vectorial Qdrant."""

    def __init__(self, config: QdrantConfig):
        self.config = config
        self.client: Optional[QC] = None
        try:
            if config.host and config.port:
                self.client = QC(
                    host=config.host,
                    port=config.port,
                    grpc_port=config.grpc_port
                    if config.grpc_port is not None
                    else 6334,
                    api_key=config.api_key,
                    https=False,
                )
                self.client.get_collections()
                logger.info(
                    f"Cliente Qdrant inicializado y conectado a {config.host}:{config.port}"
                )
            else:
                logger.error(
                    "Host o puerto de Qdrant no configurado. QdrantWrapper no será funcional."
                )
                raise QdrantWrapperError("Host o puerto de Qdrant no configurado.")
        except Exception as e:
            logger.error(
                f"Falló la conexión a Qdrant en {config.host}:{config.port}: {e}"
            )
            self.client = None
            # raise QdrantWrapperError(f"Falló la conexión a Qdrant: {e}") from e

    def _normalize_name_for_collection(self, name: str) -> str:
        """Normaliza un nombre para ser usado como identificador de colección en Qdrant."""
        if not name:
            logger.error("Se intentó normalizar un nombre vacío para la colección.")
            raise ValueError(
                "El nombre del curso no puede estar vacío para generar el nombre de la colección."
            )

        name_lower = name.lower()
        # Reemplazar espacios y caracteres problemáticos con guion bajo
        name_processed = re.sub(r"\s+", "_", name_lower)
        # Permitir solo alfanuméricos, guion bajo, guion medio
        name_processed = re.sub(r"[^a-z0-9_-]", "", name_processed)
        # Truncar a una longitud máxima (Qdrant podría tener límites)
        max_len = 60  # Un límite razonable
        if len(name_processed) > max_len:
            name_processed = name_processed[:max_len]

        if not name_processed:  # Si después de la normalización queda vacío (ej. nombre solo con caracteres especiales)
            logger.error(
                f"El nombre normalizado para '{name}' resultó vacío. Usando fallback."
            )
            raise ValueError(
                f"El nombre del curso '{name}' resultó en un nombre de colección normalizado vacío."
            )

        return name_processed

    def get_collection_name(self, course_name: str) -> str:
        """Genera el nombre de la colección para un nombre de curso dado, usando el prefijo de configuración."""
        normalized_name = self._normalize_name_for_collection(course_name)
        # El usuario quiere "entrenai_{course_name}" y ajustará el prefijo en .env a "entrenai_"
        return f"{self.config.collection_prefix}{normalized_name}"

    def ensure_collection(
        self,
        course_name: str,  # Cambiado de course_id a course_name
        vector_size: int,
        distance_metric: models.Distance = models.Distance.COSINE,
    ) -> bool:
        """
        Asegura que exista una colección para el nombre de curso dado. Si no, la crea.
        Devuelve True si la colección existe o fue creada exitosamente, False en caso contrario.
        """
        if not self.client:
            logger.error(
                "Cliente Qdrant no inicializado. No se puede asegurar la colección."
            )
            return False

        collection_name = self.get_collection_name(course_name)
        try:
            try:
                collection_info = self.client.get_collection(
                    collection_name=collection_name
                )
                # Acceder a la configuración del vector. Asumimos un solo vector por defecto.
                # La estructura es CollectionInfo -> config: CollectionConfig -> params: CollectionParams -> vectors: Union[VectorParams, Dict[str, VectorParams]]
                current_vectors_config = collection_info.config.params.vectors

                # Si es un diccionario (múltiples vectores con nombre), no manejamos este caso aún.
                # Para el vector por defecto (sin nombre), current_vectors_config debería ser VectorParams.
                if not isinstance(current_vectors_config, models.VectorParams):
                    logger.error(
                        f"La configuración de vectores para la colección '{collection_name}' no es del tipo VectorParams esperado. Es {type(current_vectors_config)}"
                    )
                    # Decidir si recrear o fallar. Por seguridad, fallar si la estructura es inesperada.
                    raise QdrantWrapperError(
                        f"Estructura de configuración de vectores inesperada para la colección '{collection_name}'."
                    )

                current_size = current_vectors_config.size
                current_distance = current_vectors_config.distance

                if (
                    current_size != vector_size
                    or current_distance.lower() != distance_metric.value.lower()
                ):
                    logger.warning(
                        f"La colección '{collection_name}' existe pero con configuración de vector diferente. "
                        f"Existente: size={current_size}, dist={current_distance}. "
                        f"Requerido: size={vector_size}, dist={distance_metric}. Recreando..."
                    )
                    self.client.delete_collection(collection_name=collection_name)
                    raise ValueError(
                        "Recreando colección por configuración incompatible."
                    )
                logger.info(
                    f"La colección '{collection_name}' ya existe con configuración compatible."
                )
                return True
            except (UnexpectedResponse, ValueError) as e:
                if (isinstance(e, UnexpectedResponse) and e.status_code == 404) or (
                    isinstance(e, ValueError)
                    and ("Not found" in str(e) or "Recreando colección" in str(e))
                ):  # Check for "Not found" for older clients or our ValueError
                    logger.info(
                        f"La colección '{collection_name}' no existe o necesita ser recreada. Intentando crearla."
                    )
                else:
                    raise

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
                f"Colección '{collection_name}' creada exitosamente con tamaño de vector {vector_size} y distancia {distance_metric}."
            )
            return True
        except Exception as e:
            logger.error(f"Error al asegurar la colección '{collection_name}': {e}")
            return False

    def upsert_chunks(
        self, course_name: str, chunks: List[DocumentChunk]
    ) -> bool:  # Cambiado de course_id
        """
        Inserta o actualiza (upsert) chunks de documentos en la colección del curso especificado.
        """
        if not self.client:
            logger.error(
                "Cliente Qdrant no inicializado. No se pueden insertar chunks."
            )
            return False
        if not chunks:
            logger.info("No se proporcionaron chunks para insertar.")
            return True

        collection_name = self.get_collection_name(course_name)

        points_to_upsert = []
        for chunk in chunks:
            if chunk.embedding is None:
                logger.warning(
                    f"Chunk con ID '{chunk.id}' (curso: {chunk.course_id}, doc: {chunk.document_id}) no tiene embedding. Omitiendo."
                )
                continue
            points_to_upsert.append(
                models.PointStruct(
                    id=chunk.id,
                    vector=chunk.embedding,
                    payload=chunk.metadata,
                )
            )

        if not points_to_upsert:
            logger.info(
                "No se encontraron chunks válidos con embeddings para insertar."
            )
            return True

        try:
            self.client.upsert(
                collection_name=collection_name,
                points=points_to_upsert,
                wait=True,
            )
            logger.info(
                f"Se insertaron/actualizaron {len(points_to_upsert)} chunks exitosamente en la colección '{collection_name}'."
            )
            return True
        except Exception as e:
            logger.error(
                f"Error al insertar/actualizar chunks en la colección '{collection_name}': {e}"
            )
            return False

    def search_chunks(
        self,
        course_name: str,  # Cambiado de course_id
        query_embedding: List[float],
        limit: int = 5,
        score_threshold: Optional[float] = None,
    ) -> List[models.ScoredPoint]:
        """
        Busca chunks relevantes en la colección del curso especificado basado en un embedding de consulta.
        """
        if not self.client:
            logger.error("Cliente Qdrant no inicializado. No se pueden buscar chunks.")
            return []

        collection_name = self.get_collection_name(course_name)
        try:
            search_result = self.client.search(
                collection_name=collection_name,
                query_vector=query_embedding,
                limit=limit,
                score_threshold=score_threshold,
                with_payload=True,
            )
            logger.info(
                f"Búsqueda en '{collection_name}' encontró {len(search_result)} resultados."
            )
            return search_result
        except Exception as e:
            logger.error(f"Error buscando en la colección '{collection_name}': {e}")
            return []

    # Añadir otros métodos según sea necesario: delete_collection, delete_points, etc.
