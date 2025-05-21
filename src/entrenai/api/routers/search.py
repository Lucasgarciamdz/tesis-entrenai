from fastapi import APIRouter, HTTPException, Depends
from typing import List, Dict, Optional, Any
from pydantic import BaseModel

from src.entrenai.core.db.qdrant_wrapper import QdrantWrapper
from src.entrenai.core.ai.ai_provider import get_ai_wrapper, AIProviderError
from src.entrenai.config import qdrant_config
from src.entrenai.config.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(
    prefix="/api/v1",
    tags=["Búsqueda"],
)


# --- Modelos de datos para la API ---
class SearchResponse(BaseModel):
    results: List[Dict[str, Any]]
    total: int
    query: str


class ContextSearchRequest(BaseModel):
    query: str
    course_name: str
    limit: Optional[int] = 5
    threshold: Optional[float] = 0.7


# --- Dependencias ---
def get_qdrant_wrapper() -> QdrantWrapper:
    return QdrantWrapper(config=qdrant_config)


def get_ai_client():
    try:
        return get_ai_wrapper()
    except AIProviderError as e:
        logger.error(f"Error al obtener el cliente de IA: {e}")
        raise HTTPException(
            status_code=500, detail="No se pudo inicializar el proveedor de IA."
        )


@router.post("/search", response_model=SearchResponse)
async def search_context(
    search_request: ContextSearchRequest,
    qdrant: QdrantWrapper = Depends(get_qdrant_wrapper),
    ai_client=Depends(get_ai_client),
):
    """
    Busca contexto relevante en la base de datos vectorial Qdrant para una consulta.
    """
    logger.info(
        f"Buscando contexto para consulta: '{search_request.query}' "
        f"en el curso '{search_request.course_name}'"
    )

    # Validar que el cliente Qdrant y el cliente AI estén disponibles
    if not qdrant.client:
        logger.error("Cliente Qdrant no disponible")
        raise HTTPException(status_code=500, detail="Cliente Qdrant no disponible")

    try:
        # Generar embedding para la consulta
        query_embedding = ai_client.generate_embedding(text=search_request.query)
        if not query_embedding:
            logger.error("No se pudo generar embedding para la consulta")
            raise HTTPException(
                status_code=500, detail="Error al generar embedding para la consulta"
            )

        # Realizar búsqueda en Qdrant
        search_results = qdrant.search_chunks(
            course_name=search_request.course_name,
            query_embedding=query_embedding,
            limit=search_request.limit,
            score_threshold=search_request.threshold,
        )

        # Formatear resultados para la respuesta
        formatted_results = []
        for result in search_results:
            formatted_result = {
                "id": result.id,
                "score": result.score,
                "text": result.payload.get("original_text", ""),
                "metadata": {
                    k: v for k, v in result.payload.items() if k != "original_text"
                },
            }
            formatted_results.append(formatted_result)

        return SearchResponse(
            results=formatted_results,
            total=len(formatted_results),
            query=search_request.query,
        )

    except Exception as e:
        logger.exception(f"Error al buscar contexto: {e}")
        raise HTTPException(
            status_code=500, detail=f"Error al buscar contexto: {str(e)}"
        )
