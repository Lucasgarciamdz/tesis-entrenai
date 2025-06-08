from typing import List, Dict, Optional, Any, Union

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from entrenai2.configuracion.configuracion import configuracion_pgvector, configuracion_base
from entrenai2.configuracion.registrador import obtener_registrador
from entrenai2.nucleo.ia.proveedor_ia import ProveedorIA, ErrorProveedorIA
from entrenai2.nucleo.bd.envoltorio_pgvector import EnvoltorioPgvector, ErrorEnvoltorioPgvector

registrador = obtener_registrador(__name__)

enrutador = APIRouter(
    prefix="/api/v1",
    tags=["Búsqueda"],
)


# --- Modelos de datos para la API ---
class RespuestaBusqueda(BaseModel):
    resultados: List[Dict[str, Any]]
    total: int
    consulta: str


class SolicitudBusquedaContexto(BaseModel):
    consulta: str
    nombre_curso: str
    limite: Optional[int] = 5


# --- Dependencias ---
def obtener_envoltorio_pgvector() -> EnvoltorioPgvector:
    try:
        return EnvoltorioPgvector(configuracion=configuracion_pgvector)
    except Exception as e:
        registrador.error(f"Error al crear EnvoltorioPgvector: {e}")
        raise HTTPException(status_code=503, detail="No se pudo conectar con la base de datos vectorial")


def obtener_cliente_ia() -> Union[Any, Any]: # Usar Any para evitar importaciones circulares o complejas aquí
    try:
        return ProveedorIA.obtener_envoltorio_ia_por_proveedor(
            proveedor_ia=configuracion_base.proveedor_ia
        )
    except ErrorProveedorIA as e:
        registrador.error(f"Error al obtener el cliente de IA: {e}")
        raise HTTPException(
            status_code=500, detail="No se pudo inicializar el proveedor de IA."
        )


@enrutador.post("/buscar", response_model=RespuestaBusqueda)
async def buscar_contexto(
    solicitud_busqueda: SolicitudBusquedaContexto,
    bd_pgvector: EnvoltorioPgvector = Depends(obtener_envoltorio_pgvector),
    cliente_ia=Depends(obtener_cliente_ia),
):
    """
    Busca contexto relevante en la base de datos vectorial Pgvector para una consulta.
    """
    registrador.info(
        f"Buscando contexto para consulta: '{solicitud_busqueda.consulta}' "
        f"en el curso '{solicitud_busqueda.nombre_curso}'"
    )

    try:
        # Generar embedding para la consulta
        embedding_consulta = cliente_ia.generar_embedding(texto=solicitud_busqueda.consulta)
        if not embedding_consulta:
            registrador.error("No se pudo generar embedding para la consulta")
            raise HTTPException(
                status_code=500, detail="Error al generar embedding para la consulta"
            )

        # Realizar búsqueda en Pgvector
        resultados_busqueda = bd_pgvector.buscar_fragmentos(
            nombre_curso=solicitud_busqueda.nombre_curso,
            embedding_consulta=embedding_consulta,
            limite=solicitud_busqueda.limite or 5,
        )

        # Formatear resultados para la respuesta
        resultados_formateados = []
        for resultado in resultados_busqueda:
            carga_util = resultado.get("payload", {})
            resultado_formateado = {
                "id": resultado.get("id"),
                "score": resultado.get("score"),
                "texto": carga_util.get("texto", ""),
                "metadata": {
                    k: v
                    for k, v in carga_util.items()
                    if k != "texto"
                },
            }
            resultados_formateados.append(resultado_formateado)

        return RespuestaBusqueda(
            resultados=resultados_formateados,
            total=len(resultados_formateados),
            consulta=solicitud_busqueda.consulta,
        )

    except (ErrorProveedorIA, ErrorEnvoltorioPgvector) as e:
        registrador.error(f"Error durante la búsqueda de contexto: {e}")
        raise HTTPException(
            status_code=500, detail=f"Error durante la búsqueda de contexto: {str(e)}"
        )
    except Exception as e:
        registrador.exception(f"Error inesperado al buscar contexto: {e}")
        raise HTTPException(
            status_code=500, detail=f"Error interno del servidor: {str(e)}"
        )
