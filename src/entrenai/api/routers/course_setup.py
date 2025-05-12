from fastapi import APIRouter, HTTPException, Query, Depends, Request
from typing import List, Optional, Dict, Any  # Added Dict, Any

from src.entrenai.core.models import (
    MoodleCourse,
    CourseSetupResponse,
    HttpUrl,
)
from src.entrenai.core.moodle_client import MoodleClient, MoodleAPIError
from src.entrenai.core.qdrant_wrapper import QdrantWrapper
from src.entrenai.core.ollama_wrapper import OllamaWrapper
from src.entrenai.core.n8n_client import N8NClient
from src.entrenai.core.file_tracker import FileTracker
from src.entrenai.core.file_processor import FileProcessor, FileProcessingError
from src.entrenai.core.embedding_manager import EmbeddingManager
from src.entrenai.config import (
    moodle_config,
    qdrant_config,
    ollama_config,
    n8n_config,
    base_config,
)
from src.entrenai.utils.logger import get_logger
from pathlib import Path

logger = get_logger(__name__)

router = APIRouter(
    prefix="/api/v1",
    tags=["Course Setup & IA Management"],
)


# --- Dependency Injection for Clients ---
def get_moodle_client() -> MoodleClient:
    return MoodleClient(config=moodle_config)


def get_qdrant_wrapper() -> QdrantWrapper:
    return QdrantWrapper(config=qdrant_config)


def get_ollama_wrapper() -> OllamaWrapper:
    return OllamaWrapper(config=ollama_config)


def get_n8n_client() -> N8NClient:
    return N8NClient(config=n8n_config)


def get_file_tracker() -> FileTracker:
    return FileTracker(db_path=Path(base_config.file_tracker_db_path))


def get_file_processor() -> FileProcessor:
    return FileProcessor()


def get_embedding_manager(
    ollama: OllamaWrapper = Depends(get_ollama_wrapper),
) -> EmbeddingManager:
    return EmbeddingManager(ollama_wrapper=ollama)


