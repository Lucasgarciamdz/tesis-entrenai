from fastapi import APIRouter, HTTPException, Query, Depends, Request
from typing import List, Optional, Dict, Any
import shutil

from src.entrenai.api.models import (
    MoodleCourse,
    CourseSetupResponse,
    HttpUrl,  # Importar MoodleModule si se va a usar para parsear respuesta de módulos
)
from src.entrenai.core.clients.moodle_client import MoodleClient, MoodleAPIError
from src.entrenai.core.db import PgvectorWrapper, PgvectorWrapperError # Updated import
from src.entrenai.core.ai.ollama_wrapper import OllamaWrapper
from src.entrenai.core.ai.gemini_wrapper import GeminiWrapper
from src.entrenai.core.ai.ai_provider import get_ai_wrapper, AIProviderError
from src.entrenai.core.clients.n8n_client import N8NClient
# from src.entrenai.core.files.file_tracker import FileTracker # Removed
from src.entrenai.core.files.file_processor import FileProcessor, FileProcessingError
from src.entrenai.core.ai.embedding_manager import EmbeddingManager
from src.entrenai.config import (
    moodle_config,
    pgvector_config, # Updated import
    ollama_config,
    gemini_config,
    base_config,
    n8n_config,
)
from src.entrenai.config.logger import get_logger
from pathlib import Path

logger = get_logger(__name__)

router = APIRouter(
    prefix="/api/v1",
    tags=["Configuración de Curso y Gestión de IA"],
)


# --- Inyección de Dependencias para Clientes ---
def get_moodle_client() -> MoodleClient:
    return MoodleClient(config=moodle_config)


def get_pgvector_wrapper() -> PgvectorWrapper: # Renamed function and updated return type
    return PgvectorWrapper(config=pgvector_config) # Updated instantiation


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


def get_file_processor() -> FileProcessor:
    return FileProcessor()


def get_embedding_manager(
    ai_client=Depends(get_ai_client),
) -> EmbeddingManager:
    return EmbeddingManager(ollama_wrapper=ai_client)


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


