from typing import List, Optional, Union

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
# Importaciones para servicios (lazy imports en las funciones de dependencia)
from src.entrenai.core.services.pgvector_service import PgvectorService
from src.entrenai.core.services.n8n_workflow_service import N8NWorkflowService  
from src.entrenai.core.services.moodle_integration_service import MoodleIntegrationService
from src.entrenai.core.services.course_setup_service import CourseSetupService
from src.entrenai.core.utils.course_utils import get_course_name_for_operations
from src.entrenai.celery_app import app as celery_app  # Import Celery app instance

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
from src.entrenai.celery_tasks import forward_file_processing_to_api as process_moodle_file_task # Import Celery task for forwarding to API

logger = get_logger(__name__)

# Constants
DEFAULT_UNSPECIFIED_TEXT = "No especificado"

router = APIRouter(
    prefix="/api/v1",
    tags=["Configuración de Curso y Gestión de IA"],
)


# --- Helper Functions ---





# --- Inyección de Dependencias para Clientes ---
def get_moodle_client() -> MoodleClient:
    return MoodleClient(config=moodle_config)


def get_pgvector_wrapper() -> PgvectorWrapper:
    return PgvectorWrapper(config=pgvector_config)


def get_ai_client() -> Union[OllamaWrapper, GeminiWrapper]:
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


# --- Inyección de Dependencias para Servicios ---
def get_pgvector_service(pgvector_wrapper: PgvectorWrapper = Depends(get_pgvector_wrapper)) -> PgvectorService:
    return PgvectorService(pgvector_wrapper)


def get_n8n_workflow_service(n8n_client: N8NClient = Depends(get_n8n_client)) -> N8NWorkflowService:
    return N8NWorkflowService(n8n_client)


def get_moodle_integration_service(moodle_client: MoodleClient = Depends(get_moodle_client)) -> MoodleIntegrationService:
    return MoodleIntegrationService(moodle_client)


def get_course_setup_service(
    pgvector_service: PgvectorService = Depends(get_pgvector_service),
    n8n_service: N8NWorkflowService = Depends(get_n8n_workflow_service),
    moodle_service: MoodleIntegrationService = Depends(get_moodle_integration_service),
    moodle_client: MoodleClient = Depends(get_moodle_client),
) -> CourseSetupService:
    return CourseSetupService(pgvector_service, n8n_service, moodle_service, moodle_client)


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
        course_name_for_pgvector = await get_course_name_for_operations(
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
    course_setup_service: CourseSetupService = Depends(get_course_setup_service),
):
    """Configura la IA para un curso específico de Moodle."""
    try:
        base_url = str(request.base_url).rstrip("/")
        
        return await course_setup_service.setup_course(
            course_id=course_id,
            base_url=base_url,
            course_name_query=course_name_query,
            initial_messages=initial_messages,
            system_message=system_message,
            input_placeholder=input_placeholder,
            chat_title=chat_title,
        )
    except Exception as e:
        logger.error(f"Error en setup_ia_for_course para curso {course_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error interno del servidor: {str(e)}"
        )