@router.get("/courses", response_model=List[MoodleCourse])
async def list_moodle_courses(
    moodle_user_id: Optional[int] = Query(
        None,
        description="Moodle User ID of the teacher. If not provided, uses MOODLE_DEFAULT_TEACHER_ID from config.",
    ),
    client: MoodleClient = Depends(get_moodle_client),
):
    teacher_id_to_use = (
        moodle_user_id
        if moodle_user_id is not None
        else moodle_config.default_teacher_id
    )
    if teacher_id_to_use is None:
        logger.error(
            "No Moodle teacher ID provided and MOODLE_DEFAULT_TEACHER_ID is not set."
        )
        raise HTTPException(
            status_code=400,
            detail="Moodle teacher ID must be provided or MOODLE_DEFAULT_TEACHER_ID must be configured on the server.",
        )
    logger.info(f"Fetching Moodle courses for teacher ID: {teacher_id_to_use}")
    try:
        courses = client.get_courses_by_user(user_id=teacher_id_to_use)
        # courses = client.get_all_courses()
        return courses
    except MoodleAPIError as e:
        logger.error(f"Moodle API error while fetching courses: {e}")
        raise HTTPException(status_code=502, detail=f"Moodle API error: {str(e)}")
    except Exception as e:
        logger.exception(f"Unexpected error fetching Moodle courses: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("/courses/{course_id}/setup-ia", response_model=CourseSetupResponse)
async def setup_ia_for_course(
    course_id: int,
    request: Request,
    moodle: MoodleClient = Depends(get_moodle_client),
    qdrant: QdrantWrapper = Depends(get_qdrant_wrapper),
    n8n: N8NClient = Depends(get_n8n_client),
):
    logger.info(f"Starting IA setup for Moodle course ID: {course_id}")
    vector_size = qdrant_config.default_vector_size
    moodle_section_name = moodle_config.course_folder_name
    moodle_folder_name = "Documentos Entrenai"
    moodle_chat_link_name = moodle_config.chat_link_name
    moodle_refresh_link_name = moodle_config.refresh_link_name

    response_details = CourseSetupResponse(
        course_id=course_id,
        status="pending",
        message=f"Setup initiated for course {course_id}.",
        qdrant_collection_name=qdrant.get_collection_name(course_id),
    )

    try:
        logger.info(
            f"Ensuring Qdrant collection for course {course_id} with vector size {vector_size}"
        )
        if not qdrant.client:
            raise HTTPException(status_code=500, detail="Qdrant client not available.")
        if not qdrant.ensure_collection(course_id, vector_size):
            response_details.status = "failed"
            response_details.message = (
                f"Failed to ensure Qdrant collection for course {course_id}."
            )
            logger.error(response_details.message)
            raise HTTPException(status_code=500, detail=response_details.message)
        logger.info(
            f"Qdrant collection '{response_details.qdrant_collection_name}' ensured."
        )

        logger.info(f"Configuring N8N chat workflow for course {course_id}")
        ollama_params_for_n8n = {
            "host": ollama_config.host,
            "embedding_model": ollama_config.embedding_model,
            "qa_model": ollama_config.qa_model,
        }
        n8n_chat_url_str = n8n.configure_and_deploy_chat_workflow(
            course_id=course_id,
            qdrant_collection_name=response_details.qdrant_collection_name,
            ollama_config_params=ollama_params_for_n8n, # Corrected parameter name
        )
        if not n8n_chat_url_str:
            logger.warning(
                f"Could not automatically configure/retrieve N8N chat URL for course {course_id}."
            )
            response_details.message += " N8N chat URL not automatically configured."
            n8n_chat_url_str = n8n_config.webhook_url
            if not n8n_chat_url_str:
                logger.error("N8N_WEBHOOK_URL is also not set.")
        response_details.n8n_chat_url = (
            HttpUrl(n8n_chat_url_str) if n8n_chat_url_str else None
        )  # type: ignore
        logger.info(
            f"N8N chat URL for course {course_id}: {response_details.n8n_chat_url}"
        )

        logger.info(
            f"Creating Moodle section '{moodle_section_name}' for course {course_id}"
        )
        created_section = moodle.create_course_section(
            course_id, moodle_section_name, position=1
        )
        if not created_section or not created_section.id:
            response_details.status = "failed"
            response_details.message = f"Failed to create Moodle section '{moodle_section_name}' for course {course_id}."
            logger.error(response_details.message)
            raise HTTPException(status_code=500, detail=response_details.message)
        response_details.moodle_section_id = created_section.id
        logger.info(
            f"Moodle section '{created_section.name}' (ID: {created_section.id}) created."
        )

        logger.info(
            f"Creating Moodle folder '{moodle_folder_name}' in section {created_section.id}"
        )
        created_folder_module = moodle.create_folder_in_section(
            course_id, created_section.id, moodle_folder_name
        )
        if not created_folder_module or not created_folder_module.id:
            logger.warning(
                f"Failed to create Moodle folder '{moodle_folder_name}' in section {created_section.id}. Proceeding."
            )
            response_details.message += (
                f" Warning: Failed to create Moodle folder '{moodle_folder_name}'."
            )
        else:
            response_details.moodle_folder_id = created_folder_module.id
            logger.info(
                f"Moodle folder '{created_folder_module.name}' (Module ID: {created_folder_module.id}) created."
            )

        if response_details.n8n_chat_url:
            logger.info(
                f"Creating Moodle link for N8N Chat ('{moodle_chat_link_name}') in section {created_section.id}"
            )
            chat_link_module = moodle.create_url_in_section(
                course_id,
                created_section.id,
                moodle_chat_link_name,
                str(response_details.n8n_chat_url),
            )
            if not chat_link_module or not chat_link_module.id:
                logger.warning(
                    f"Failed to create Moodle link for N8N Chat in section {created_section.id}. Proceeding."
                )
                response_details.message += (
                    " Warning: Failed to create Moodle link for N8N Chat."
                )
            else:
                response_details.moodle_chat_link_id = chat_link_module.id
                logger.info(
                    f"Moodle link for N8N Chat (Module ID: {chat_link_module.id}) created."
                )
        else:
            logger.warning(
                "No N8N chat URL available, skipping Moodle link creation for chat."
            )
            response_details.message += (
                " N8N chat URL not available, Moodle link for chat not created."
            )

        refresh_path = router.url_path_for(
            "refresh_files", course_id=course_id
        )  # Changed name
        refresh_files_url = str(request.base_url.replace(path=str(refresh_path)))
        logger.info(
            f"Creating Moodle link for Refresh Files ('{moodle_refresh_link_name}') -> {refresh_files_url} in section {created_section.id}"
        )
        refresh_link_module = moodle.create_url_in_section(
            course_id, created_section.id, moodle_refresh_link_name, refresh_files_url
        )
        if not refresh_link_module or not refresh_link_module.id:
            logger.warning(
                f"Failed to create Moodle link for Refresh Files in section {created_section.id}. Proceeding."
            )
            response_details.message += (
                " Warning: Failed to create Moodle link for Refresh Files."
            )
        else:
            response_details.moodle_refresh_link_id = refresh_link_module.id
            logger.info(
                f"Moodle link for Refresh Files (Module ID: {refresh_link_module.id}) created."
            )

        response_details.status = "success"
        response_details.message = (
            f"Entrenai IA setup completed successfully for course {course_id}."
        )
        logger.info(response_details.message)
        return response_details
    except HTTPException as http_exc:
        raise http_exc
    except MoodleAPIError as e:
        logger.error(f"Moodle API error during IA setup for course {course_id}: {e}")
        response_details.status = "failed"
        response_details.message = f"Moodle API error: {str(e)}"
        raise HTTPException(status_code=502, detail=response_details.message)
    except Exception as e:
        logger.exception(
            f"Unexpected error during IA setup for course {course_id}: {e}"
        )
        response_details.status = "failed"
        response_details.message = f"Internal server error: {str(e)}"
        raise HTTPException(status_code=500, detail=response_details.message)


@router.get("/courses/{course_id}/refresh-files", name="refresh_files")
async def refresh_course_files(
    course_id: int,
    moodle: MoodleClient = Depends(get_moodle_client),
    file_tracker: FileTracker = Depends(get_file_tracker),
    qdrant: QdrantWrapper = Depends(get_qdrant_wrapper),
    ollama: OllamaWrapper = Depends(get_ollama_wrapper),
    embedding_manager: EmbeddingManager = Depends(get_embedding_manager),
    file_processor: FileProcessor = Depends(get_file_processor),
):
    logger.info(f"Starting file refresh process for course ID: {course_id}")
    target_section_name = moodle_config.course_folder_name
    target_folder_name = "Documentos Entrenai"

    processed_files_summary: List[Dict[str, Any]] = []
    files_to_process_count = 0
    successfully_processed_count = 0
    total_chunks_upserted_count = 0
    processed_files_summary: List[
        Dict[str, Any]
    ] = []  # Ensure type allows mixed values

    try:
        all_course_contents = moodle._make_request(
            "core_course_get_contents", payload_params={"courseid": course_id}
        )
        if not isinstance(all_course_contents, list):
            raise HTTPException(
                status_code=500, detail="Could not retrieve course contents."
            )

        found_section_id: Optional[int] = None
        for section_data in all_course_contents:
            if section_data.get("name") == target_section_name:
                found_section_id = section_data.get("id")
                break

        if not found_section_id:
            logger.error(
                f"Target section '{target_section_name}' not found in course {course_id}."
            )
            raise HTTPException(
                status_code=404,
                detail=f"Setup section '{target_section_name}' not found.",
            )
        logger.info(
            f"Found section '{target_section_name}' with ID: {found_section_id}."
        )

        folder_module = moodle.get_course_module_by_name(
            course_id, found_section_id, target_folder_name, "folder"
        )
        if not folder_module or not folder_module.id:
            logger.error(
                f"Folder '{target_folder_name}' not found in course {course_id}, section {found_section_id}."
            )
            raise HTTPException(
                status_code=404,
                detail=f"Designated Moodle folder '{target_folder_name}' not found.",
            )

        folder_cmid = folder_module.id
        logger.info(f"Found folder '{target_folder_name}' with cmid: {folder_cmid}.")

        moodle_files = moodle.get_folder_files(folder_cmid=folder_cmid)
        if not moodle_files:
            logger.info(
                f"No files found in folder '{target_folder_name}' (cmid: {folder_cmid})."
            )
            return {
                "message": "No files found in the designated Moodle folder.",
                "files_checked": 0,
                "files_processed": 0,
                "total_chunks_upserted": 0,
            }

        logger.info(
            f"Found {len(moodle_files)} files in Moodle folder. Checking for new/modified files..."
        )

        course_download_dir = Path(base_config.download_dir) / str(course_id)
        course_download_dir.mkdir(parents=True, exist_ok=True)

        for mf in moodle_files:
            file_summary: Dict[str, Any] = {
                "filename": mf.filename,
                "status": "skipped_unchanged",
            }  # Explicitly type file_summary
            if not mf.filename or not mf.fileurl or mf.timemodified is None:
                logger.warning(
                    f"Skipping Moodle file with incomplete data: {mf.model_dump_json()}"
                )
                file_summary["status"] = "skipped_incomplete_data"
                processed_files_summary.append(file_summary)
                continue

            if file_tracker.is_file_new_or_modified(
                course_id, mf.filename, mf.timemodified
            ):
                files_to_process_count += 1
                logger.info(f"File '{mf.filename}' is new or modified. Processing...")
                downloaded_path: Optional[Path] = None
                try:
                    downloaded_path = moodle.download_file(
                        str(mf.fileurl), course_download_dir, mf.filename
                    )
                    logger.info(
                        f"Successfully downloaded: {mf.filename} to {downloaded_path}"
                    )

                    raw_text = file_processor.process_file(downloaded_path)
                    if not raw_text:
                        logger.error(f"Text extraction failed for {mf.filename}.")
                        file_summary["status"] = "text_extraction_failed"
                        raise FileProcessingError(
                            f"Text extraction failed for {mf.filename}"
                        )

                    markdown_text = ollama.format_to_markdown(raw_text)
                    logger.info(
                        f"Formatted to Markdown for {mf.filename} (length: {len(markdown_text)})"
                    )

                    text_chunks = embedding_manager.split_text_into_chunks(
                        markdown_text
                    )
                    if not text_chunks:
                        logger.warning(f"No chunks generated for {mf.filename}.")
                        file_summary["status"] = "no_chunks_generated"
                        raise FileProcessingError(
                            f"No chunks generated for {mf.filename}"
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
                        logger.warning(f"No valid embeddings for {mf.filename}.")
                        file_summary["status"] = "embedding_generation_failed"
                        raise FileProcessingError(
                            f"No valid embeddings for {mf.filename}"
                        )

                    final_texts, final_embeddings = zip(*valid_data)
                    qdrant_chunks = (
                        embedding_manager.prepare_document_chunks_for_qdrant(
                            course_id,
                            mf.filename,
                            mf.filename,
                            mf.filename,
                            list(final_texts),
                            list(final_embeddings),
                        )
                    )

                    if qdrant_chunks:
                        if qdrant.upsert_chunks(course_id, qdrant_chunks):
                            logger.info(
                                f"Upserted {len(qdrant_chunks)} chunks for {mf.filename}."
                            )
                            total_chunks_upserted_count += len(qdrant_chunks)
                            file_summary["chunks_upserted"] = len(qdrant_chunks)
                        else:
                            logger.error(f"Qdrant upsert failed for {mf.filename}.")
                            file_summary["status"] = "qdrant_upsert_failed"
                            raise FileProcessingError(
                                f"Qdrant upsert failed for {mf.filename}"
                            )

                    file_tracker.mark_file_as_processed(
                        course_id, mf.filename, mf.timemodified
                    )
                    successfully_processed_count += 1
                    file_summary["status"] = "processed_successfully"
                except (MoodleAPIError, FileProcessingError, Exception) as e:
                    logger.error(f"Error processing file '{mf.filename}': {e}")
                    if (
                        "status" not in file_summary
                        or file_summary["status"] == "skipped_unchanged"
                    ):  # if not already set by a more specific error
                        file_summary["status"] = f"error: {str(e)}"
                finally:
                    if downloaded_path and downloaded_path.exists():
                        try:
                            downloaded_path.unlink()
                        except OSError as e_unlink:
                            logger.error(
                                f"Error deleting temp file {downloaded_path}: {e_unlink}"
                            )
            processed_files_summary.append(file_summary)

        msg = (
            f"File refresh completed for course {course_id}. Checked {len(moodle_files)} files. "
            f"Attempted to process {files_to_process_count} new/modified files. "
            f"Successfully processed and embedded {successfully_processed_count} files. "
            f"Total chunks upserted: {total_chunks_upserted_count}."
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
        raise http_exc
    except MoodleAPIError as e:
        logger.error(
            f"Moodle API error during file refresh for course {course_id}: {e}"
        )
        raise HTTPException(status_code=502, detail=f"Moodle API error: {str(e)}")
    except Exception as e:
        logger.exception(
            f"Unexpected error during file refresh for course {course_id}: {e}"
        )
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")
