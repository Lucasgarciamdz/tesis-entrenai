from pathlib import Path
from typing import List, Optional, Dict, Any
import json # Añadido para manipulación de JSON
import re  # Agregado para parsear HTML
import copy

from celery.result import AsyncResult  # Import AsyncResult
from fastapi import APIRouter, HTTPException, Query, Depends, Request
from fastapi.responses import RedirectResponse

from src.entrenai.api.models import (
    MoodleCourse,
    CourseSetupResponse,
    HttpUrl,  # Importar MoodleModule si se va a usar para parsear respuesta de módulos
    IndexedFile,  # Added for the new endpoint
    DeleteFileResponse,  # Added for the new DELETE endpoint
)
from src.entrenai.celery_app import app as celery_app  # Import Celery app instance

# from src.entrenai.core.files.file_tracker import FileTracker # Removed
# from src.entrenai.core.files.file_processor import FileProcessor, FileProcessingError # Removed if not used directly
# from src.entrenai.core.ai.embedding_manager import EmbeddingManager # Removed if not used directly
from src.entrenai.config import (
    moodle_config,
    pgvector_config,
    ollama_config,
    gemini_config,
    base_config,
    n8n_config,
)
from src.entrenai.config.logger import get_logger
from src.entrenai.core.ai.ai_provider import get_ai_wrapper, AIProviderError
from src.entrenai.core.ai.gemini_wrapper import (
    GeminiWrapper,
)  # Keep for type hint if get_ai_client stays
from src.entrenai.core.ai.ollama_wrapper import (
    OllamaWrapper,
)  # Keep for type hint if get_ai_client stays
from src.entrenai.core.clients.moodle_client import MoodleClient, MoodleAPIError
from src.entrenai.core.clients.n8n_client import N8NClient
from src.entrenai.core.db import PgvectorWrapper, PgvectorWrapperError  # Updated import
from src.entrenai.core.tasks import process_moodle_file_task  # Import Celery task

logger = get_logger(__name__)

router = APIRouter(
    prefix="/api/v1",
    tags=["Configuración de Curso y Gestión de IA"],
)


# --- Helper Functions ---
def _extract_chat_config_from_html(html_content: str) -> Dict[str, str]:
    """
    Extrae configuraciones del chat de IA desde el HTML Summary del curso.
    
    Busca patrones específicos en el HTML para extraer:
    - Mensaje inicial/bienvenida
    - Mensaje del sistema 
    - Placeholder del input
    - Título del chat
    
    Returns:
        Dict con las configuraciones encontradas
    """
    config = {}
    
    logger.debug("Procesando HTML content para extraer configuraciones...")
    
    # Patterns más flexibles para buscar configuraciones en el HTML
    # Buscar por los labels específicos que se usan en el HTML generado
    patterns = {
        'initial_messages': [
            r'<strong>Mensajes Iniciales:</strong>\s*["\']([^"\'<]+)["\']',
            r'<strong>Mensajes Iniciales:</strong>\s*([^<]+)',
            r'(?:mensaje[s]?\s+inicial[es]?|bienvenida|saludo)[:\s]*["\']([^"\']+)["\']'
        ],
        'system_message': [
            r'<strong>Mensaje del Sistema:</strong>\s*["\']([^"\'<]+)["\']',
            r'<strong>Mensaje del Sistema:</strong>\s*([^<]+)',
            r'(?:mensaje\s+del?\s+sistema|instrucciones?)[:\s]*["\']([^"\']+)["\']'
        ], 
        'input_placeholder': [
            r'<strong>Marcador de Posición de Entrada:</strong>\s*["\']([^"\'<]+)["\']',
            r'<strong>Marcador de Posición de Entrada:</strong>\s*([^<]+)',
            r'(?:placeholder|marcador\s+de\s+posición|texto\s+de\s+ayuda)[:\s]*["\']([^"\']+)["\']'
        ],
        'chat_title': [
            r'<strong>Título del Chat:</strong>\s*["\']([^"\'<]+)["\']',
            r'<strong>Título del Chat:</strong>\s*([^<]+)',
            r'(?:título\s+del?\s+chat|nombre\s+del?\s+chat)[:\s]*["\']([^"\']+)["\']'
        ]
    }
    
    for key, pattern_list in patterns.items():
        for pattern in pattern_list:
            match = re.search(pattern, html_content, re.IGNORECASE | re.MULTILINE | re.DOTALL)
            if match:
                extracted_value = match.group(1).strip()
                # Limpiar el valor extraído
                if extracted_value and extracted_value != 'No especificado':
                    config[key] = extracted_value
                    logger.info(f"Extraída configuración {key}: '{extracted_value}'")
                    break  # Si encontramos una coincidencia, no buscar más patrones para esta clave
            else:
                logger.debug(f"No se encontró patrón para {key}: {pattern}")
    
    if not config:
        logger.warning("No se encontraron configuraciones válidas en el HTML")
    
    return config

async def _get_course_name_for_operations(course_id: int, moodle: MoodleClient) -> str:
    """
    Retrieves the course name for a given course_id, used for Pgvector operations.
    This logic is shared by refresh_course_files and the new delete_indexed_file endpoint.
    """
    course_name_for_pgvector: Optional[str] = None
    try:
        logger.info(
            f"Obteniendo nombre del curso {course_id} para operaciones de Pgvector..."
        )
        target_user_id_for_name = moodle_config.default_teacher_id
        if target_user_id_for_name:
            courses = moodle.get_courses_by_user(user_id=target_user_id_for_name)
            course = next((c for c in courses if c.id == course_id), None)
            if course:
                course_name_for_pgvector = course.displayname or course.fullname

        if (
            not course_name_for_pgvector
        ):  # If not found under default teacher or no default teacher
            all_courses = moodle.get_all_courses()
            course = next((c for c in all_courses if c.id == course_id), None)
            if course:
                course_name_for_pgvector = course.displayname or course.fullname

        if not course_name_for_pgvector:
            # If still not found after checking all courses, it's a genuine "not found"
            logger.warning(
                f"No se pudo encontrar el curso {course_id} en Moodle para obtener su nombre."
            )
            raise HTTPException(
                status_code=404,
                detail=f"Curso con ID {course_id} no encontrado en Moodle.",
            )

        logger.info(f"Nombre del curso para Pgvector: '{course_name_for_pgvector}'")
        return course_name_for_pgvector
    except MoodleAPIError as e:
        logger.error(
            f"Error de API de Moodle al obtener el nombre del curso {course_id} para Pgvector: {e}"
        )
        raise HTTPException(
            status_code=502,  # Bad Gateway, Moodle error
            detail=f"Error de API de Moodle al intentar obtener el nombre del curso {course_id}.",
        )
    except HTTPException:  # Re-raise HTTPException (e.g. the 404 from above)
        raise
    except Exception as e:  # Catch-all for other unexpected errors
        logger.error(
            f"Error inesperado al obtener el nombre del curso {course_id} para Pgvector: {e}"
        )
        # Using a fallback name as in setup_ia_for_course or refresh_course_files might be an option,
        # but for deletion, it's safer to fail if the name can't be reliably determined.
        # However, the original refresh_course_files uses a fallback `Curso_{course_id}`.
        # For deletion, this could be risky if the fallback name doesn't match what was used for table creation.
        # Sticking to raising an error if not found via Moodle API.
        raise HTTPException(
            status_code=500,
            detail=f"No se pudo determinar el nombre del curso {course_id} para operaciones de base de datos debido a un error interno.",
        )


# --- Inyección de Dependencias para Clientes ---
def get_moodle_client() -> MoodleClient:
    return MoodleClient(config=moodle_config)


def get_pgvector_wrapper() -> (
    PgvectorWrapper
):  # Renamed function and updated return type
    return PgvectorWrapper(config=pgvector_config)  # Updated instantiation


