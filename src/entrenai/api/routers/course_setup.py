from fastapi import APIRouter, HTTPException, Query, Depends, Request
from typing import List, Optional

from src.entrenai.core.models import (
    MoodleCourse,
    CourseSetupResponse,
    HttpUrl,
)  # Add more models as needed
from src.entrenai.core.moodle_client import MoodleClient, MoodleAPIError
from src.entrenai.core.qdrant_wrapper import QdrantWrapper
from src.entrenai.core.ollama_wrapper import OllamaWrapper
from src.entrenai.core.n8n_client import N8NClient
from src.entrenai.core.file_tracker import FileTracker  # Moved import to top
from src.entrenai.config import (
    moodle_config,
    qdrant_config,
    ollama_config,
    n8n_config,
    base_config,
)  # Added base_config
from src.entrenai.utils.logger import get_logger
from pathlib import Path  # Added Path import

logger = get_logger(__name__)

router = APIRouter(
    prefix="/api/v1",  # Prefix for all routes in this router
    tags=["Course Setup & IA Management"],  # Tag for OpenAPI docs
)

# --- Dependency Injection for Clients (optional but good practice) ---
# This allows for easier testing by mocking dependencies.
# For simplicity now, we can instantiate them directly in the route if preferred.


def get_moodle_client() -> MoodleClient:
    # In a real app, you might get a session or other dependencies here
    return MoodleClient(config=moodle_config)


def get_qdrant_wrapper() -> QdrantWrapper:
    return QdrantWrapper(config=qdrant_config)


def get_ollama_wrapper() -> OllamaWrapper:
    return OllamaWrapper(config=ollama_config)


def get_n8n_client() -> N8NClient:
    return N8NClient(config=n8n_config)


def get_file_tracker() -> FileTracker:
    # base_config.file_tracker_db_path is already a string path
    # FileTracker constructor handles converting it to Path if needed.
    return FileTracker(db_path=Path(base_config.file_tracker_db_path))


@router.get("/courses", response_model=List[MoodleCourse])
async def list_moodle_courses(
    moodle_user_id: Optional[int] = Query(
        None,
        description="Moodle User ID of the teacher. If not provided, uses MOODLE_DEFAULT_TEACHER_ID from config.",
    ),
    client: MoodleClient = Depends(get_moodle_client),
):
    """
    Lists Moodle courses for a given teacher ID.
    If moodle_user_id is not provided, it attempts to use the
    MOODLE_DEFAULT_TEACHER_ID from the server configuration.
    """
    teacher_id_to_use = moodle_user_id or moodle_config.default_teacher_id

    if not teacher_id_to_use:
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
        if not courses:
            logger.info(f"No courses found for teacher ID: {teacher_id_to_use}")
            # Return empty list, not an error, if API call was successful but no courses
        return courses
    except MoodleAPIError as e:
        logger.error(f"Moodle API error while fetching courses: {e}")
        raise HTTPException(
            status_code=502, detail=f"Moodle API error: {e}"
        )  # 502 Bad Gateway
    except Exception as e:
        logger.exception(f"Unexpected error fetching Moodle courses: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {e}")