@router.get("/courses/{course_id}/refresh-files", name="refresh_files")
async def refresh_course_files(
    course_id: int,
    moodle: MoodleClient = Depends(get_moodle_client),
    pgvector_db: PgvectorWrapper = Depends(get_pgvector_wrapper),
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
        course_name_for_pgvector = await get_course_name_for_operations(
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
    filenames_by_task_id: Dict[str, str] = {}  # To store filename mapping for frontend
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
                    filenames_by_task_id[task_result.id] = mf.filename  # Store filename mapping
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
            "filenames_by_task_id": filenames_by_task_id,
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
            - `filename` (str): El nombre del archivo siendo procesado (si está disponible).
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
        "filename": None,
    }

    # Intentar extraer el nombre del archivo de los argumentos de la tarea o del resultado
    try:
        if hasattr(task_result, 'args') and task_result.args:
            # Los argumentos están en orden: course_id, course_name_for_pgvector, moodle_file_info, ...
            if len(task_result.args) >= 3 and isinstance(task_result.args[2], dict):
                moodle_file_info = task_result.args[2]
                status_response["filename"] = moodle_file_info.get("filename", "archivo_desconocido")
    except Exception as e:
        logger.warning(f"No se pudo extraer el nombre del archivo de la tarea {task_id}: {e}")

    if task_result.successful():
        task_result_data = task_result.result
        status_response["result"] = task_result_data
        # Si el resultado contiene información del archivo, usar esa información
        if isinstance(task_result_data, dict) and "filename" in task_result_data:
            status_response["filename"] = task_result_data["filename"]
    elif task_result.failed():
        task_result_data = task_result.result
        status_response["result"] = str(task_result_data)  # Exception object as string
        status_response["traceback"] = task_result.traceback
        # Intentar extraer filename del resultado de error
        if isinstance(task_result_data, dict) and "filename" in task_result_data:
            status_response["filename"] = task_result_data["filename"]
    else:
        # For PENDING, STARTED, RETRY, REVOKED, result is often None or not the final outcome
        status_response["result"] = task_result.result if task_result.result else None

    # Si no pudimos obtener el filename de ninguna manera, usar un placeholder
    if not status_response["filename"]:
        status_response["filename"] = f"Tarea {task_id[:8]}"

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
        course_name_for_n8n = await get_course_name_for_operations(course_id, moodle)
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
@router.get("/courses/{course_id}/refresh-chat-config", name="refresh_chat_config")
async def refresh_chat_config(
    course_id: int,
    request: Request,
    moodle: MoodleClient = Depends(get_moodle_client),
    n8n: N8NClient = Depends(get_n8n_client),
    pgvector_db: PgvectorWrapper = Depends(get_pgvector_wrapper),
    moodle_service: MoodleIntegrationService = Depends(get_moodle_integration_service),
):
    """
    Refreshes the N8n chat workflow configuration for a given course.

    Steps:
    1.  Accepts `PgvectorWrapper` as a dependency.
    2.  Obtains `course_name_str` using `get_course_name_for_operations`.
    3.  Determines `pgvector_table_name` using `pgvector_db.get_table_name(course_name_str)`.
    4.  Identifies the existing N8n workflow for the course and get its ID.
        If multiple workflows match, attempts to find the active one.
        If no specific workflow is found, logs a warning and attempts to proceed.
    5.  Fetches the Moodle section summary using `moodle.get_section_details`.
    6.  Extracts chat configuration from the HTML summary using `moodle_service.extract_chat_config_from_html`.
        If no configuration is found, redirects with an error.
    7.  If an existing N8n workflow ID was found, calls `n8n.delete_workflow(existing_workflow_id)`.
        Logs the outcome and proceeds even if deletion fails.
    8.  Prepares `ai_params` (Gemini/Ollama configuration).
    9.  Calls `n8n.configure_and_deploy_chat_workflow()` to create and activate a new workflow.
    10. If `new_n8n_chat_url` is not obtained, redirects with an error.
    11. Re-constructs the `html_summary` string for the Moodle section.
    12. Updates the Moodle course section's summary.
    13. Redirects to `config_log.html` with a success or error message.
    """
    logger.info(
        f"Iniciando refresco de configuración de chat para el curso ID: {course_id}"
    )
    base_url = str(request.base_url).rstrip("/")
    redirect_url_base = f"{base_url}/ui/config_log.html?course_id={course_id}"

    try:
        # 1. & 2. Obtain course_name_str
        logger.info(f"Obteniendo nombre del curso {course_id} para operaciones...")
        try:
            course_name_str = await get_course_name_for_operations(course_id, moodle)
        except HTTPException as e:
            logger.error(f"Error al obtener nombre del curso: {e.detail}")
            return RedirectResponse(
                url=f"{redirect_url_base}&status=error&message=Error al obtener nombre del curso: {e.detail}",
                status_code=302,
            )
        logger.info(f"Nombre del curso obtenido: '{course_name_str}'")

        # 3. Determine pgvector_table_name
        pgvector_table_name = pgvector_db.get_table_name(course_name_str)
        logger.info(f"Nombre de tabla Pgvector: '{pgvector_table_name}'")

        # 5. Fetch Moodle section and extract chat config
        logger.info(f"Buscando sección de Moodle '{moodle_config.course_folder_name}' en curso {course_id}...")
        moodle_section_name_desired = moodle_config.course_folder_name
        
        # Try to get the section by its desired name using the correct method
        entrenai_section = moodle.get_section_by_name(course_id, moodle_section_name_desired)
        if not entrenai_section:
            logger.error(f"No se encontró la sección '{moodle_section_name_desired}' en el curso {course_id}.")
            return RedirectResponse(
                url=f"{redirect_url_base}&status=error&message=Sección '{moodle_section_name_desired}' no encontrada en Moodle.",
                status_code=302,
            )
        
        target_section_id = entrenai_section.id
        logger.info(f"Sección '{moodle_section_name_desired}' encontrada con ID: {target_section_id}. Obteniendo detalles...")
        
        # Fetch the specific section's details to get the latest summary
        section_details = moodle.get_section_details(section_id=target_section_id, course_id=course_id)

        if not section_details or not section_details.summary:
            logger.error(f"No se pudo obtener el summary de la sección ID {target_section_id} del curso {course_id}.")
            return RedirectResponse(
                url=f"{redirect_url_base}&status=error&message=No se pudo obtener el contenido de la sección de Moodle.",
                status_code=302,
            )
        html_summary = section_details.summary
        logger.info(f"Summary de la sección ID {target_section_id} obtenido.")

        # 6. Extract chat configuration from HTML summary
        logger.info("Extrayendo configuraciones del chat desde el HTML summary...")
        chat_config = moodle_service.extract_chat_config_from_html(html_summary)
        logger.info(f"Configuraciones del chat extraídas: {chat_config}")
        if not chat_config:
            logger.warning(f"No se encontraron configuraciones de chat válidas en el HTML summary de la sección {target_section_id}.")
            return RedirectResponse(
                url=f"{redirect_url_base}&status=error&message=No se encontraron configuraciones de chat para actualizar en el Moodle summary.",
                status_code=302,
            )

        # 4. Identify existing N8n workflow
        logger.info(f"Buscando workflow existente de N8N para curso '{course_name_str}' (ID: {course_id})...")
        existing_workflow_id: Optional[str] = None
        # Prioritize exact name match first
        exact_workflow_name = f"Entrenai - {course_id} - {course_name_str}"
        # Fallback prefix if exact name changes or for wider matching
        workflow_name_prefix = f"Entrenai - {course_id}"
        
        all_n8n_workflows = n8n.get_workflows_list()
        
        # Try exact match first
        for wf in all_n8n_workflows:
            if wf.name == exact_workflow_name:
                if wf.active: # Prioritize active exact match
                    existing_workflow_id = wf.id
                    logger.info(f"Encontrado workflow activo con nombre exacto: '{wf.name}' (ID: {existing_workflow_id})")
                    break
                elif not existing_workflow_id: # Store inactive exact match if no active one found yet
                    existing_workflow_id = wf.id
                    logger.info(f"Encontrado workflow inactivo con nombre exacto: '{wf.name}' (ID: {existing_workflow_id})")
        
        # If no exact match, try prefix match (active preferred)
        if not existing_workflow_id:
            active_prefix_match = None
            inactive_prefix_match = None
            for wf in all_n8n_workflows:
                if wf.name and wf.name.startswith(workflow_name_prefix):
                    if wf.active:
                        active_prefix_match = wf.id
                        logger.info(f"Encontrado workflow activo con prefijo: '{wf.name}' (ID: {active_prefix_match})")
                        break
                    elif not inactive_prefix_match: # Store first inactive prefix match
                        inactive_prefix_match = wf.id
                        logger.info(f"Encontrado workflow inactivo con prefijo: '{wf.name}' (ID: {inactive_prefix_match})")

            existing_workflow_id = active_prefix_match or inactive_prefix_match

        if existing_workflow_id:
            logger.info(f"Workflow de N8N existente identificado con ID: {existing_workflow_id}")
        else:
            logger.warning(
                f"No se encontró un workflow de N8N específico para '{exact_workflow_name}' o con prefijo '{workflow_name_prefix}'. "
                "Se procederá a crear uno nuevo. Esto es normal si es la primera configuración del chat."
            )

        # 7. If an existing N8n workflow ID was found, delete it
        if existing_workflow_id:
            logger.info(f"Intentando eliminar workflow de N8N existente ID: {existing_workflow_id}...")
            try:
                delete_success = n8n.delete_workflow(existing_workflow_id)
                if delete_success:
                    logger.info(f"Workflow de N8N ID: {existing_workflow_id} eliminado exitosamente.")
                else:
                    logger.warning(f"No se pudo eliminar el workflow de N8N ID: {existing_workflow_id} o ya no existía. Se procederá a crear uno nuevo.")
            except Exception as e_del_wf:
                logger.error(f"Error al intentar eliminar el workflow de N8N ID: {existing_workflow_id}: {e_del_wf}. Se procederá a crear uno nuevo.")
        
        # 8. Prepare ai_params (similar to setup_ia_for_course)
        logger.info(f"Preparando parámetros de IA basados en la configuración: {base_config.ai_provider}")
        if base_config.ai_provider == "gemini":
            ai_params = {
                "api_key": gemini_config.api_key,
                "embedding_model": gemini_config.embedding_model,
                "qa_model": gemini_config.text_model,
            }
        elif base_config.ai_provider == "ollama":
            ai_params = {
                "host": ollama_config.host,
                "embedding_model": ollama_config.embedding_model,
                "qa_model": ollama_config.qa_model,
            }
        else:
            logger.error(f"Proveedor de IA no soportado: {base_config.ai_provider}")
            return RedirectResponse(
                url=f"{redirect_url_base}&status=error&message=Proveedor de IA no soportado: {base_config.ai_provider}",
                status_code=302,
            )
        logger.debug(f"Parámetros de IA preparados: {ai_params}")

        # 9. Call n8n.configure_and_deploy_chat_workflow()
        logger.info(f"Configurando y desplegando nuevo workflow de chat N8N para curso '{course_name_str}' (ID: {course_id})")
        logger.info(f"Usando nombre de tabla Pgvector para N8N: '{pgvector_table_name}'")
        
        # Preparar parámetros para N8N - solo pasar valores válidos, no "No especificado"
        def get_n8n_param(value):
            return None if value == DEFAULT_UNSPECIFIED_TEXT else value
        
        new_n8n_chat_url: Optional[HttpUrl] = None
        try:
            # Pass extracted chat parameters to the configuration function
            new_n8n_chat_url_str = n8n.configure_and_deploy_chat_workflow(
                course_id=course_id,
                course_name=course_name_str, # course_name_str for consistency
                qdrant_collection_name=pgvector_table_name, # This will be used as tableName for PGVector node
                ai_config_params=ai_params,
                initial_messages=get_n8n_param(chat_config.get("initial_messages")),
                system_message=get_n8n_param(chat_config.get("system_message")),
                input_placeholder=get_n8n_param(chat_config.get("input_placeholder")),
                chat_title=get_n8n_param(chat_config.get("chat_title")),
            )
            if new_n8n_chat_url_str:
                new_n8n_chat_url = HttpUrl(new_n8n_chat_url_str)
        except Exception as e_n8n_config:
            logger.error(f"Error al configurar/desplegar el workflow de N8N: {e_n8n_config}")
            return RedirectResponse(
                url=f"{redirect_url_base}&status=error&message=Error al configurar el workflow de N8N: {e_n8n_config}",
                status_code=302,
            )

        # 10. If new_n8n_chat_url is not obtained, redirect with an error
        if not new_n8n_chat_url:
            logger.error(f"No se pudo obtener la nueva URL del chat de N8N para el curso '{course_name_str}'.")
            return RedirectResponse(
                url=f"{redirect_url_base}&status=error&message=No se pudo obtener la nueva URL del chat de N8N.",
                status_code=302,
            )
        logger.info(f"Nueva URL de chat de N8N obtenida: {new_n8n_chat_url}")

        # 11. Re-construct the html_summary string for the Moodle section
        logger.info("Reconstruyendo HTML summary para la sección de Moodle...")
        
        # Links for Moodle section
        refresh_files_ui_url = f"{base_url}/ui/manage_files.html?course_id={course_id}"
        # The current endpoint itself is the refresh chat config URL
        refresh_chat_config_api_url = str(request.url_for("refresh_chat_config", course_id=course_id))

        # Ensure chat parameters used in summary are the ones applied
        # Limpiar comillas existentes para evitar acumulación infinita
        def clean_value(value):
            if not value or value == DEFAULT_UNSPECIFIED_TEXT:
                return DEFAULT_UNSPECIFIED_TEXT
            # Remover comillas dobles al inicio y final si existen
            cleaned = str(value).strip()
            if cleaned.startswith('"') and cleaned.endswith('"'):
                cleaned = cleaned[1:-1]
            # Remover múltiples comillas dobles consecutivas
            while '""' in cleaned:
                cleaned = cleaned.replace('""', '"')
            return cleaned
        
        applied_initial_messages = clean_value(chat_config.get("initial_messages", DEFAULT_UNSPECIFIED_TEXT))
        applied_system_message = clean_value(chat_config.get("system_message", DEFAULT_UNSPECIFIED_TEXT))
        applied_input_placeholder = clean_value(chat_config.get("input_placeholder", DEFAULT_UNSPECIFIED_TEXT))
        applied_chat_title = clean_value(chat_config.get("chat_title", DEFAULT_UNSPECIFIED_TEXT))

        # Edit instruction message
        edit_instruction_message = """
<p><strong>Nota para el profesor:</strong> Puede modificar las configuraciones del chat directamente en la sección "Configuración del Chat de IA" a continuación. Después de realizar cambios, use el enlace "Actualizar Configuraciones del Chat" para aplicar los cambios al sistema de IA.</p>
"""

        new_html_summary = f"""
<h4>Recursos de Entrenai IA</h4>
<p>Utilice esta sección para interactuar con la Inteligencia Artificial de asistencia para este curso.</p>
<ul>
    <li><a href="{str(new_n8n_chat_url).rstrip('/')}" target="_blank">{moodle_config.chat_link_name}</a>: Acceda aquí para chatear con la IA.</li>
    <li>Carpeta "<strong>Documentos Entrenai</strong>": Suba aquí los documentos PDF, DOCX, PPTX que la IA utilizará como base de conocimiento.</li>
    <li><a href="{refresh_files_ui_url}" target="_blank">{moodle_config.refresh_link_name}</a>: Haga clic aquí después de subir nuevos archivos o modificar existentes en la carpeta "Documentos Entrenai" para que la IA los procese.</li>
    <li><a href="{refresh_chat_config_api_url}" target="_blank">Actualizar Configuraciones del Chat</a>: Haga clic aquí después de modificar las configuraciones del chat (abajo) para aplicar los cambios.</li>
</ul>
{edit_instruction_message}
<h5>Configuración del Chat de IA (Aplicada):</h5>
<ul>
    <li><strong>Mensajes Iniciales:</strong> {applied_initial_messages}</li>
    <li><strong>Mensaje del Sistema:</strong> {applied_system_message}</li>
    <li><strong>Marcador de Posición de Entrada:</strong> {applied_input_placeholder}</li>
    <li><strong>Título del Chat:</strong> {applied_chat_title}</li>
</ul>
"""
        logger.debug(f"Nuevo HTML summary generado:\n{new_html_summary}")

        # 12. Update the Moodle course section's summary
        logger.info(f"Actualizando summary de la sección de Moodle ID {target_section_id}...")
        update_payload = {
            "courseid": course_id,
            "sections": [
                {
                    "type": "id", # type can be 'id' or 'sectionnumber'
                    "section": target_section_id,
                    "name": moodle_section_name_desired, # Keep the section name
                    "summary": new_html_summary,
                    "summaryformat": 1,  # 1 for HTML
                }
            ],
        }
        try:
            update_result = moodle._make_request("local_wsmanagesections_update_sections", update_payload)
            logger.info(f"Resultado de actualización de sección de Moodle: {update_result}")
            # Add more robust check for update_result if the API provides clear success/failure indicators
            if not update_result or (isinstance(update_result, list) and not update_result[0].get("success", True)): # success might not be present
                 logger.warning(f"La actualización de la sección de Moodle para el curso {course_id} podría no haber sido exitosa. Respuesta: {update_result}")
                 # Not necessarily a fatal error for the chat config refresh, but good to log.
        except MoodleAPIError as e_moodle_update:
            logger.error(f"Error de API de Moodle al actualizar la sección del curso {course_id}: {e_moodle_update}")
            # This is not ideal, as N8N is configured, but Moodle summary update failed.
            # For now, proceed to redirect with a partial success/warning message.
            return RedirectResponse(
                url=f"{redirect_url_base}&status=warning&message=Configuración del chat de IA en N8N actualizada, pero falló la actualización del resumen en Moodle: {e_moodle_update}",
                status_code=302,
            )

        # 13. Redirect to config_log.html with a success message
        logger.info(f"Configuración del chat para el curso {course_id} refrescada exitosamente.")
        return RedirectResponse(
            url=f"{redirect_url_base}&status=success&message=Configuración del chat de IA refrescada exitosamente. Nueva URL de chat desplegada.",
            status_code=302,
        )

    except HTTPException as http_exc: # Re-raise HTTPExceptions from helpers or specific checks
        logger.error(f"HTTPException durante el refresco de configuración de chat para el curso {course_id}: {http_exc.detail}")
        # Ensure detail is a string for the URL
        error_message = str(http_exc.detail) if http_exc.detail else "Error desconocido"
        return RedirectResponse(
            url=f"{redirect_url_base}&status=error&message={error_message}",
            status_code=302,
        )
    except Exception as e:
        logger.exception(f"Error inesperado durante el refresco de configuración de chat para el curso {course_id}: {e}")
        error_message = str(e) if str(e) else "Error interno del servidor"
        return RedirectResponse(
            url=f"{redirect_url_base}&status=error&message=Error interno del servidor: {error_message}",
            status_code=302,
        )
        