def get_ai_client() -> OllamaWrapper | GeminiWrapper:
    try:
        return get_ai_wrapper()
    except AIProviderError as e:
        logger.error(f"Error al obtener el cliente de IA: {e}")
        if base_config.ai_provider == "gemini":
            logger.warning("Intentando fallback a Ollama ya que Gemini falló")
            try:
                return get_ai_wrapper(ai_provider="ollama")
            except AIProviderError as e2:
                logger.error(f"Error con fallback a Ollama: {e2}")
                raise HTTPException(
                    status_code=500,
                    detail="No se pudo inicializar ningún proveedor de IA disponible.",
                )
        elif base_config.ai_provider == "ollama":
            logger.warning("Intentando fallback a Gemini ya que Ollama falló")
            try:
                return get_ai_wrapper(ai_provider="gemini")
            except AIProviderError as e2:
                logger.error(f"Error con fallback a Gemini: {e2}")
                raise HTTPException(
                    status_code=500,
                    detail="No se pudo inicializar ningún proveedor de IA disponible.",
                )
        else:
            raise HTTPException(
                status_code=500,
                detail=f"Proveedor de IA '{base_config.ai_provider}' no válido. Opciones: 'ollama', 'gemini'",
            )


def get_n8n_client() -> N8NClient:
    return N8NClient(config=n8n_config)


# def get_file_tracker() -> FileTracker: # Removed
#     return FileTracker(db_path=Path(base_config.file_tracker_db_path)) # Removed


# def get_file_processor() -> FileProcessor: # Removed as file_processor dependency is removed
#     return FileProcessor()

# def get_embedding_manager( # Removed as embedding_manager dependency is removed
#     ai_client=Depends(get_ai_client),
# ) -> EmbeddingManager:
#     return EmbeddingManager(ollama_wrapper=ai_client)


@router.get("/courses", response_model=List[MoodleCourse])
async def list_moodle_courses(
    moodle_user_id: Optional[int] = Query(
        None,
        description="ID de Usuario de Moodle del profesor. Si no se provee, usa MOODLE_DEFAULT_TEACHER_ID de la configuración.",
    ),
    client: MoodleClient = Depends(get_moodle_client),
):
    """Obtiene la lista de cursos de Moodle para un profesor."""
    teacher_id_to_use = (
        moodle_user_id
        if moodle_user_id is not None
        else moodle_config.default_teacher_id
    )
    if teacher_id_to_use is None:
        logger.error(
            "No se proporcionó ID de profesor de Moodle y MOODLE_DEFAULT_TEACHER_ID no está configurado."
        )
        raise HTTPException(
            status_code=400,
            detail="Debe proporcionar un ID de profesor de Moodle o MOODLE_DEFAULT_TEACHER_ID debe estar configurado en el servidor.",
        )
    logger.info(
        f"Obteniendo cursos de Moodle para el ID de profesor: {teacher_id_to_use}"
    )
    try:
        courses = client.get_courses_by_user(user_id=teacher_id_to_use)
        return courses
    except MoodleAPIError as e:
        logger.error(f"Error de API de Moodle al obtener cursos: {e}")
        raise HTTPException(status_code=502, detail=f"Error de API de Moodle: {str(e)}")
    except Exception as e:
        logger.exception(f"Error inesperado obteniendo cursos de Moodle: {e}")
        raise HTTPException(
            status_code=500, detail=f"Error interno del servidor: {str(e)}"
        )


@router.delete(
    "/courses/{course_id}/indexed-files/{file_identifier}",
    response_model=DeleteFileResponse,
)
async def delete_indexed_file(
    course_id: int,
    file_identifier: str,  # FastAPI handles URL decoding of path parameters
    moodle: MoodleClient = Depends(get_moodle_client),
    pgvector_db: PgvectorWrapper = Depends(get_pgvector_wrapper),
):
    """
    Elimina un archivo específico y sus datos asociados del sistema de IA
    (chunks en Pgvector y registro en la tabla de seguimiento).
    El document_id para los chunks se deriva de course_id y file_identifier.
    """
    logger.info(
        f"Solicitud para eliminar archivo '{file_identifier}' del curso ID: {course_id}"
    )

    try:
        # 1. Obtener el nombre del curso para operaciones de Pgvector
        # This helper will raise HTTPException (404, 502, or 500) if it fails
        course_name_for_pgvector = await _get_course_name_for_operations(
            course_id, moodle
        )
        logger.info(
            f"Operando sobre la tabla derivada de: '{course_name_for_pgvector}' para la eliminación de chunks."
        )

        # 2. Eliminar chunks del archivo de Pgvector
        # PgvectorWrapper.delete_file_chunks returns True if successful or if document_id not found (idempotent)
        # Construir el document_id para los chunks como se hace en tasks.py
        document_id_for_chunks = f"{course_id}_{file_identifier}"
        logger.info(
            f"Intentando eliminar chunks con document_id derivado: '{document_id_for_chunks}'"
        )
        chunks_deleted_success = pgvector_db.delete_file_chunks(
            course_name=course_name_for_pgvector, document_id=document_id_for_chunks
        )
        if not chunks_deleted_success:
            logger.error(
                f"Falló la eliminación de chunks para el document_id derivado '{document_id_for_chunks}' (archivo '{file_identifier}') del curso '{course_name_for_pgvector}' (ID: {course_id})."
            )
            raise HTTPException(
                status_code=500,
                detail=f"Error al eliminar los datos del archivo '{file_identifier}' (document_id derivado: {document_id_for_chunks}) del almacén de vectores. La tabla de seguimiento no fue modificada.",
            )
        logger.info(
            f"Chunks para el document_id derivado '{document_id_for_chunks}' (archivo '{file_identifier}') eliminados (o no encontrados) del curso '{course_name_for_pgvector}' (ID: {course_id})."
        )

        # 3. Eliminar el archivo de la tabla de seguimiento (file_tracker)
        # PgvectorWrapper.delete_file_from_tracker returns True if successful or if not found (idempotent)
        tracker_deleted_success = pgvector_db.delete_file_from_tracker(
            course_id=course_id, file_identifier=file_identifier
        )
        if not tracker_deleted_success:
            logger.error(
                f"Falló la eliminación del archivo '{file_identifier}' (curso ID: {course_id}) de la tabla de seguimiento, "
                f"aunque los chunks podrían haber sido eliminados."
            )
            # This is a state of partial failure. Chunks might be gone, but tracker entry remains.
            # Or, chunks might have failed AND tracker failed.
            # The message should ideally guide the user or admin.
            raise HTTPException(
                status_code=500,
                detail=f"Error al eliminar el registro del archivo '{file_identifier}' de la tabla de seguimiento. "
                f"Es posible que los datos del archivo hayan sido eliminados del almacén de vectores, pero el seguimiento está inconsistente.",
            )
        logger.info(
            f"Registro del archivo '{file_identifier}' (curso ID: {course_id}) eliminado (o no encontrado) de la tabla de seguimiento."
        )

        # 4. Si ambas operaciones son exitosas (o el archivo/chunks no existían, lo cual es un tipo de éxito para delete)
        success_message = f"Archivo '{file_identifier}' y sus datos asociados eliminados exitosamente para el curso ID {course_id}."
        logger.info(success_message)
        return DeleteFileResponse(message=success_message)

    except (
        HTTPException
    ) as http_exc:  # Re-raise HTTPExceptions (from helper or from here)
        raise http_exc
    except MoodleAPIError as e:  # Should be caught by the helper, but as a safeguard
        logger.error(
            f"Error de API de Moodle durante la eliminación del archivo '{file_identifier}' para el curso {course_id}: {e}"
        )
        raise HTTPException(status_code=502, detail=f"Error de API de Moodle: {str(e)}")
    except PgvectorWrapperError as e:  # Specific errors from PgvectorWrapper if any are not handled by True/False returns
        logger.error(
            f"Error de PgvectorWrapper durante la eliminación del archivo '{file_identifier}' para el curso {course_id}: {e}"
        )
        raise HTTPException(status_code=500, detail=f"Error de base de datos: {str(e)}")
    except Exception as e:
        logger.exception(
            f"Error inesperado durante la eliminación del archivo '{file_identifier}' para el curso {course_id}: {e}"
        )
        raise HTTPException(
            status_code=500, detail=f"Error interno del servidor: {str(e)}"
        )


