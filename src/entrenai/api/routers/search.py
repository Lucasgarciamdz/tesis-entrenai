from typing import List, Dict, Optional, Any

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from src.entrenai.config import pgvector_config  # Updated import
from src.entrenai.config.logger import get_logger
from src.entrenai.core.ai.ai_provider import get_ai_wrapper, AIProviderError
from src.entrenai.core.db import PgvectorWrapper  # Updated import

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
    threshold: Optional[float] = 0.7  # This will be removed from search_chunks call


# --- Dependencias ---
def get_pgvector_wrapper() -> (
    PgvectorWrapper
):  # Renamed function and updated return type
    return PgvectorWrapper(config=pgvector_config)  # Updated instantiation


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
    pgvector_db: PgvectorWrapper = Depends(get_pgvector_wrapper),
    # Updated dependency
    ai_client=Depends(get_ai_client),
):
    """
    Busca contexto relevante en la base de datos vectorial Pgvector para una consulta.
    """
    logger.info(
        f"Buscando contexto para consulta: '{search_request.query}' "
        f"en el curso '{search_request.course_name}'"
    )

    # Removed qdrant.client check, PgvectorWrapper handles connection internally

    try:
        # Generar embedding para la consulta
        query_embedding = ai_client.generate_embedding(text=search_request.query)
        if not query_embedding:
            logger.error("No se pudo generar embedding para la consulta")
            raise HTTPException(
                status_code=500, detail="Error al generar embedding para la consulta"
            )

        # Realizar búsqueda en Pgvector
        # Note: score_threshold is not used by PgvectorWrapper.search_chunks as implemented
        search_results = pgvector_db.search_chunks(
            course_name=search_request.course_name,
            query_embedding=query_embedding,
            limit=search_request.limit or 5,  # Ensure limit has a default if None
            # score_threshold is not a direct parameter for the current pgvector_wrapper.search_chunks
        )

        # Formatear resultados para la respuesta
        # PgvectorWrapper.search_chunks returns List[Dict[str, Any]]
        # Each dict has 'id', 'score', and 'payload' (which includes 'text', 'document_id', etc.)
        formatted_results = []
        for result in search_results:  # result is a dict
            payload = result.get("payload", {})
            formatted_result = {
                "id": result.get("id"),
                "score": result.get("score"),
                "text": payload.get("text", ""),  # text is directly in payload
                "metadata": {
                    k: v
                    for k, v in payload.items()
                    if k != "text"  # Adjust to exclude 'text' from metadata
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
