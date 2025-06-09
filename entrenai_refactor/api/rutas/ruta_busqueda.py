from fastapi import APIRouter, HTTPException, Depends, status
from typing import List # Optional no se usa directamente aquí, pero List sí.

# Importar modelos Pydantic refactorizados (usando sus nombres en español)
from entrenai_refactor.api import modelos as modelos_api
# Importar clases refactorizadas del núcleo
from entrenai_refactor.nucleo.bd import EnvoltorioPgVector, ErrorBaseDeDatosVectorial
from entrenai_refactor.nucleo.ia import ProveedorInteligencia, ErrorProveedorInteligencia
from entrenai_refactor.config.registrador import obtener_registrador

registrador = obtener_registrador(__name__) # Registrador para este módulo de rutas

# Definición del enrutador para los endpoints de búsqueda
enrutador_busqueda = APIRouter(
    prefix="/v1/busquedas", # Prefijo común para todos los endpoints en este enrutador
    tags=["Búsqueda Semántica y Contextual"], # Etiqueta para la documentación de OpenAPI/Swagger
)

# --- Funciones de Dependencia (Inyección de Dependencias de FastAPI) ---

def obtener_dependencia_envoltorio_pgvector() -> EnvoltorioPgVector: # Nombre de función más explícito
    """
    Dependencia de FastAPI para obtener una instancia del EnvoltorioPgVector.
    Maneja errores de inicialización y los convierte en HTTPExceptions para la respuesta API.
    Esta instancia será utilizada por los endpoints para interactuar con la base de datos vectorial.
    """
    try:
        # EnvoltorioPgVector se inicializa de forma perezosa; la conexión real
        # a la base de datos ocurre cuando se utiliza por primera vez.
        return EnvoltorioPgVector()
    except ErrorBaseDeDatosVectorial as e_error_bd_vectorial: # Captura la excepción personalizada del envoltorio
        registrador.error(f"Error crítico al inicializar EnvoltorioPgVector: {e_error_bd_vectorial}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"No se pudo establecer conexión o configurar el servicio de base de datos vectorial: {str(e_error_bd_vectorial)}"
        )
    except Exception as e_error_inesperado: # Otros errores inesperados durante la instanciación
        registrador.exception(f"Error inesperado al instanciar EnvoltorioPgVector: {e_error_inesperado}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno del servidor al intentar configurar el acceso a la base de datos vectorial."
        )

def obtener_dependencia_proveedor_inteligencia() -> ProveedorInteligencia: # Nombre de función más explícito
    """
    Dependencia de FastAPI para obtener una instancia del ProveedorInteligencia.
    Maneja errores de inicialización y los convierte en HTTPExceptions.
    Esta instancia permite acceder a los servicios de IA (generación de embeddings, etc.).
    """
    try:
        return ProveedorInteligencia()
    except ErrorProveedorInteligencia as e_error_proveedor_ia: # Captura la excepción personalizada del proveedor
        registrador.error(f"Error crítico al inicializar ProveedorInteligencia: {e_error_proveedor_ia}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"No se pudo inicializar el proveedor de inteligencia artificial configurado en el sistema: {str(e_error_proveedor_ia)}"
        )
    except Exception as e_error_inesperado: # Otros errores durante la instanciación
        registrador.exception(f"Error inesperado al instanciar ProveedorInteligencia: {e_error_inesperado}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno del servidor al intentar configurar el proveedor de inteligencia artificial."
        )

# --- Endpoint de Búsqueda Contextual ---

@enrutador_busqueda.post("/contextual",
                         response_model=modelos_api.RespuestaBusquedaSemantica, # Modelo Pydantic para la respuesta
                         summary="Realizar Búsqueda Semántica en un Curso",
                         description="Este endpoint recibe una consulta de usuario y un ID de curso. Genera un embedding para la consulta y busca fragmentos de documentos semánticamente similares dentro de la base de datos vectorial asociada al curso indicado. Devuelve una lista de los fragmentos más relevantes encontrados.")