@router.post("/courses/{course_id}/setup-ia", response_model=CourseSetupResponse)
async def setup_ia_for_course(
    course_id: int,
    request: Request,
    course_name_query: str = Query(
        None,
        alias="courseName",
        description="Nombre del curso para la IA (opcional, se intentará obtener de Moodle).",
    ),
    initial_messages: Optional[str] = Query(
        None,
        alias="initialMessages",
        description="Mensajes iniciales para el chat de IA.",
    ),
    system_message: Optional[str] = Query(
        None,
        alias="systemMessage",
        description="Mensaje del sistema para el agente de IA (se añadirá al mensaje por defecto).",
    ),
    input_placeholder: Optional[str] = Query(
        None,
        alias="inputPlaceholder",
        description="Texto de marcador de posición para el campo de entrada del chat.",
    ),
    chat_title: Optional[str] = Query(
        None, alias="chatTitle", description="Título del chat de IA."
    ),
    moodle: MoodleClient = Depends(get_moodle_client),
    pgvector_db: PgvectorWrapper = Depends(get_pgvector_wrapper),
    ai_client=Depends(get_ai_client),  # Updated dependency
    n8n: N8NClient = Depends(get_n8n_client),
):
    """Configura la IA para un curso específico de Moodle."""
    logger.info(
        f"Iniciando configuración de IA para el curso de Moodle ID: {course_id}"
    )

    course_name_str: str = ""
    if course_name_query:
        course_name_str = course_name_query
        logger.info(f"Nombre del curso proporcionado en la query: '{course_name_str}'")
    else:
        try:
            logger.info(
                f"Intentando obtener nombre del curso {course_id} desde Moodle..."
            )
            moodle_course_details: Optional[MoodleCourse] = None
            if moodle_config.default_teacher_id:
                courses = moodle.get_courses_by_user(
                    user_id=moodle_config.default_teacher_id
                )
                moodle_course_details = next(
                    (c for c in courses if c.id == course_id), None
                )
            if not moodle_course_details:
                all_courses = moodle.get_all_courses()
                moodle_course_details = next(
                    (c for c in all_courses if c.id == course_id), None
                )
            if moodle_course_details:
                course_name_str = (
                    moodle_course_details.displayname or moodle_course_details.fullname
                )
                logger.info(f"Nombre del curso obtenido de Moodle: '{course_name_str}'")
            else:
                logger.warning(
                    f"No se pudo encontrar el curso {course_id} en Moodle para obtener su nombre."
                )
        except Exception as e:
            logger.warning(
                f"Excepción al obtener el nombre del curso {course_id} desde Moodle: {e}"
            )
        if not course_name_str:
            course_name_str = f"Curso_{course_id}"
            logger.warning(
                f"Usando nombre de curso por defecto para Qdrant: '{course_name_str}'"
            )

    if not course_name_str:
        logger.error(
            f"El nombre del curso para el ID {course_id} no pudo ser determinado."
        )
        raise HTTPException(
            status_code=500,
            detail=f"No se pudo determinar el nombre del curso {course_id}.",
        )

    vector_size = pgvector_config.default_vector_size  # Updated config usage
    pgvector_table_name = pgvector_db.get_table_name(
        course_name_str
    )  # Updated method call

    moodle_section_name_desired = (
        moodle_config.course_folder_name
    )  # Nombre deseado para la sección
    moodle_folder_name = "Documentos Entrenai"
    moodle_chat_link_name = moodle_config.chat_link_name
    moodle_refresh_link_name = moodle_config.refresh_link_name

    response_details = CourseSetupResponse(
        course_id=course_id,
        status="pendiente",
        message=f"Configuración iniciada para el curso {course_id} ('{course_name_str}').",
        qdrant_collection_name=pgvector_table_name,
        # Renamed field for clarity, though model might not reflect this directly
    )

    try:
        logger.info(
            f"Asegurando tabla Pgvector '{pgvector_table_name}' para curso '{course_name_str}' con tamaño de vector {vector_size}"
        )
        # Removed qdrant.client check as PgvectorWrapper handles connection internally
        if not pgvector_db.ensure_table(
            course_name_str, vector_size
        ):  # Updated method call
            response_details.status = "fallido"
            response_details.message = (
                f"Falló al asegurar la tabla Pgvector '{pgvector_table_name}'."
            )
            logger.error(response_details.message)
            raise HTTPException(status_code=500, detail=response_details.message)
        logger.info(f"Tabla Pgvector '{pgvector_table_name}' asegurada.")

        logger.info(
            f"Configurando workflow de chat N8N para curso '{course_name_str}' (ID: {course_id})"
        )
        logger.info(f"El tableName para el nodo PGVector en N8N se establecerá a: '{pgvector_table_name}'")

        # --- INICIO DE MODIFICACIÓN DEL WORKFLOW JSON (en memoria) ---
        # Cargar la plantilla del workflow para asegurar que tableName se actualice.
        # CWD es /Users/lucas/facultad/tesis_entrenai
        workflow_template_path = Path("src/entrenai/n8n_workflow.json")
        
        if not workflow_template_path.exists():
            logger.warning(
                f"No se encontró la plantilla del workflow de N8N en: {workflow_template_path}. "
                "N8NClient deberá manejar la configuración del tableName usando qdrant_collection_name."
            )
        else:
            try:
                with open(workflow_template_path, 'r', encoding='utf-8') as f:
                    workflow_data = json.load(f)

                pg_vector_node_found_and_updated = False
                for node in workflow_data.get("nodes", []):
                    if node.get("type") == "@n8n/n8n-nodes-langchain.vectorStorePGVector" and \
                       node.get("parameters", {}).get("mode") == "retrieve-as-tool":
                        original_table_name = node["parameters"].get("tableName")
                        node["parameters"]["tableName"] = pgvector_table_name # Usar el nombre de tabla del curso
                        pg_vector_node_found_and_updated = True
                        logger.info(
                            f"Nodo PGVector ('retrieve-as-tool') encontrado en la plantilla n8n_workflow.json. "
                            f"Actualizando 'tableName' de '{original_table_name}' a '{pgvector_table_name}' en la copia en memoria."
                        )
                        break 
                
                if not pg_vector_node_found_and_updated:
                    logger.warning(
                        "No se encontró el nodo Postgres PGVector Store ('retrieve-as-tool') en la plantilla "
                        "n8n_workflow.json para actualizar 'tableName'. N8NClient deberá manejar esta configuración."
                    )
            except json.JSONDecodeError as e:
                logger.error(f"Error al decodificar la plantilla JSON del workflow de N8N desde {workflow_template_path}: {e}")
            except Exception as e:
                logger.error(f"Error inesperado al procesar la plantilla del workflow de N8N desde {workflow_template_path}: {e}")
        # --- FIN DE MODIFICACIÓN DEL WORKFLOW JSON ---

        # Preparar parámetros de IA según el proveedor seleccionado
        if base_config.ai_provider == "gemini":
            ai_params = {
                "api_key": gemini_config.api_key,
                "embedding_model": gemini_config.embedding_model,
                "qa_model": gemini_config.text_model,
            }
        else:  # Ollama por defecto
            ai_params = {
                "host": ollama_config.host,
                "embedding_model": ollama_config.embedding_model,
                "qa_model": ollama_config.qa_model,
            }

        n8n_chat_url_str = n8n.configure_and_deploy_chat_workflow(
            course_id=course_id,
            course_name=course_name_str,
            qdrant_collection_name=pgvector_table_name,
            ai_config_params=ai_params,
            initial_messages=initial_messages,
            system_message=system_message,
            input_placeholder=input_placeholder,
            chat_title=chat_title,
        )

        if not n8n_chat_url_str:
            logger.warning(
                f"No se pudo configurar/obtener automáticamente la URL del chat de N8N para el curso '{course_name_str}'."
            )
            response_details.message += (
                " URL del chat de N8N no configurada automáticamente."
            )
            n8n_chat_url_str = n8n_config.webhook_url
        response_details.n8n_chat_url = (
            HttpUrl(n8n_chat_url_str) if n8n_chat_url_str else None
        )
        logger.info(
            f"URL del chat de N8N para curso '{course_name_str}': {response_details.n8n_chat_url}"
        )

        logger.info(
            f"Paso 1: Creando/obteniendo estructura de sección de Moodle para curso {course_id} (nombre deseado: '{moodle_section_name_desired}')"
        )
        created_section_structure = moodle.create_course_section(
            course_id, moodle_section_name_desired, position=1
        )
        if not created_section_structure or not created_section_structure.id:
            response_details.status = "fallido"
            response_details.message = f"Falló la creación de la estructura de la sección de Moodle para el curso {course_id}."
            logger.error(response_details.message)
            raise HTTPException(status_code=500, detail=response_details.message)

        section_id_to_update = created_section_structure.id
        response_details.moodle_section_id = section_id_to_update
        logger.info(
            f"Estructura de sección de Moodle (ID: {section_id_to_update}, Nombre Actual: '{created_section_structure.name}') obtenida/creada."
        )

        # Construir URLs y HTML summary
        # Old way:
        # refresh_path = router.url_path_for("refresh_files", course_id=course_id)
        # refresh_files_url = str(request.base_url.replace(path=str(refresh_path)))
        # Construir URLs para los enlaces
        refresh_files_url = (
            str(request.base_url).rstrip("/")
            + "/ui/manage_files.html?course_id="
            + str(course_id)
        )
        
        refresh_chat_config_url = (
            str(request.base_url).rstrip("/")
            + f"/api/v1/courses/{course_id}/refresh-chat-config"
        )

        n8n_chat_url_for_moodle = (
            str(response_details.n8n_chat_url).rstrip('/') if response_details.n8n_chat_url else "#"
        )

        # Mensaje para el profesor sobre la edición
        edit_instruction_message = """
<p><strong>Nota para el profesor:</strong> Puede modificar las configuraciones del chat directamente en la sección "Configuración del Chat de IA" a continuación. Después de realizar cambios, use el enlace "Actualizar Configuraciones del Chat" para aplicar los cambios al sistema de IA.</p>
"""

        # Construir el summary HTML con los nuevos campos
        html_summary = f"""
<h4>Recursos de Entrenai IA</h4>
<p>Utilice esta sección para interactuar con la Inteligencia Artificial de asistencia para este curso.</p>
<ul>
    <li><a href="{n8n_chat_url_for_moodle}" target="_blank">{moodle_chat_link_name}</a>: Acceda aquí para chatear con la IA.</li>
    <li>Carpeta "<strong>{moodle_folder_name}</strong>": Suba aquí los documentos PDF, DOCX, PPTX que la IA utilizará como base de conocimiento.</li>
    <li><a href="{refresh_files_url}" target="_blank">{moodle_refresh_link_name}</a>: Haga clic aquí después de subir nuevos archivos o modificar existentes en la carpeta "{moodle_folder_name}" para que la IA los procese.</li>
    <li><a href="{refresh_chat_config_url}" target="_blank">Actualizar Configuraciones del Chat</a>: Haga clic aquí después de modificar las configuraciones del chat (abajo) para aplicar los cambios.</li>
</ul>
{edit_instruction_message}
<h5>Configuración del Chat de IA:</h5>
<ul>
    <li><strong>Mensajes Iniciales:</strong> "{initial_messages if initial_messages else 'No especificado'}"</li>
    <li><strong>Mensaje del Sistema:</strong> "{system_message if system_message else 'No especificado'}"</li>
    <li><strong>Marcador de Posición de Entrada:</strong> "{input_placeholder if input_placeholder else 'No especificado'}"</li>
    <li><strong>Título del Chat:</strong> "{chat_title if chat_title else 'No especificado'}"</li>
</ul>
"""

        # Payload para actualizar la sección (nombre, summary) y añadir módulos
        update_section_and_modules_payload = {
            "courseid": course_id,
            "sections": [
                {
                    "type": "id",
                    "section": section_id_to_update,
                    "name": moodle_section_name_desired,  # Nombre deseado
                    "summary": html_summary,
                    "summaryformat": 1,  # 1 para HTML
                    "visible": 1,
                }
            ],
        }

        logger.info(
            f"Paso 2: Actualizando sección ID {section_id_to_update} con nombre '{moodle_section_name_desired}', summary y módulos."
        )
        logger.debug(
            f"Payload para local_wsmanagesections_update_sections: {update_section_and_modules_payload}"
        )

        update_result = moodle._make_request(
            "local_wsmanagesections_update_sections", update_section_and_modules_payload
        )
        logger.info(f"Resultado de actualización de sección y módulos: {update_result}")

        # Verificar módulos creados (opcional, para obtener IDs)
        # Por ahora, asumimos que la creación fue exitosa si no hubo error.
        # Los IDs de los módulos no se capturan en response_details con este flujo simplificado.

        response_details.status = "exitoso"
        response_details.message = f"Configuración de Entrenai IA completada exitosamente para el curso {course_id} ('{course_name_str}')."
        logger.info(response_details.message)
        return response_details

    except HTTPException as http_exc:
        logger.error(
            f"HTTPException durante configuración de IA para curso {course_id}: {http_exc.detail}"
        )
        raise http_exc
    except MoodleAPIError as e:
        logger.error(
            f"Error de API de Moodle durante configuración de IA para curso {course_id}: {e}"
        )
        response_details.status = "fallido"
        response_details.message = f"Error de API de Moodle: {str(e)}"
        raise HTTPException(status_code=502, detail=response_details.message)
    except Exception as e:
        logger.exception(
            f"Error inesperado durante configuración de IA para curso {course_id}: {e}"
        )
        response_details.status = "fallido"
        response_details.message = f"Error interno del servidor: {str(e)}"
        raise HTTPException(status_code=500, detail=response_details.message)


