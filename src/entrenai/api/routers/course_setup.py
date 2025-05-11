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
from src.entrenai.config import moodle_config, qdrant_config, ollama_config, n8n_config
from src.entrenai.utils.logger import get_logger

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


# import os # Moved to top
