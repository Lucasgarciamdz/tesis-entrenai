from fastapi import APIRouter, HTTPException, Depends, Query, status
from typing import List, Optional, Dict, Any

from entrenai_refactor.api import modelos as modelos_api
from entrenai_refactor.nucleo.bd.envoltorio_pgvector import EnvoltorioPgVector, ErrorEnvoltorioPgVector
from entrenai_refactor.nucleo.ia.proveedor_inteligencia import ProveedorInteligencia, ErrorProveedorInteligencia
from entrenai_refactor.config.registrador import obtener_registrador
from entrenai_refactor.config.configuracion import configuracion_global # Aunque no se use directamente, es bueno tenerlo si se necesita config general

registrador = obtener_registrador(__name__)

enrutador = APIRouter(
    prefix="/api/v1/busqueda", # Prefijo para todos los endpoints en este router
    tags=["Búsqueda Contextual"], # Etiqueta para la documentación de Swagger/OpenAPI
)

# --- Funciones de Dependencia (Inyección) ---

def obtener_envoltorio_pgvector() -> EnvoltorioPgVector:
    try:
        return EnvoltorioPgVector()
    except Exception as e:
        registrador.error(f"Error al crear instancia de EnvoltorioPgVector: {e}")
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"No se pudo conectar con la base de datos vectorial: {str(e)}")

def obtener_proveedor_inteligencia() -> ProveedorInteligencia:
    try:
        return ProveedorInteligencia()
    except ErrorProveedorInteligencia as e:
        registrador.error(f"Error al crear instancia de ProveedorInteligencia: {e}")
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"No se pudo inicializar el proveedor de IA: {str(e)}")
    except Exception as e:
        registrador.error(f"Error inesperado al crear ProveedorInteligencia: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error interno al configurar el proveedor de IA.")

# --- Endpoint de Búsqueda ---

@enrutador.post("/contextual",
                 response_model=modelos_api.RespuestaBusqueda,
                 summary="Realizar Búsqueda Contextual en un Curso",
                 description="Genera un embedding para la consulta y busca fragmentos de documentos similares en la base de datos vectorial del curso especificado.")
async def buscar_contextual(
    solicitud: modelos_api.SolicitudBusquedaContextual,
    bd_pgvector: EnvoltorioPgVector = Depends(obtener_envoltorio_pgvector),
    proveedor_ia: ProveedorInteligencia = Depends(obtener_proveedor_inteligencia)
):
    registrador.info(f"Recibida solicitud de búsqueda contextual para curso ID '{solicitud.id_curso}' con consulta: '{solicitud.consulta[:50]}...'")

    try:
        # Obtener el nombre de la tabla para el curso.
        # El modelo usa id_curso, el envoltorio pgvector puede tomar id_curso directamente para generar el nombre de tabla.
        # nombre_tabla_curso = bd_pgvector.obtener_nombre_tabla_curso(str(solicitud.id_curso)) # Asumiendo que toma string o int

        registrador.debug(f"Generando embedding para la consulta: '{solicitud.consulta}'")
        embedding_generado = proveedor_ia.generar_embedding(texto=solicitud.consulta)

        if not embedding_generado:
            registrador.error("No se pudo generar el embedding para la consulta.")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error al generar embedding para la consulta.")

        registrador.debug(f"Buscando fragmentos similares en curso ID '{solicitud.id_curso}' (límite: {solicitud.limite}).")
        # buscar_fragmentos_similares espera nombre_curso_o_id_curso, podemos pasar id_curso directamente.
        resultados_busqueda_crudos = bd_pgvector.buscar_fragmentos_similares(
            nombre_curso_o_id_curso=solicitud.id_curso,
            embedding_consulta=embedding_generado,
            limite=solicitud.limite
        )

        resultados_mapeados: List[modelos_api.ResultadoBusquedaItem] = []
        for res_crudo in resultados_busqueda_crudos:
            # El payload ya contiene texto y metadatos según la implementación de buscar_fragmentos_similares
            payload = res_crudo.get("payload", {})
            item = modelos_api.ResultadoBusquedaItem(
                id_fragmento=res_crudo.get("id_fragmento", ""), # id_fragmento es el id del DocumentChunk
                similitud=res_crudo.get("similitud", 0.0),
                texto_fragmento=payload.get("texto", ""), # El texto del fragmento
                metadatos=payload # Todos los metadatos del payload
            )
            resultados_mapeados.append(item)

        registrador.info(f"Búsqueda contextual completada. Se encontraron {len(resultados_mapeados)} resultados para la consulta.")

        return modelos_api.RespuestaBusqueda(
            consulta_original=solicitud.consulta,
            resultados=resultados_mapeados,
            total_resultados=len(resultados_mapeados)
        )

    except ErrorEnvoltorioPgVector as e_pg:
        registrador.error(f"Error de base de datos vectorial durante búsqueda: {e_pg}")
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"Error en la base de datos de búsqueda: {str(e_pg)}")
    except ErrorProveedorInteligencia as e_ia:
        registrador.error(f"Error del proveedor de IA durante búsqueda: {e_ia}")
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"Error en el proveedor de IA: {str(e_ia)}")
    except HTTPException as e_http: # Re-lanzar HTTPExceptions de las dependencias
        raise e_http
    except Exception as e_gen:
        registrador.exception(f"Error inesperado durante búsqueda contextual: {e_gen}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error interno del servidor durante la búsqueda: {str(e_gen)}")

[end of entrenai_refactor/api/rutas/ruta_busqueda.py]