@router.get("/courses/{course_id}/refresh-files", name="refresh_files")
async def refresh_course_files(
    course_id: int,
    moodle: MoodleClient = Depends(get_moodle_client),
    pgvector_db: PgvectorWrapper = Depends(get_pgvector_wrapper),
    # ai_client: OllamaWrapper | GeminiWrapper = Depends(get_ai_client), # Removed, task handles AI client
    # embedding_manager: EmbeddingManager = Depends(get_embedding_manager), # Removed, task handles embeddings
    # file_processor: FileProcessor = Depends(get_file_processor), # Removed, task handles file processing
):
    """
    Inicia el refresco y procesamiento asíncrono de archivos para un curso.

    Esta operación identifica archivos nuevos o modificados en la carpeta designada
    del curso en Moodle y despacha tareas Celery individuales para procesar cada archivo.
    El procesamiento incluye la descarga, extracción de texto, formateo a Markdown,
    generación de embeddings y almacenamiento en la base de datos vectorial (Pgvector).

    La API responde inmediatamente con una lista de IDs de las tareas despachadas,
    permitiendo al cliente rastrear el progreso de forma asíncrona usando el endpoint
    `/api/v1/task/{task_id}/status`.

    Respuesta:
    - `message`: Mensaje indicando el inicio del proceso y el número de tareas despachadas.
    - `course_id`: ID del curso.
    - `files_identified_for_processing`: Número de archivos que se determinó necesitan procesamiento.
    - `tasks_dispatched`: Número de tareas Celery efectivamente despachadas.
    - `task_ids`: Lista de strings, donde cada string es el ID de una tarea Celery despachada.
    """
    logger.info(
        f"Iniciando proceso de refresco de archivos para el curso ID: {course_id}"
    )

    # Obtener nombre del curso para Pgvector usando función helper
    try:
        course_name_for_pgvector = await _get_course_name_for_operations(
            course_id, moodle
        )
    except HTTPException as e:
        if e.status_code == 404:
            # Usar fallback si el curso no se encuentra
            course_name_for_pgvector = f"Curso_{course_id}"
            logger.warning(
                f"No se pudo obtener el nombre para el curso ID {course_id}, usando fallback: '{course_name_for_pgvector}' para Pgvector."
            )
        else:
            raise

    target_section_name = moodle_config.course_folder_name
    target_folder_name = "Documentos Entrenai"  # As defined in setup_ia_for_course

    files_to_process_count = 0
    tasks_dispatched_count = 0
    dispatched_task_ids: List[str] = []  # To store IDs of dispatched tasks
    # Ruta que el API podría usar para crear el directorio en el host/API-environment
    course_download_dir_on_api_host = (
        Path(base_config.download_dir) / str(course_id)
    ).resolve()

    # Ruta que se pasará a la tarea Celery (relativa al WORKDIR del contenedor Celery, o absoluta dentro del contenedor)
    # base_config.download_dir es 'data/downloads'
    # Esto resultará en 'data/downloads/<course_id>'
    download_dir_for_task_str = str(Path(base_config.download_dir) / str(course_id))

    try:
        # 1. Asegurar que existe la tabla de Pgvector antes de procesar archivos
        vector_size = pgvector_config.default_vector_size  # Updated config usage
        logger.info(
            f"Asegurando tabla Pgvector para curso {course_id} ('{course_name_for_pgvector}') con tamaño de vector {vector_size}"
        )
        if not pgvector_db.ensure_table(
            course_name_for_pgvector, vector_size
        ):  # Updated method call
            logger.error(
                f"Falló al asegurar la tabla Pgvector para el curso {course_id} ('{course_name_for_pgvector}')"
            )
            raise HTTPException(
                status_code=500,
                detail=f"Falló al asegurar la tabla Pgvector para el curso {course_id} ('{course_name_for_pgvector}')",
            )
        logger.info(
            f"Tabla Pgvector '{pgvector_db.get_table_name(course_name_for_pgvector)}' asegurada."
        )

        # 2. Obtener todos los contenidos del curso para encontrar la sección y módulos
        all_course_contents = moodle._make_request(
            "core_course_get_contents", payload_params={"courseid": course_id}
        )
        if not isinstance(all_course_contents, list):
            raise HTTPException(
                status_code=500,
                detail="No se pudieron obtener los contenidos del curso.",
            )

        # 3. Buscar la sección objetivo por nombre
        found_section_id: Optional[int] = None
        for section_data in all_course_contents:
            if section_data.get("name") == target_section_name:
                found_section_id = section_data.get("id")
                break

        if not found_section_id:
            logger.error(
                f"Sección objetivo '{target_section_name}' no encontrada en curso {course_id}."
            )
            raise HTTPException(
                status_code=404,
                detail=f"Sección de configuración '{target_section_name}' no encontrada.",
            )
        logger.info(
            f"Sección '{target_section_name}' encontrada con ID: {found_section_id}."
        )

        # 4. Encontrar el módulo de carpeta en la sección
        folder_module = moodle.get_course_module_by_name(
            course_id, found_section_id, target_folder_name, "folder"
        )
        if not folder_module or not folder_module.id:
            logger.error(
                f"Carpeta '{target_folder_name}' no encontrada en curso {course_id}, sección {found_section_id}."
            )
            raise HTTPException(
                status_code=404,
                detail=f"Carpeta designada de Moodle '{target_folder_name}' no encontrada.",
            )

        folder_cmid = folder_module.id
        logger.info(
            f"Carpeta '{target_folder_name}' encontrada con cmid: {folder_cmid}."
        )

        # 5. Obtener los archivos de la carpeta
        moodle_files = moodle.get_folder_files(folder_cmid=folder_cmid)
        if not moodle_files:
            logger.info(
                f"No se encontraron archivos en la carpeta '{target_folder_name}' (cmid: {folder_cmid})."
            )
            return {
                "message": "No se encontraron archivos en la carpeta designada de Moodle para procesar.",
                "course_id": course_id,
                "files_identified_for_processing": 0,
                "tasks_dispatched": 0,
            }

        logger.info(
            f"Se encontraron {len(moodle_files)} archivos en la carpeta de Moodle. Verificando archivos nuevos/modificados..."
        )
        # Asegurar que el directorio de descarga del curso exista (creado por el API en su entorno)
        course_download_dir_on_api_host.mkdir(
            parents=True, exist_ok=True
        )  # Ensure download dir for the course exists

        # 6. Loop through Moodle files and dispatch tasks
        for mf in moodle_files:
            if not mf.filename or not mf.fileurl or mf.timemodified is None:
                logger.warning(
                    f"Omitiendo archivo de Moodle con datos incompletos: {mf.model_dump_json(exclude_none=True)}"
                )
                continue

            if pgvector_db.is_file_new_or_modified(
                course_id, mf.filename, mf.timemodified
            ):
                files_to_process_count += 1
                logger.info(
                    f"Archivo '{mf.filename}' es nuevo o modificado. Despachando tarea Celery..."
                )

                # Prepare AI provider configuration
                ai_provider_config_payload: Dict[str, Any] = {
                    "selected_provider": base_config.ai_provider
                }
                if base_config.ai_provider == "gemini":
                    ai_provider_config_payload["gemini"] = vars(gemini_config)
                else:  # Default to ollama
                    ai_provider_config_payload["ollama"] = vars(ollama_config)

                # Dispatch Celery task
                try:
                    task_result = process_moodle_file_task.delay(
                        course_id=course_id,
                        course_name_for_pgvector=course_name_for_pgvector,
                        moodle_file_info={
                            "filename": mf.filename,
                            "filepath": mf.filepath,
                            "filesize": mf.filesize,
                            "fileurl": str(
                                mf.fileurl
                            ),  # Explicitly convert HttpUrl to string
                            "timemodified": mf.timemodified,
                            "mimetype": mf.mimetype,
                        },
                        download_dir_str=download_dir_for_task_str,  # <--- CAMBIO CLAVE AQUÍ
                        ai_provider_config=ai_provider_config_payload,
                        pgvector_config_dict=vars(pgvector_config),
                        moodle_config_dict=vars(moodle_config),
                        base_config_dict=vars(base_config),
                    )
                    tasks_dispatched_count += 1
                    dispatched_task_ids.append(task_result.id)
                    logger.info(
                        f"Tarea Celery {task_result.id} despachada para archivo: {mf.filename}"
                    )
                except Exception as e_task:
                    logger.error(
                        f"Error al despachar tarea Celery para {mf.filename}: {e_task}"
                    )
                    # Potentially add to a list of failed dispatches if needed for response

            else:
                logger.info(
                    f"Archivo '{mf.filename}' no ha sido modificado. Omitiendo."
                )

        # 7. Cleanup (optional, as tasks handle individual file cleanup)
        # The main course_download_dir might still be useful for tasks if they are slow to pick up
        # Or if multiple tasks share it. Consider if this cleanup is still needed.
        # For now, individual tasks clean up their own downloaded files.
        # If the directory is meant to be cleaned only if empty:
        try:
            if course_download_dir_on_api_host.exists() and not any(
                course_download_dir_on_api_host.iterdir()
            ):
                # This check might be problematic if tasks haven't run yet.
                # Consider if this cleanup is still appropriate here.
                # shutil.rmtree(course_download_dir_on_api_host)
                # logger.info(
                #     f"Directorio de descargas del curso vacío (aparentemente) eliminado: {course_download_dir_on_api_host}"
                # )
                logger.info(
                    f"Revisión de directorio de descargas {course_download_dir_on_api_host} completada. Las tareas gestionarán los archivos individuales."
                )
        except Exception as e_rm:
            logger.warning(
                f"No se pudo realizar la limpieza del directorio de descargas del curso {course_download_dir_on_api_host}: {e_rm}"
            )

        # 8. Prepare and return response
        response_message = (
            f"Refresco de archivos iniciado para el curso {course_id}. "
            f"{tasks_dispatched_count} tareas despachadas para {files_to_process_count} archivos identificados para procesamiento."
        )
        logger.info(response_message)
        return {
            "message": response_message,
            "course_id": course_id,
            "files_identified_for_processing": files_to_process_count,
            "tasks_dispatched": tasks_dispatched_count,
            "task_ids": dispatched_task_ids,
        }

    except HTTPException as http_exc:
        logger.error(
            f"HTTPException durante el inicio del refresco de archivos para curso {course_id}: {http_exc.detail}"
        )
        raise http_exc
    except MoodleAPIError as e:
        logger.error(
            f"Error de API de Moodle durante el inicio del refresco de archivos para curso {course_id}: {e}"
        )
        raise HTTPException(status_code=502, detail=f"Error de API de Moodle: {str(e)}")
    except Exception as e:
        logger.exception(
            f"Error inesperado durante el inicio del refresco de archivos para curso {course_id}: {e}"
        )
        raise HTTPException(
            status_code=500, detail=f"Error interno del servidor: {str(e)}"
        )