# Placeholder for POST /courses/{course_id}/setup-ia
@router.post("/courses/{course_id}/setup-ia", response_model=CourseSetupResponse)
async def setup_ia_for_course(
    course_id: int,
    request: Request,  # Corrected: Injected Request object
    moodle: MoodleClient = Depends(get_moodle_client),
    qdrant: QdrantWrapper = Depends(get_qdrant_wrapper),
    n8n: N8NClient = Depends(get_n8n_client),
    # ollama: OllamaWrapper = Depends(get_ollama_wrapper) # Not directly used in this endpoint yet
):
    """
    Sets up the Entrenai IA for a specific Moodle course. This involves:
    1. Ensuring a Qdrant collection for the course.
    2. Configuring/getting the N8N chat workflow URL.
    3. Creating a dedicated section in the Moodle course.
    4. Creating a folder for documents within that Moodle section.
    5. Adding a link to the N8N chat in the Moodle section.
    6. Adding a link to the 'Refresh Files' API endpoint in the Moodle section.
    """
    logger.info(f"Starting IA setup for Moodle course ID: {course_id}")

    # Default values from config or constants
    vector_size = qdrant_config.default_vector_size

    moodle_section_name = (
        moodle_config.course_folder_name
    )  # e.g., "Entrenai IA Resources"
    moodle_folder_name = "Documentos Entrenai"  # Name of the sub-folder for documents
    moodle_chat_link_name = moodle_config.chat_link_name
    moodle_refresh_link_name = moodle_config.refresh_link_name

    response_details = CourseSetupResponse(
        course_id=course_id,
        status="pending",
        message=f"Setup initiated for course {course_id}.",
        qdrant_collection_name=qdrant.get_collection_name(
            course_id
        ),  # Store expected name
    )

    try:
        # 1. Ensure Qdrant collection
        logger.info(
            f"Ensuring Qdrant collection for course {course_id} with vector size {vector_size}"
        )
        if not qdrant.client:  # Check if qdrant client initialized properly
            raise HTTPException(status_code=500, detail="Qdrant client not available.")
        collection_exists = qdrant.ensure_collection(course_id, vector_size)
        if not collection_exists:
            response_details.status = "failed"
            response_details.message = (
                f"Failed to ensure Qdrant collection for course {course_id}."
            )
            logger.error(response_details.message)
            raise HTTPException(status_code=500, detail=response_details.message)
        logger.info(
            f"Qdrant collection '{response_details.qdrant_collection_name}' ensured."
        )

        # 2. Configure N8N chat workflow and get URL
        logger.info(f"Configuring N8N chat workflow for course {course_id}")
        # Pass relevant ollama config if n8n client needs it for parameterizing the workflow
        ollama_params_for_n8n = {
            "host": ollama_config.host,
            "embedding_model": ollama_config.embedding_model,
            "qa_model": ollama_config.qa_model,
        }
        n8n_chat_url = n8n.configure_and_deploy_chat_workflow(
            course_id=course_id,
            qdrant_collection_name=response_details.qdrant_collection_name,
            ollama_config=ollama_params_for_n8n,
        )
        if not n8n_chat_url:
            # This might not be a fatal error if a default/manual N8N URL is acceptable
            logger.warning(
                f"Could not automatically configure/retrieve N8N chat URL for course {course_id}. Manual setup might be needed."
            )
            response_details.message += " N8N chat URL not automatically configured."
            # For now, let's allow proceeding if a default URL is in config.N8N_WEBHOOK_URL
            n8n_chat_url = (
                n8n_config.webhook_url
            )  # Fallback to general webhook URL if specific one not found
            if not n8n_chat_url:
                logger.error(
                    "N8N_WEBHOOK_URL is also not set. Cannot create Moodle link for chat."
                )
                # Decide if this is fatal
        response_details.n8n_chat_url = HttpUrl(n8n_chat_url) if n8n_chat_url else None
        logger.info(
            f"N8N chat URL for course {course_id}: {response_details.n8n_chat_url}"
        )

        # 3. Create Moodle Section
        logger.info(
            f"Creating Moodle section '{moodle_section_name}' for course {course_id}"
        )
        created_section = moodle.create_course_section(
            course_id, moodle_section_name, position=1
        )  # Position 1 after general
        if not created_section or not created_section.id:
            response_details.status = "failed"
            response_details.message = f"Failed to create Moodle section '{moodle_section_name}' for course {course_id}."
            logger.error(response_details.message)
            raise HTTPException(status_code=500, detail=response_details.message)
        response_details.moodle_section_id = created_section.id
        logger.info(
            f"Moodle section '{created_section.name}' (ID: {created_section.id}) created."
        )

        # 4. Create Folder in Moodle Section
        logger.info(
            f"Creating Moodle folder '{moodle_folder_name}' in section {created_section.id}"
        )
        created_folder_module = moodle.create_folder_in_section(
            course_id, created_section.id, moodle_folder_name
        )
        if not created_folder_module or not created_folder_module.id:
            # Non-fatal, log warning, IA can still work if folder creation fails but section exists
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

        # 5. Create N8N Chat Link in Moodle Section
        if n8n_chat_url:  # Only create link if we have a URL
            logger.info(
                f"Creating Moodle link for N8N Chat ('{moodle_chat_link_name}') in section {created_section.id}"
            )
            chat_link_module = moodle.create_url_in_section(
                course_id, created_section.id, moodle_chat_link_name, n8n_chat_url
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

        # 6. Create "Refresh Files" Link in Moodle Section
        # Construct the refresh URL based on the current request's base URL
        # Need to import 'Request' from fastapi and add as a dependency to the route: `request: Request`
        # For now, let's assume base_config.fastapi_host and port are correct for external access.
        # This might need adjustment if behind a reverse proxy.
        # A better way is to use request.url_for(...) but that requires naming the route.

        # Corrected: Need to get Request object from FastAPI for base_url
        # The `request: Depends` in the function signature is incorrect. It should be `request: Request`
        # from fastapi import Request. I will fix this in the next iteration if it causes an error.
        # For now, I'll construct it manually, which is less robust.

        # This is a placeholder, as constructing the URL correctly without the Request object is tricky.
        # The actual URL should be resolvable by the Moodle server and point to our FastAPI.
        # Example: http://<your_fastapi_service_host_or_domain>:<port>/api/v1/courses/{course_id}/refresh-files
        # We'll use a placeholder and log a warning.
        # refresh_files_endpoint_url = f"http://{base_config.fastapi_host}:{base_config.fastapi_port}/api/v1/courses/{course_id}/refresh-files"
        # A more robust way if running locally and Moodle is in Docker: http://host.docker.internal:{base_config.fastapi_port}/...
        # For now, let's assume the user will configure MOODLE_URL for FastAPI access from Moodle's perspective
        # or we use a relative path if Moodle and FastAPI are on the same domain.
        # This needs careful consideration for deployment.
        # For now, let's use a placeholder that needs to be configured.

        # A better approach for now is to make it configurable or a known relative path if possible.
        # Let's assume the FastAPI app is accessible from Moodle at a certain base URL.
        # This is a simplification and might need to be made more robust.
        # The `request` object from FastAPI is needed to build this URL correctly relative to the server.

        # Construct refresh_files_url using request.url_for if the route is named,
        # or by combining request.base_url with the path.
        # For now, let's build it from base_url and path.
        # Ensure the refresh-files endpoint will be named 'refresh_course_files' or similar.
        # A simple way:
        refresh_path = router.url_path_for(
            "refresh_course_files_placeholder", course_id=course_id
        )
        refresh_files_url = str(request.base_url.replace(path=str(refresh_path)))
        # Note: The 'refresh_course_files_placeholder' route needs to be defined, even if just as a placeholder for url_path_for to work.

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
        # Re-raise HTTPExceptions directly
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


# Placeholder for GET /api/v1/courses/{course_id}/refresh-files
# This endpoint will be implemented in a later phase.
@router.get(
    "/courses/{course_id}/refresh-files", name="refresh_course_files_placeholder"
)
async def refresh_course_files_placeholder(course_id: int):
    logger.info(
        f"Placeholder: Received request to refresh files for course {course_id}"
    )
    # Actual logic will be implemented in Phase 3
    return {"message": f"File refresh process placeholder for course {course_id}."}


@router.get(
    "/courses/{course_id}/refresh-files", name="refresh_files"
)  # Renamed from placeholder
async def refresh_course_files(
    course_id: int,
    moodle: MoodleClient = Depends(get_moodle_client),
    file_tracker: FileTracker = Depends(get_file_tracker),  # Corrected dependency
    # qdrant: QdrantWrapper = Depends(get_qdrant_wrapper), # For later processing steps
    # ollama: OllamaWrapper = Depends(get_ollama_wrapper), # For later processing steps
):
    """
    Refreshes files for a given course:
    1. Finds the designated Moodle folder for the course.
    2. Lists files in that folder.
    3. Compares with FileTracker to find new/modified files.
    4. Downloads these files.
    (Future steps: process files, generate embeddings, upsert to Qdrant).
    """
    logger.info(f"Starting file refresh process for course ID: {course_id}")

    # base_config is now imported at the top and available
    # FileTracker instance is injected via Depends(get_file_tracker)

    # --- Locate Moodle Section and Folder ---
    target_section_name = moodle_config.course_folder_name
    target_folder_name = "Documentos Entrenai"  # As defined in setup_ia_for_course

    course_section_id: Optional[int] = None
    folder_module_id: Optional[int] = None

    try:
        # Find the section. This is a bit simplified.
        # A more robust way would be to store section_id during setup_ia or iterate all sections.
        # For now, let's assume create_course_section was successful and we might need to find it by name.
        # Or, better, the setup_ia should store the created section_id somewhere accessible.
        # For this iteration, let's assume we need to find it.
        # This part is tricky without knowing the exact section ID.
        # Let's assume the section created by setup_ia is the one we need.
        # We need a way to get the section ID for "Entrenai IA".
        # MoodleClient.create_course_section returns a MoodleSection object.
        # The setup_ia endpoint should ideally store this.
        # For now, we'll try to find it by name, which is less robust.

        logger.info(
            f"Searching for section '{target_section_name}' in course {course_id}"
        )
        # This requires a method in MoodleClient like get_section_by_name(course_id, name)
        # Let's assume we have the section_id from a previous step or config for now.
        # This is a placeholder for fetching/knowing the correct section_id.
        # For the purpose of this endpoint, we'd typically have the section_id from the setup phase.
        # If not, we'd need to implement a robust get_section_by_name in MoodleClient.

        # Simplified: Assume the setup_ia_for_course stored the moodle_section_id somewhere,
        # or we re-fetch course contents and find it.
        # For now, let's simulate finding it. This part needs a robust solution.
        # We'll use get_course_module_by_name within a loop of sections if needed,
        # or a new MoodleClient method: get_section_by_name.

        # Let's assume we have a way to get the target_section_id.
        # This is a critical missing piece if not stored from setup.
        # For now, we'll try to find the folder directly in any section if section_id is unknown.
        # This is not ideal. A better approach is to get all sections, find the target one, then the folder.

        # Placeholder: Get all sections, find the one named `target_section_name`
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
            course_id,
            target_section_id=found_section_id,
            target_module_name=target_folder_name,
            target_mod_type="folder",
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

        # --- List files in the folder ---
        moodle_files = moodle.get_folder_files(folder_cmid=folder_cmid)
        if not moodle_files:
            logger.info(
                f"No files found in folder '{target_folder_name}' (cmid: {folder_cmid})."
            )
            return {
                "message": "No files found in the designated Moodle folder.",
                "files_checked": 0,
                "files_downloaded": 0,
            }

        logger.info(f"Found {len(moodle_files)} files in Moodle folder.")

        # --- Filter new/modified files and download ---
        files_to_download_count = 0
        downloaded_files_paths: List[str] = []

        # Ensure course-specific download directory exists
        course_download_dir = Path(base_config.download_dir) / str(course_id)
        course_download_dir.mkdir(parents=True, exist_ok=True)

        for mf in moodle_files:
            if not mf.filename or not mf.fileurl or mf.timemodified is None:
                logger.warning(
                    f"Skipping Moodle file with incomplete data: {mf.model_dump_json()}"
                )
                continue

            if file_tracker.is_file_new_or_modified(
                course_id, mf.filename, mf.timemodified
            ):
                logger.info(f"File '{mf.filename}' is new or modified. Downloading...")
                try:
                    downloaded_path = moodle.download_file(
                        file_url=str(mf.fileurl),  # Ensure HttpUrl is converted to str
                        download_dir=course_download_dir,
                        filename=mf.filename,
                    )
                    file_tracker.mark_file_as_processed(
                        course_id, mf.filename, mf.timemodified
                    )
                    files_to_download_count += 1
                    downloaded_files_paths.append(str(downloaded_path))
                    logger.info(
                        f"Successfully downloaded and marked as processed: {mf.filename}"
                    )
                except MoodleAPIError as e:
                    logger.error(f"Failed to download Moodle file '{mf.filename}': {e}")
                except Exception as e:
                    logger.exception(
                        f"Unexpected error downloading file '{mf.filename}': {e}"
                    )
            else:
                logger.info(
                    f"File '{mf.filename}' is already up-to-date. Skipping download."
                )

        msg = f"File refresh process completed for course {course_id}. Checked {len(moodle_files)} files. Downloaded {files_to_download_count} new/modified files."
        logger.info(msg)
        return {
            "message": msg,
            "files_checked": len(moodle_files),
            "files_downloaded": files_to_download_count,
            "downloaded_paths": downloaded_files_paths,  # For debugging/info
        }

    except HTTPException as http_exc:
        raise http_exc  # Re-raise FastAPI's HTTPExceptions
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


# import os # Moved to top
