from fastapi import APIRouter, HTTPException, Depends, status
from typing import List, Optional # No se usa Dict, Any directamente aquí

# Importar modelos Pydantic refactorizados (usando sus nuevos nombres en español)
from entrenai_refactor.api import modelos as modelos_api_traducidos
# Importar clases refactorizadas del núcleo
from entrenai_refactor.nucleo.bd import EnvoltorioPgVector, ErrorBaseDeDatosVectorial
from entrenai_refactor.nucleo.ia import ProveedorInteligencia, ErrorProveedorInteligencia
from entrenai_refactor.config.registrador import obtener_registrador

registrador = obtener_registrador(__name__)

enrutador_busqueda = APIRouter( # Renombrado para más claridad si se importa en otro lado
    prefix="/api/v1/busqueda",
    tags=["Búsqueda Semántica y Contextual"],
)

# --- Funciones de Dependencia (Inyección de Dependencias de FastAPI) ---

def obtener_conexion_envoltorio_pgvector() -> EnvoltorioPgVector:
    """
    Dependencia de FastAPI para obtener una instancia del EnvoltorioPgVector.
    Maneja errores de inicialización y los convierte en HTTPExceptions.
    """
    try:
        # EnvoltorioPgVector se inicializa de forma perezosa, la conexión real ocurre al usarlo.
        return EnvoltorioPgVector()
    except ErrorBaseDeDatosVectorial as e_bd_vec: # Captura la excepción personalizada del envoltorio
        registrador.error(f"Error crítico al inicializar EnvoltorioPgVector: {e_bd_vec}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"No se pudo establecer conexión con el servicio de base de datos vectorial: {str(e_bd_vec)}"
        )
    except Exception as e_inesperado: # Otros errores inesperados durante la instanciación
        registrador.exception(f"Error inesperado al instanciar EnvoltorioPgVector: {e_inesperado}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno del servidor al configurar el acceso a la base de datos."
        )

def obtener_instancia_proveedor_inteligencia() -> ProveedorInteligencia:
    """
    Dependencia de FastAPI para obtener una instancia del ProveedorInteligencia.
    Maneja errores de inicialización y los convierte en HTTPExceptions.
    """
    try:
        return ProveedorInteligencia()
    except ErrorProveedorInteligencia as e_prov_ia: # Captura la excepción personalizada
        registrador.error(f"Error crítico al inicializar ProveedorInteligencia: {e_prov_ia}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"No se pudo inicializar el proveedor de inteligencia artificial configurado: {str(e_prov_ia)}"
        )
    except Exception as e_inesperado: # Otros errores
        registrador.exception(f"Error inesperado al instanciar ProveedorInteligencia: {e_inesperado}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno del servidor al configurar el proveedor de inteligencia artificial."
        )

# --- Endpoint de Búsqueda Contextual ---

@enrutador_busqueda.post("/contextual", # Mantener la ruta como estaba
                         response_model=modelos_api_traducidos.RespuestaBusquedaContextual, # Usar modelo traducido
                         summary="Realizar Búsqueda Semántica Contextual en un Curso Específico",
                         description="Genera un embedding para la consulta del usuario y busca fragmentos de documentos semánticamente similares dentro de la base de datos vectorial del curso indicado.")