@router.post("/courses/{course_id}/setup-ia", response_model=CourseSetupResponse)
async def setup_ia_for_course(
    course_id: int,
    request: Request,
    course_name_query: str = Query(
        None,
        alias="courseName",
        description="Nombre del curso para la IA (opcional, se intentará obtener de Moodle).",
    ),
    moodle: MoodleClient = Depends(get_moodle_client),
    pgvector_db: PgvectorWrapper = Depends(get_pgvector_wrapper), # Updated dependency
    ai_client=Depends(get_ai_client),
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

    vector_size = pgvector_config.default_vector_size # Updated config usage
    pgvector_table_name = pgvector_db.get_table_name(course_name_str) # Updated method call

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
        qdrant_collection_name=pgvector_table_name, # Renamed field for clarity, though model might not reflect this directly
    )

    try:
        logger.info(
            f"Asegurando tabla Pgvector '{pgvector_table_name}' para curso '{course_name_str}' con tamaño de vector {vector_size}"
        )
        # Removed qdrant.client check as PgvectorWrapper handles connection internally
        if not pgvector_db.ensure_table(course_name_str, vector_size): # Updated method call
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
            course_id, course_name_str, pgvector_table_name, ai_params # Updated variable
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
        refresh_path = router.url_path_for("refresh_files", course_id=course_id)
        refresh_files_url = str(request.base_url.replace(path=str(refresh_path)))
        n8n_chat_url_for_moodle = (
            str(response_details.n8n_chat_url) if response_details.n8n_chat_url else "#"
        )

        html_summary = f"""
<h4>Recursos de Entrenai IA</h4>
<p>Utilice esta sección para interactuar con la Inteligencia Artificial de asistencia para este curso.</p>
<ul>
    <li><a href="{n8n_chat_url_for_moodle}" target="_blank">{moodle_chat_link_name}</a>: Acceda aquí para chatear con la IA.</li>
    <li>Carpeta "<strong>{moodle_folder_name}</strong>": Suba aquí los documentos PDF, DOCX, PPTX que la IA utilizará como base de conocimiento.</li>
    <li><a href="{refresh_files_url}" target="_blank">{moodle_refresh_link_name}</a>: Haga clic aquí después de subir nuevos archivos o modificar existentes en la carpeta "{moodle_folder_name}" para que la IA los procese.</li>
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
    # file_tracker: FileTracker = Depends(get_file_tracker), # Removed
    pgvector_db: PgvectorWrapper = Depends(get_pgvector_wrapper), 
    ai_client: OllamaWrapper | GeminiWrapper = Depends(get_ai_client),
    embedding_manager: EmbeddingManager = Depends(get_embedding_manager),
    file_processor: FileProcessor = Depends(get_file_processor),
):
    """Refresca y procesa los archivos de un curso, actualizando la base de conocimiento de la IA."""
    logger.info(
        f"Iniciando proceso de refresco de archivos para el curso ID: {course_id}"
    )

    # Obtener nombre del curso para Pgvector
    course_name_for_pgvector: Optional[str] = None # Renamed variable
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
        if not course_name_for_pgvector:
            all_courses = moodle.get_all_courses()
            course = next((c for c in all_courses if c.id == course_id), None)
            if course:
                course_name_for_pgvector = course.displayname or course.fullname

        if not course_name_for_pgvector:
            course_name_for_pgvector = f"Curso_{course_id}"
            logger.warning(
                f"No se pudo obtener el nombre para el curso ID {course_id}, usando fallback: '{course_name_for_pgvector}' para Pgvector."
            )
        else:
            logger.info(f"Nombre del curso para Pgvector: '{course_name_for_pgvector}'")
    except Exception as e:
        logger.error(
            f"Error al obtener el nombre del curso {course_id} para Pgvector: {e}"
        )
        raise HTTPException(
            status_code=500,
            detail=f"No se pudo determinar el nombre del curso {course_id} para operaciones de Pgvector.",
        )

    if not course_name_for_pgvector:
        raise HTTPException(
            status_code=500,
            detail=f"Nombre del curso para Pgvector es inválido para el curso ID {course_id}.",
        )

    target_section_name = moodle_config.course_folder_name
    target_folder_name = "Documentos Entrenai"

    files_to_process_count = 0
    successfully_processed_count = 0
    total_chunks_upserted_count = 0
    processed_files_summary: List[Dict[str, Any]] = []
    course_download_dir = Path(base_config.download_dir) / str(course_id)

    try:
        # Asegurar que existe la tabla de Pgvector antes de procesar archivos
        vector_size = pgvector_config.default_vector_size # Updated config usage
        logger.info(
            f"Asegurando tabla Pgvector para curso {course_id} ('{course_name_for_pgvector}') con tamaño de vector {vector_size}"
        )
        if not pgvector_db.ensure_table(course_name_for_pgvector, vector_size): # Updated method call
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

        # Obtener todos los contenidos del curso para encontrar la sección y módulos
        all_course_contents = moodle._make_request(
            "core_course_get_contents", payload_params={"courseid": course_id}
        )
        if not isinstance(all_course_contents, list):
            raise HTTPException(
                status_code=500,
                detail="No se pudieron obtener los contenidos del curso.",
            )

        # Buscar la sección objetivo por nombre
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

        # Encontrar el módulo de carpeta en la sección
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

        # Obtener los archivos de la carpeta
        moodle_files = moodle.get_folder_files(folder_cmid=folder_cmid)
        if not moodle_files:
            logger.info(
                f"No se encontraron archivos en la carpeta '{target_folder_name}' (cmid: {folder_cmid})."
            )
            return {
                "message": "No se encontraron archivos en la carpeta designada de Moodle.",
                "files_checked": 0,
                "files_processed": 0,
                "total_chunks_upserted": 0,
            }

        logger.info(
            f"Se encontraron {len(moodle_files)} archivos en la carpeta de Moodle. Verificando archivos nuevos/modificados..."
        )
        course_download_dir.mkdir(parents=True, exist_ok=True)

        for mf in moodle_files:
            file_summary: Dict[str, Any] = {
                "filename": mf.filename,
                "status": "omitido_sin_cambios",
            }
            downloaded_path: Optional[Path] = None
            try:
                if not mf.filename or not mf.fileurl or mf.timemodified is None:
                    logger.warning(
                        f"Omitiendo archivo de Moodle con datos incompletos: {mf.model_dump_json()}"
                    )
                    file_summary["status"] = "omitido_datos_incompletos"
                    processed_files_summary.append(file_summary)
                    continue

                if pgvector_db.is_file_new_or_modified( # Changed from file_tracker to pgvector_db
                    course_id, mf.filename, mf.timemodified
                ):
                    files_to_process_count += 1
                    logger.info(
                        f"Archivo '{mf.filename}' es nuevo o modificado. Procesando..."
                    )

                    downloaded_path = moodle.download_file(
                        str(mf.fileurl), course_download_dir, mf.filename
                    )
                    logger.info(
                        f"Descargado exitosamente: {mf.filename} a {downloaded_path}"
                    )

                    raw_text = file_processor.process_file(downloaded_path)
                    if not raw_text:
                        logger.error(f"Extracción de texto falló para {mf.filename}.")
                        file_summary["status"] = "extraccion_texto_fallida"
                        raise FileProcessingError(
                            f"Extracción de texto falló para {mf.filename}"
                        )

                    markdown_text = ai_client.format_to_markdown(
                        raw_text, save_path=str(Path(base_config.data_dir) / "markdown")
                    )
                    logger.info(
                        f"Formateado a Markdown para {mf.filename} (longitud: {len(markdown_text)})"
                    )

                    text_chunks = embedding_manager.split_text_into_chunks(
                        markdown_text
                    )
                    if not text_chunks:
                        logger.warning(f"No se generaron chunks para {mf.filename}.")
                        file_summary["status"] = "no_se_generaron_chunks"
                        raise FileProcessingError(
                            f"No se generaron chunks para {mf.filename}"
                        )

                    contextualized_chunks = [
                        embedding_manager.contextualize_chunk(
                            c, mf.filename, mf.filename
                        )
                        for c in text_chunks
                    ]
                    embeddings_list = embedding_manager.generate_embeddings_for_chunks(
                        contextualized_chunks
                    )

                    valid_data = [
                        (ctx_c, emb)
                        for ctx_c, emb in zip(contextualized_chunks, embeddings_list)
                        if emb
                    ]
                    if not valid_data:
                        logger.warning(f"No hay embeddings válidos para {mf.filename}.")
                        file_summary["status"] = "generacion_embedding_fallida"
                        raise FileProcessingError(
                            f"No hay embeddings válidos para {mf.filename}"
                        )

                    final_texts, final_embeddings = zip(*valid_data)
                    db_chunks = ( # Renamed variable
                        embedding_manager.prepare_document_chunks_for_vector_db( # Updated method call
                            course_id, # Keep course_id here as per EmbeddingManager's current signature
                            mf.filename,
                            mf.filename,
                            mf.filename,
                            list(final_texts),
                            list(final_embeddings),
                        )
                    )

                    if db_chunks:
                        # Usar course_name_for_pgvector en lugar de course_id para la interacción con Pgvector
                        if pgvector_db.upsert_chunks(course_name_for_pgvector, db_chunks): # Updated method call
                            logger.info(
                                f"Insertados/actualizados {len(db_chunks)} chunks para {mf.filename} en Pgvector."
                            )
                            total_chunks_upserted_count += len(db_chunks)
                            file_summary["chunks_upserted"] = len(db_chunks)
                        else:
                            logger.error(
                                f"Falló el upsert a Pgvector para {mf.filename}."
                            )
                            file_summary["status"] = "pgvector_upsert_fallido"
                            raise FileProcessingError(
                                f"Falló el upsert a Pgvector para {mf.filename}"
                            )

                    pgvector_db.mark_file_as_processed( # Changed from file_tracker to pgvector_db
                        course_id, mf.filename, mf.timemodified
                    )
                    successfully_processed_count += 1
                    file_summary["status"] = "procesado_exitosamente"
            except (MoodleAPIError, FileProcessingError, Exception) as e:
                logger.error(f"Error procesando archivo '{mf.filename}': {e}")
                if (
                    "status" not in file_summary
                    or file_summary["status"] == "omitido_sin_cambios"
                ):
                    file_summary["status"] = f"error: {str(e)}"
            # finally:
            #     if downloaded_path and downloaded_path.exists():
            #         try:
            #             downloaded_path.unlink()
            #             logger.debug(f"Archivo temporal eliminado: {downloaded_path}")
            #         except OSError as e_unlink:
            #             logger.error(f"Error eliminando archivo temporal {downloaded_path}: {e_unlink}")
            processed_files_summary.append(file_summary)

        try:
            if course_download_dir.exists() and not any(course_download_dir.iterdir()):
                shutil.rmtree(course_download_dir)
                logger.info(
                    f"Directorio de descargas del curso vacío eliminado: {course_download_dir}"
                )
        except Exception as e_rm:
            logger.warning(
                f"No se pudo eliminar el directorio de descargas del curso {course_download_dir}: {e_rm}"
            )

        msg = (
            f"Refresco de archivos completado para el curso {course_id}. "
            f"Archivos verificados: {len(moodle_files)}. "
            f"Se intentaron procesar {files_to_process_count} archivos nuevos/modificados. "
            f"Procesados exitosamente e incrustados: {successfully_processed_count} archivos. "
            f"Total de chunks insertados/actualizados: {total_chunks_upserted_count}."
        )
        logger.info(msg)
        return {
            "message": msg,
            "files_checked": len(moodle_files),
            "files_to_process": files_to_process_count,
            "files_processed_successfully": successfully_processed_count,
            "total_chunks_upserted": total_chunks_upserted_count,
            "processed_files_details": processed_files_summary,
        }

    except HTTPException as http_exc:
        logger.error(
            f"HTTPException durante refresco de archivos para curso {course_id}: {http_exc.detail}"
        )
        raise http_exc
    except MoodleAPIError as e:
        logger.error(
            f"Error de API de Moodle durante refresco de archivos para curso {course_id}: {e}"
        )
        raise HTTPException(status_code=502, detail=f"Error de API de Moodle: {str(e)}")
    except Exception as e:
        logger.exception(
            f"Error inesperado durante refresco de archivos para curso {course_id}: {e}"
        )
        raise HTTPException(
            status_code=500, detail=f"Error interno del servidor: {str(e)}"
        )