async def realizar_busqueda_semantica_en_curso( # Nombre de función más descriptivo
    peticion_de_busqueda: modelos_api.SolicitudBusquedaSemantica, # Modelo Pydantic para el cuerpo de la petición
    envoltorio_bd: EnvoltorioPgVector = Depends(obtener_dependencia_envoltorio_pgvector), # Inyección de dependencia
    proveedor_ia: ProveedorInteligencia = Depends(obtener_dependencia_proveedor_inteligencia) # Inyección de dependencia
):
    """
    Maneja las solicitudes de búsqueda semántica.
    1. Genera un embedding para la consulta del usuario.
    2. Busca fragmentos similares en la base de datos vectorial del curso.
    3. Formatea y devuelve los resultados.
    """
    registrador.info(
        f"Recibida solicitud de búsqueda semántica para curso ID '{peticion_de_busqueda.id_curso}' "
        f"con consulta: '{peticion_de_busqueda.consulta_usuario[:70]}...' (límite de resultados: {peticion_de_busqueda.limite_resultados_similares})."
    )

    try:
        # Paso 1: Generar embedding para la consulta del usuario.
        registrador.debug(f"Generando embedding para la consulta del usuario: '{peticion_de_busqueda.consulta_usuario}'.")
        embedding_consulta_generado = proveedor_ia.generar_embedding(
            texto_entrada=peticion_de_busqueda.consulta_usuario
        )

        if not embedding_consulta_generado: # Comprobar si el embedding es None o una lista vacía
            registrador.error("No se pudo generar el embedding para la consulta del usuario. El proveedor de IA devolvió un resultado vacío.")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Ocurrió un error al procesar la consulta para la búsqueda (falló la generación del embedding)."
            )
        registrador.debug(f"Embedding generado para la consulta (dimensión: {len(embedding_consulta_generado)}).")

        # Paso 2: Buscar fragmentos similares en la base de datos vectorial.
        registrador.debug(
            f"Buscando fragmentos similares en la base de datos para el curso ID '{peticion_de_busqueda.id_curso}' "
            f"con un límite de {peticion_de_busqueda.limite_resultados_similares} resultados."
        )
        # El método 'buscar_fragmentos_similares_por_embedding' en EnvoltorioPgVector ya fue refactorizado.
        resultados_crudos_desde_bd = envoltorio_bd.buscar_fragmentos_similares_por_embedding(
            identificador_curso=peticion_de_busqueda.id_curso, # El método espera 'identificador_curso'
            embedding_de_consulta=embedding_consulta_generado, # Nombre de parámetro refactorizado
            limite_resultados=peticion_de_busqueda.limite_resultados_similares
            # Se podría añadir 'factor_ef_search_hnsw' si se quisiera controlar desde la API.
        )

        # Paso 3: Mapear los resultados crudos de la BD al modelo de respuesta de la API.
        items_resultado_para_api: List[modelos_api.ItemResultadoBusquedaSemantica] = []
        for resultado_bd_item_crudo in resultados_crudos_desde_bd:
            # El payload ya contiene 'texto' y otros metadatos según la implementación de 'buscar_fragmentos_similares_por_embedding'.
            payload_fragmento_bd = resultado_bd_item_crudo.get("payload", {})
            item_api_mapeado = modelos_api.ItemResultadoBusquedaSemantica(
                id_fragmento=resultado_bd_item_crudo.get("id_fragmento", "ID_DESCONOCIDO"), # Valor por defecto si falta
                puntuacion_similitud=resultado_bd_item_crudo.get("similitud", 0.0), # Usar alias 'similitud'
                distancia_vectorial=resultado_bd_item_crudo.get("distancia"), # Nuevo campo opcional
                texto_completo_fragmento=payload_fragmento_bd.get("texto", "Texto no disponible."), # Usar alias 'texto_fragmento'
                metadatos_asociados_fragmento=payload_fragmento_bd # Todos los metadatos del payload se incluyen aquí
            )
            items_resultado_para_api.append(item_api_mapeado)

        registrador.info(
            f"Búsqueda semántica completada para curso ID '{peticion_de_busqueda.id_curso}'. "
            f"Se encontraron {len(items_resultado_para_api)} resultados para la consulta del usuario."
        )

        # Construir y devolver la respuesta final.
        return modelos_api.RespuestaBusquedaSemantica(
            consulta_original_del_usuario=peticion_de_busqueda.consulta_usuario, # Usar alias 'consulta_original'
            resultados_de_la_busqueda=items_resultado_para_api, # Usar alias 'resultados'
            numero_total_resultados_devueltos=len(items_resultado_para_api) # Usar alias 'total_resultados'
        )

    except ErrorBaseDeDatosVectorial as e_error_bd_busqueda:
        registrador.error(f"Error específico de la base de datos vectorial durante la búsqueda semántica: {e_error_bd_busqueda}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Error al acceder a la base de datos durante la búsqueda semántica: {str(e_error_bd_busqueda)}"
        )
    except ErrorProveedorInteligencia as e_error_ia_busqueda:
        registrador.error(f"Error específico del proveedor de IA durante la búsqueda semántica: {e_error_ia_busqueda}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Error con el servicio de inteligencia artificial durante la búsqueda semántica: {str(e_error_ia_busqueda)}"
        )
    except HTTPException: # Re-lanzar HTTPExceptions que puedan originarse en las dependencias para no enmascararlas.
        raise
    except Exception as e_error_general_busqueda: # Capturar cualquier otra excepción no esperada.
        registrador.exception(f"Error inesperado durante la ejecución de la búsqueda semántica: {e_error_general_busqueda}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Se produjo un error interno en el servidor al realizar la búsqueda semántica: {str(e_error_general_busqueda)}"
        )
[end of entrenai_refactor/api/rutas/ruta_busqueda.py]