@router.get("/task/{task_id}/status", name="get_task_status")
async def get_task_status(task_id: str):
    """
    Consulta el estado de una tarea Celery específica por su ID.

    Permite rastrear el progreso de las tareas de procesamiento de archivos despachadas
    por el endpoint `refresh_course_files`.

    Args:
        task_id (str): El ID de la tarea Celery a consultar.

    Returns:
        dict: Un diccionario con la información del estado de la tarea:
            - `task_id` (str): El ID de la tarea consultada.
            - `status` (str): El estado actual de la tarea (ej. "PENDING", "STARTED",
                              "SUCCESS", "FAILURE", "RETRY", "REVOKED").
            - `result` (Any): El resultado de la tarea.
                - Si `status` es "SUCCESS", este es el valor de retorno de la función de la tarea.
                - Si `status` es "FAILURE", este es la representación string de la excepción.
                - Para otros estados, puede ser `None` o información de estado intermedio.
            - `traceback` (str, optional): Si la tarea falló (`status`="FAILURE"),
              esto contendrá el traceback de la excepción. `None` en otros casos.
    """
    logger.info(f"Consultando estado para la tarea ID: {task_id}")
    task_result = AsyncResult(task_id, app=celery_app)

    status_response = {
        "task_id": task_id,
        "status": task_result.status,
        "result": None,
        "traceback": None,
    }

    if task_result.successful():
        status_response["result"] = task_result.result
    elif task_result.failed():
        status_response["result"] = str(
            task_result.result
        )  # Exception object as string
        status_response["traceback"] = task_result.traceback
    else:
        # For PENDING, STARTED, RETRY, REVOKED, result is often None or not the final outcome
        status_response["result"] = task_result.result if task_result.result else None

    logger.debug(f"Estado de la tarea {task_id}: {status_response}")
    return status_response