async def realizar_busqueda_contextual_en_curso( # Nombre de función traducido y más descriptivo
    peticion_busqueda: modelos_api_traducidos.SolicitudBusquedaContextual, # Usar modelo traducido
    envoltorio_bd_pgvector: EnvoltorioPgVector = Depends(obtener_conexion_envoltorio_pgvector),
    proveedor_ia_seleccionado: ProveedorInteligencia = Depends(obtener_instancia_proveedor_inteligencia)
):
    registrador.info(
        f"Recibida solicitud de búsqueda contextual para curso ID '{peticion_busqueda.id_curso}' "
        f"con consulta: '{peticion_busqueda.consulta_usuario[:70]}...' (límite: {peticion_busqueda.numero_resultados})."
    )

    try:
        # Generar embedding para la consulta del usuario usando el proveedor de IA.
        # El método en ProveedorInteligencia ya fue refactorizado a 'generar_embedding'.
        registrador.debug(f"Generando embedding para la consulta: '{peticion_busqueda.consulta_usuario}'.")
        embedding_de_consulta = proveedor_ia_seleccionado.generar_embedding(
            texto_entrada=peticion_busqueda.consulta_usuario
        )

        if not embedding_de_consulta: # Si el embedding es None o lista vacía
            registrador.error("No se pudo generar el embedding para la consulta del usuario.")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Ocurrió un error al procesar la consulta para la búsqueda (generación de embedding fallida)."
            )

        # Buscar fragmentos similares en la base de datos vectorial.
        # El método en EnvoltorioPgVector ya fue refactorizado a 'buscar_fragmentos_similares_por_embedding'.
        registrador.debug(
            f"Buscando fragmentos similares en curso ID '{peticion_busqueda.id_curso}' "
            f"con límite de {peticion_busqueda.numero_resultados} resultados."
        )
        resultados_crudos_bd = envoltorio_bd_pgvector.buscar_fragmentos_similares_por_embedding(
            identificador_curso=peticion_busqueda.id_curso, # El método espera 'identificador_curso'
            embedding_consulta=embedding_de_consulta,
            limite_resultados=peticion_busqueda.numero_resultados
        )

        # Mapear los resultados crudos de la base de datos al modelo de respuesta de la API.
        items_resultado_mapeados: List[modelos_api_traducidos.ItemResultadoBusqueda] = []
        for resultado_crudo_item in resultados_crudos_bd:
            # El payload ya contiene 'texto' y otros metadatos según la implementación de 'buscar_fragmentos_similares_por_embedding'.
            payload_fragmento = resultado_crudo_item.get("payload", {})
            item_mapeado = modelos_api_traducidos.ItemResultadoBusqueda(
                id_fragmento=resultado_crudo_item.get("id_fragmento", ""),
                similitud=resultado_crudo_item.get("similitud", 0.0),
                texto_fragmento=payload_fragmento.get("texto", "Texto no disponible."),
                metadatos=payload_fragmento # Todos los metadatos del payload se incluyen aquí
            )
            items_resultado_mapeados.append(item_mapeado)

        registrador.info(
            f"Búsqueda contextual completada para curso ID '{peticion_busqueda.id_curso}'. "
            f"Se encontraron {len(items_resultado_mapeados)} resultados para la consulta."
        )

        return modelos_api_traducidos.RespuestaBusquedaContextual(
            consulta_original_usuario=peticion_busqueda.consulta_usuario,
            resultados_busqueda=items_resultado_mapeados,
            total_resultados_devueltos=len(items_resultado_mapeados)
        )

    except ErrorBaseDeDatosVectorial as e_bd_vec:
        registrador.error(f"Error específico de la base de datos vectorial durante la búsqueda: {e_bd_vec}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Error al acceder a la base de datos durante la búsqueda: {str(e_bd_vec)}"
        )
    except ErrorProveedorInteligencia as e_prov_ia:
        registrador.error(f"Error específico del proveedor de IA durante la búsqueda: {e_prov_ia}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Error con el servicio de inteligencia artificial durante la búsqueda: {str(e_prov_ia)}"
        )
    except HTTPException: # Re-lanzar HTTPExceptions que puedan originarse en las dependencias
        raise
    except Exception as e_general: # Capturar cualquier otra excepción no esperada
        registrador.exception(f"Error inesperado durante la ejecución de la búsqueda contextual: {e_general}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Se produjo un error interno en el servidor al realizar la búsqueda: {str(e_general)}"
        )

[end of entrenai_refactor/api/rutas/ruta_busqueda.py]