@router.get("/courses/{course_id}/n8n-workflow-config")
async def get_n8n_workflow_config(
    course_id: int,
    moodle: MoodleClient = Depends(get_moodle_client),
    n8n: N8NClient = Depends(get_n8n_client),
):
    """
    Obtiene la configuración actual de los parámetros del workflow de n8n
    (initialMessages, inputPlaceholder, title, systemMessage) para un curso.
    """
    logger.info(f"Solicitud para obtener configuración de workflow n8n para curso ID: {course_id}")

    try:
        course_name_for_n8n = await _get_course_name_for_operations(course_id, moodle)
        workflow_name_prefix = f"Entrenai - {course_id}"
        exact_workflow_name = f"{workflow_name_prefix} - {course_name_for_n8n}"

        # Buscar el workflow por nombre
        workflows = n8n.get_workflows_list()
        target_workflow = None
        for wf in workflows:
            if wf.name == exact_workflow_name:
                target_workflow = wf
                break
            # Fallback: si no hay coincidencia exacta, buscar por prefijo y tomar el primero activo
            if not target_workflow and wf.name and wf.name.startswith(workflow_name_prefix) and wf.active:
                target_workflow = wf

        if not target_workflow or not target_workflow.id:
            logger.warning(f"No se encontró workflow de n8n para el curso ID: {course_id} con nombre '{exact_workflow_name}'.")
            raise HTTPException(
                status_code=404,
                detail=f"No se encontró un workflow de n8n activo para el curso ID {course_id}.",
            )

        workflow_details = n8n.get_workflow_details(target_workflow.id)

        config_data: Dict[str, Optional[str]] = {
            "initialMessages": None,
            "inputPlaceholder": None,
            "chatTitle": None,
            "systemMessage": None,
        }

        if workflow_details:
            # Para satisfacer al linter, reasignamos a una variable que se sabe que no es None
            # Esto es una técnica común para ayudar a los linters con el flujo de control de Optional
            actual_workflow_details = workflow_details

            # Extraer los parámetros del nodo 'When chat message received'
            chat_trigger_node = next(
                (
                    node
                    for node in actual_workflow_details.nodes
                    if node.type == "@n8n/n8n-nodes-langchain.chatTrigger"
                ),
                None,
            )

            # Extraer los parámetros del nodo 'AI Agent'
            ai_agent_node = next(
                (
                    node
                    for node in actual_workflow_details.nodes
                    if node.type == "@n8n/n8n-nodes-langchain.agent"
                ),
                None,
            )

            if chat_trigger_node and chat_trigger_node.parameters:
                config_data["initialMessages"] = chat_trigger_node.parameters.initialMessages
                if chat_trigger_node.parameters.options:
                    config_data["inputPlaceholder"] = chat_trigger_node.parameters.options.get("inputPlaceholder")
                    config_data["chatTitle"] = chat_trigger_node.parameters.options.get("title")

            if ai_agent_node and ai_agent_node.parameters and ai_agent_node.parameters.options:
                config_data["systemMessage"] = ai_agent_node.parameters.options.get("systemMessage")
        else:
            logger.error(f"No se pudieron obtener los detalles del workflow n8n ID: {target_workflow.id}")
            raise HTTPException(
                status_code=500,
                detail=f"No se pudieron obtener los detalles del workflow n8n para el curso ID {course_id}.",
            )

        logger.info(f"Configuración de workflow n8n obtenida para curso ID {course_id}: {config_data}")
        return config_data

    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        logger.exception(f"Error inesperado al obtener la configuración del workflow n8n para el curso {course_id}: {e}")
        raise HTTPException(
            status_code=500, detail=f"Error interno del servidor: {str(e)}"
        )

@router.get("/courses/{course_id}/indexed-files", response_model=List[IndexedFile])
async def get_indexed_files_for_course(
    course_id: int,
    pgvector_db: PgvectorWrapper = Depends(get_pgvector_wrapper),
):
    """Recupera una lista de archivos indexados y sus fechas de última modificación para un ID de curso específico."""
    logger.info(
        f"Solicitud para obtener archivos indexados para el curso ID: {course_id}"
    )
    try:
        processed_files_timestamps = pgvector_db.get_processed_files_timestamps(
            course_id=course_id
        )

        if processed_files_timestamps is None or not processed_files_timestamps:
            logger.warning(
                f"No se encontraron archivos indexados para el curso ID: {course_id} o el curso no existe en el seguimiento."
            )
            raise HTTPException(
                status_code=404,
                detail=f"No se encontraron archivos indexados para el curso ID {course_id} o el curso no se encuentra.",
            )

        indexed_files = [
            IndexedFile(filename=filename, last_modified_moodle=timestamp)
            for filename, timestamp in processed_files_timestamps.items()
        ]

        logger.info(
            f"Se encontraron {len(indexed_files)} archivos indexados para el curso ID: {course_id}"
        )
        return indexed_files

    except (
        PgvectorWrapperError
    ) as e:  # Asumiendo que PgvectorWrapper puede lanzar un error específico
        logger.error(
            f"Error de PgvectorWrapper al obtener archivos indexados para el curso {course_id}: {e}"
        )
        raise HTTPException(
            status_code=500,
            detail=f"Error de base de datos al obtener archivos indexados: {str(e)}",
        )
    except HTTPException as http_exc:  # Re-raise HTTPExceptions para no enmascararlas
        raise http_exc
    except Exception as e:
        logger.exception(
            f"Error inesperado al obtener archivos indexados para el curso {course_id}: {e}"
        )
        raise HTTPException(
            status_code=500, detail=f"Error interno del servidor: {str(e)}"
        )


def clean_n8n_workflow_for_update(workflow_data: dict) -> dict:
    """
    Limpia el JSON del workflow de n8n para que sea compatible con la API de actualización.
    Elimina campos no permitidos y asegura que 'credentials' sea un objeto.
    """
    workflow_fields_to_remove = [
        "createdAt", "updatedAt", "active", "versionId", "tags", "pinData"
    ]
    node_fields_to_remove = [
        "typeVersion", "disabled", "notes", "createdAt", "updatedAt", "retryOf", "retrySuccessId"
    ]
    cleaned = {k: v for k, v in workflow_data.items() if k not in workflow_fields_to_remove}
    # Limpiar nodos
    cleaned_nodes = []
    for node in cleaned.get("nodes", []):
        node_clean = {k: v for k, v in node.items() if k not in node_fields_to_remove}
        
        # Solo el nodo chatTrigger debe tener webhookId
        node_type = node_clean.get('type', '')
        if node_type == "@n8n/n8n-nodes-langchain.chatTrigger":
            # Asegurar que webhookId sea string si existe
            if 'webhookId' in node_clean and node_clean['webhookId'] is not None:
                node_clean['webhookId'] = str(node_clean['webhookId'])
        else:
            # Para todos los otros nodos, eliminar webhookId si existe
            if 'webhookId' in node_clean:
                del node_clean['webhookId']
        
        # Asegurar que credentials sea un objeto o eliminarlo si está vacío
        if "credentials" in node_clean and (not isinstance(node_clean["credentials"], dict) or not node_clean["credentials"]):
            node_clean["credentials"] = {}
        elif "credentials" not in node_clean:
            node_clean["credentials"] = {}
        
        cleaned_nodes.append(node_clean)
    cleaned["nodes"] = cleaned_nodes
    return cleaned


def build_n8n_workflow_from_template(template_path: str, chat_config: dict) -> dict:
    """
    Lee el workflow de referencia y actualiza solo los parámetros de chat según chat_config.
    """
    with open(template_path, 'r', encoding='utf-8') as f:
        workflow = json.load(f)
    workflow = copy.deepcopy(workflow)
    for node in workflow.get("nodes", []):
        if node.get("type") == "@n8n/n8n-nodes-langchain.chatTrigger":
            params = node.get("parameters", {})
            options = params.get("options", {})
            if "initial_messages" in chat_config:
                params["initialMessages"] = chat_config["initial_messages"]
            if "input_placeholder" in chat_config:
                options["inputPlaceholder"] = chat_config["input_placeholder"]
            if "chat_title" in chat_config:
                options["title"] = chat_config["chat_title"]
            params["options"] = options
            node["parameters"] = params
        if node.get("type") == "@n8n/n8n-nodes-langchain.agent":
            params = node.get("parameters", {})
            options = params.get("options", {})
            if "system_message" in chat_config:
                options["systemMessage"] = chat_config["system_message"]
            params["options"] = options
            node["parameters"] = params
        # Asegurar que credentials sea un objeto
        if "credentials" in node and not isinstance(node["credentials"], dict):
            node["credentials"] = {}
    return workflow


def update_n8n_workflow_params_from_template(current_workflow: dict, template_path: str, chat_config: dict) -> dict:
    """
    Actualiza los parámetros de chat del workflow actual con los valores del chat_config,
    manteniendo la estructura y los ids del workflow actual.
    """
    with open(template_path, 'r', encoding='utf-8') as f:
        template = json.load(f)

    template_nodes = {n['type']: n for n in template.get('nodes', [])}
    updated = copy.deepcopy(current_workflow)
    
    def clean_value(value: str) -> str:
        """Limpia un valor de configuración, removiendo comillas extras y 'No especificado'"""
        if not value:
            return ""
        # Remover comillas del inicio y final si existen
        value = value.strip('"\'')
        # Si es "No especificado", retornar string vacío
        if value.lower() == "no especificado":
            return ""
        return value

    # Limpiar y asegurar webhookId correcto para todos los nodos
    for node in updated.get('nodes', []):
        node_type = node.get('type', '')
        
        # Solo el nodo chatTrigger debe tener webhookId
        if node_type == "@n8n/n8n-nodes-langchain.chatTrigger":
            # Asegurar que webhookId sea string si existe
            if 'webhookId' in node and node['webhookId'] is not None:
                node['webhookId'] = str(node['webhookId'])
            elif 'webhookId' not in node or node['webhookId'] is None:
                # Si no hay webhookId, mantener None o generar uno nuevo si es necesario
                # En este caso, mantener el existente para no romper el workflow
                pass
        else:
            # Para todos los otros nodos, eliminar webhookId si existe
            if 'webhookId' in node:
                del node['webhookId']
            
        t_node = template_nodes.get(node_type)
        if not t_node:
            continue
            
        # chatTrigger
        if node_type == "@n8n/n8n-nodes-langchain.chatTrigger":
            params = node.get("parameters", {})
            t_params = t_node.get("parameters", {})
            options = params.get("options", {})
            t_options = t_params.get("options", {})
            
            # Actualizar initialMessages si es necesario
            initial_msg = clean_value(chat_config.get("initial_messages", ""))
            if initial_msg:
                params["initialMessages"] = initial_msg
            
            # Actualizar solo los campos específicos en options si son válidos
            input_placeholder = clean_value(chat_config.get("input_placeholder", ""))
            if input_placeholder:
                options["inputPlaceholder"] = input_placeholder
                
            chat_title = clean_value(chat_config.get("chat_title", ""))
            if chat_title:
                options["title"] = chat_title
            
            # Limpiar campos existentes que contienen "No especificado"
            for key in ["inputPlaceholder", "title"]:
                if key in options:
                    cleaned = clean_value(str(options[key]))
                    if cleaned:
                        options[key] = cleaned
                    elif key in t_options:
                        options[key] = t_options[key]
            
            # Asegurar que los campos requeridos existan y mantener los valores existentes si no hay nuevos
            for key in ["allowFileUploads", "subtitle", "customCss"]:
                if key not in options and key in t_options:
                    options[key] = t_options[key]
                elif key in options and not options[key]:
                    if key in t_options:
                        options[key] = t_options[key]
            
            params["options"] = options
            node["parameters"] = params
            
        # agent
        if node_type == "@n8n/n8n-nodes-langchain.agent":
            params = node.get("parameters", {})
            t_params = t_node.get("parameters", {})
            options = params.get("options", {})
            t_options = t_params.get("options", {})
            
            system_msg = clean_value(chat_config.get("system_message", ""))
            if system_msg:
                options["systemMessage"] = system_msg
            elif "systemMessage" in options:
                # Limpiar el systemMessage existente
                cleaned = clean_value(str(options["systemMessage"]))
                if cleaned:
                    options["systemMessage"] = cleaned
                elif "systemMessage" in t_options:
                    options["systemMessage"] = t_options["systemMessage"]
            elif "systemMessage" in t_options:
                options["systemMessage"] = t_options["systemMessage"]
            
            params["options"] = options
            node["parameters"] = params
            
        # Asegurar que credentials sea un objeto vacío si es None o no es dict
        if "credentials" in node and (node["credentials"] is None or not isinstance(node["credentials"], dict)):
            node["credentials"] = {}
            
    return updated


@router.get("/courses/{course_id}/refresh-chat-config", name="refresh_chat_config")
async def refresh_chat_config(
    course_id: int,
    request: Request,
    moodle: MoodleClient = Depends(get_moodle_client),
    n8n: N8NClient = Depends(get_n8n_client),
):
    """
    Actualiza las configuraciones del chat de IA en el workflow de N8N 
    leyendo el HTML Summary del curso desde Moodle.
    
    Este endpoint:
    1. Obtiene el HTML Summary del curso desde Moodle
    2. Extrae las configuraciones del chat (mensajes, placeholders, etc.)
    3. Busca el workflow activo de N8N para el curso
    4. Actualiza el workflow con las nuevas configuraciones
    5. Redirige a una página de log con el resultado
    
    Returns:
        RedirectResponse a la página de log con el resultado
    """
    logger.info(
        f"Iniciando actualización de configuraciones del chat para el curso ID: {course_id}"
    )
    
    try:
        # 1. Obtener información del curso desde Moodle
        logger.info(f"Obteniendo información del curso {course_id} desde Moodle...")
        all_courses = moodle.get_all_courses()
        course_info = next((c for c in all_courses if c.id == course_id), None)
        if not course_info:
            # Redirigir con error
            base_url = str(request.base_url).rstrip("/")
            return RedirectResponse(
                url=f"{base_url}/ui/config_log.html?course_id={course_id}&status=error&message=Curso no encontrado en Moodle",
                status_code=302
            )
        
        logger.info(f"Curso encontrado: {course_info.fullname}")
        
        # 2. Buscar la sección de Entrenai específicamente
        logger.info("Buscando sección de Entrenai en el curso...")
        entrenai_section_name = moodle_config.course_folder_name  # "Entrenai Documents" por defecto
        entrenai_section = moodle.get_section_by_name(course_id, entrenai_section_name)
        
        if not entrenai_section:
            logger.warning(f"No se encontró la sección '{entrenai_section_name}' en el curso {course_id}")
            base_url = str(request.base_url).rstrip("/")
            return RedirectResponse(
                url=f"{base_url}/ui/config_log.html?course_id={course_id}&status=error&message=No se encontró la sección de Entrenai en el curso",
                status_code=302
            )
        
        logger.info(f"Sección de Entrenai encontrada: {entrenai_section.name} (ID: {entrenai_section.id})")
        
        # 3. Obtener detalles completos de la sección para acceder al contenido actualizado
        logger.info("Obteniendo detalles completos de la sección...")
        # Siempre intentar obtener el summary actualizado usando get_section_details
        section_details = moodle.get_section_details(entrenai_section.id, course_id=course_id)
        if section_details and section_details.summary:
            html_summary = section_details.summary
            logger.info("Detalles de la sección obtenidos exitosamente (summary actualizado)")
        else:
            # Fallback: usar el summary de la sección encontrada por nombre
            html_summary = entrenai_section.summary or ""
            logger.warning("No se pudieron obtener los detalles actualizados de la sección, usando summary de la sección encontrada por nombre")
        
        # 4. Extraer configuraciones del HTML Summary de la sección de Entrenai
        logger.info("Extrayendo configuraciones del HTML Summary de la sección Entrenai...")
        logger.debug(f"HTML Summary de la sección (primeros 500 caracteres): {html_summary[:500]}")
        
        chat_config = _extract_chat_config_from_html(html_summary)
        logger.info(f"Configuraciones extraídas: {chat_config}")
        
        if not chat_config:
            logger.warning("No se encontraron configuraciones de chat en el HTML Summary de la sección Entrenai")
            base_url = str(request.base_url).rstrip("/")
            return RedirectResponse(
                url=f"{base_url}/ui/config_log.html?course_id={course_id}&status=error&message=No se encontraron configuraciones de chat para actualizar",
                status_code=302
            )
        
        # 5. Buscar workflow activo para el curso
        logger.info("Buscando workflow de N8N para el curso...")
        workflows = n8n.get_workflows_list()
        target_workflow = None
        
        # Buscar workflow que contenga el nombre del curso o ID del curso
        course_name_patterns = [
            course_info.fullname,
            course_info.displayname,
            f"curso_{course_id}",
            f"entrenai_{course_id}"
        ]
        
        for workflow in workflows or []:
            for pattern in course_name_patterns:
                if pattern and pattern.lower() in workflow.name.lower():
                    target_workflow = workflow
                    logger.info(f"Encontrado workflow: {workflow.name} (ID: {workflow.id})")
                    break
            if target_workflow:
                break
        
        if not target_workflow:
            # Si no encontramos workflow específico, buscar el workflow "Entrenai" genérico
            for workflow in workflows or []:
                if "entrenai" in workflow.name.lower():
                    target_workflow = workflow
                    logger.info(f"Usando workflow genérico: {workflow.name} (ID: {workflow.id})")
                    break
        
        if not target_workflow:
            base_url = str(request.base_url).rstrip("/")
            return RedirectResponse(
                url=f"{base_url}/ui/config_log.html?course_id={course_id}&status=error&message=No se encontró workflow de N8N para actualizar",
                status_code=302
            )
        
        # 6. Obtener detalles completos del workflow
        logger.info(f"Obteniendo detalles del workflow {target_workflow.id}...")
        workflow_details = n8n.get_workflow_details(target_workflow.id)
        print("----------------DETAILS----------------\n\n\n")
        print(workflow_details)
        print("--------------------------------\n\n\n")
        if not workflow_details:
            base_url = str(request.base_url).rstrip("/")
            return RedirectResponse(
                url=f"{base_url}/ui/config_log.html?course_id={course_id}&status=error&message=No se pudieron obtener los detalles del workflow",
                status_code=302
            )
        
        # 7. Actualizar configuraciones en el workflow
        logger.info("Actualizando configuraciones del workflow...")
        updated = False
        workflow_data = workflow_details.dict()
        
        # Buscar y actualizar el nodo chatTrigger
        for node in workflow_data.get("nodes", []):
            if node.get("type") == "@n8n/n8n-nodes-langchain.chatTrigger":
                node_params = node.get("parameters", {})
                node_options = node_params.get("options", {})
                
                # Actualizar configuraciones encontradas
                if "initial_messages" in chat_config:
                    node_params["initialMessages"] = chat_config["initial_messages"]
                    updated = True
                    logger.info(f"Actualizado initialMessages: {chat_config['initial_messages']}")
                
                if "input_placeholder" in chat_config:
                    node_options["inputPlaceholder"] = chat_config["input_placeholder"]
                    updated = True
                    logger.info(f"Actualizado inputPlaceholder: {chat_config['input_placeholder']}")
                
                if "chat_title" in chat_config:
                    node_options["title"] = chat_config["chat_title"]
                    updated = True
                    logger.info(f"Actualizado title: {chat_config['chat_title']}")
                
                # Guardar cambios en options
                node_params["options"] = node_options
                node["parameters"] = node_params
                break
        
        # Buscar y actualizar el nodo AI Agent (para system message)
        if "system_message" in chat_config:
            for node in workflow_data.get("nodes", []):
                if node.get("type") == "@n8n/n8n-nodes-langchain.agent":
                    node_params = node.get("parameters", {})
                    node_options = node_params.get("options", {})
                    node_options["systemMessage"] = chat_config["system_message"]
                    node_params["options"] = node_options
                    node["parameters"] = node_params
                    updated = True
                    logger.info(f"Actualizado systemMessage: {chat_config['system_message']}")
                    break
        
        if not updated:
            base_url = str(request.base_url).rstrip("/")
            return RedirectResponse(
                url=f"{base_url}/ui/config_log.html?course_id={course_id}&status=error&message=No se realizaron actualizaciones (configuraciones no compatibles)",
                status_code=302
            )
        
        # 8. Enviar workflow actualizado a N8N usando la plantilla y manteniendo los ids
        logger.info("Actualizando workflow manteniendo estructura e ids...")
        template_path = "src/entrenai/n8n_workflow.json"

        print("--------------------------------\n\n\n")
        print(workflow_data)
        print("--------------------------------\n\n\n")
        workflow_data_clean = update_n8n_workflow_params_from_template(
            workflow_data, template_path, chat_config
        )


        print("--------------------------------\n\n\n")
        print(workflow_data_clean)
        print("--------------------------------\n\n\n")
        updated_workflow = n8n.update_workflow(target_workflow.id, workflow_data_clean)
        
        if not updated_workflow:
            base_url = str(request.base_url).rstrip("/")
            return RedirectResponse(
                url=f"{base_url}/ui/config_log.html?course_id={course_id}&status=error&message=Error al actualizar el workflow en N8N",
                status_code=302
            )
        
        logger.info("Configuraciones del chat actualizadas exitosamente")
        
        # Redirigir con éxito
        base_url = str(request.base_url).rstrip("/")
        config_count = len([k for k in chat_config.keys() if updated])
        return RedirectResponse(
            url=f"{base_url}/ui/config_log.html?course_id={course_id}&status=success&message=Se actualizaron {config_count} configuraciones del chat exitosamente",
            status_code=302
        )
        
    except Exception as e:
        logger.exception(f"Error inesperado al actualizar configuraciones del chat: {e}")
        base_url = str(request.base_url).rstrip("/")
        return RedirectResponse(
            url=f"{base_url}/ui/config_log.html?course_id={course_id}&status=error&message=Error interno del servidor",
            status_code=302
        )