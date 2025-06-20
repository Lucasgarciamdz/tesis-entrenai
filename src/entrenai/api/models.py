from typing import List, Optional, Dict, Any

from pydantic import BaseModel, Field, HttpUrl


# --- Moodle Specific Models ---


class MoodleCourse(BaseModel):
    id: int
    shortname: str
    fullname: str
    displayname: str
    summary: Optional[str] = None
    # Add other relevant fields from Moodle's get_courses response


class MoodleSection(BaseModel):
    id: int
    name: str
    section: Optional[int] = None  # Section number
    summary: Optional[str] = None
    summaryformat: Optional[int] = None
    # Add other relevant fields


class MoodleModule(BaseModel):
    id: int
    name: str
    modname: str  # e.g., 'folder', 'url'
    instance: Optional[int] = None
    # Add other relevant fields


class MoodleFile(BaseModel):
    filename: str
    filepath: str
    filesize: int
    fileurl: HttpUrl
    timemodified: int
    mimetype: Optional[str] = None


class MoodleFolder(BaseModel):
    id: int  # Course module ID for the folder
    name: str
    # Potentially list of files if the API returns them directly


class MoodleUrl(BaseModel):
    id: int  # Course module ID for the URL
    name: str
    externalurl: HttpUrl


# --- Qdrant Specific Models ---


class DocumentChunk(BaseModel):
    id: str  # Unique ID for the chunk (e.g., uuid)
    course_id: int
    document_id: str  # ID of the source document
    text: str
    embedding: Optional[List[float]] = None  # Embedding vector
    metadata: dict = Field(default_factory=dict)
    # Metadata could include page_number, source_filename, original_text_md5, etc.


# --- N8N Specific Models ---
# These will depend heavily on how N8N workflows are structured and interacted with.
# Placeholder for now.


class N8NNodeParameters(BaseModel):
    # This model will be flexible to accommodate various node parameters
    # Use Field(default_factory=dict) for nested dictionaries that might not always be present
    initialMessages: Optional[str] = None
    options: Optional[Dict[str, Any]] = Field(default_factory=dict)
    # Add other common parameters if needed, or keep it flexible with **kwargs
    # For now, we only care about initialMessages and options for chatTrigger
    # and systemMessage for agent node.

class N8NNode(BaseModel):
    id: str
    name: str
    type: str
    typeVersion: float
    position: List[float]
    parameters: Optional[N8NNodeParameters] = None
    credentials: Optional[Dict[str, Any]] = None # Credentials can be complex, keep as dict for now
    webhookId: Optional[str] = None  # Added for chat trigger nodes
    # Add other fields that might be present in a node definition

class N8NWorkflow(BaseModel):
    id: str
    name: str
    active: bool
    nodes: List[N8NNode] = Field(default_factory=list)
    connections: Optional[Dict[str, Any]] = Field(default_factory=dict)
    settings: Optional[Dict[str, Any]] = Field(default_factory=dict)
    staticData: Optional[Dict[str, Any]] = None
    webhook_url: Optional[HttpUrl] = None # This might be derived, not directly from N8N API response
    meta: Optional[Dict[str, Any]] = Field(default_factory=dict)
    tags: Optional[List[str]] = Field(default_factory=list)


# --- API Request/Response Models (FastAPI) ---


class CourseSetupRequest(BaseModel):
    # Potentially professor_id or other auth info if needed
    pass  # For now, course_id is in path


class CourseSetupResponse(BaseModel):
    course_id: int
    status: str
    message: str
    qdrant_collection_name: str
    moodle_section_id: Optional[int] = None
    moodle_folder_id: Optional[int] = None
    moodle_chat_link_id: Optional[int] = None
    moodle_refresh_link_id: Optional[int] = None
    n8n_chat_url: Optional[HttpUrl] = None


class IndexedFile(BaseModel):
    filename: str
    last_modified_moodle: int


class DeleteFileResponse(BaseModel):
    message: str
    detail: Optional[str] = None


# Add other models as needed for API interactions, internal data structures, etc.


# --- File Processing Specific Models ---

class FileProcessingRequest(BaseModel):
    course_id: int
    course_name_for_pgvector: str
    moodle_file_info: MoodleFile # Reusing the existing MoodleFile model
    download_dir_str: str # This will be a relative path within the Fastapi container's /app/data
    ai_provider_config: Dict[str, Any]
    pgvector_config_dict: Dict[str, Any] # Serialized PgvectorConfig
    moodle_config_dict: Dict[str, Any]   # Serialized MoodleConfig
    base_config_dict: Dict[str, Any]     # Serialized BaseConfig

class FileProcessingResponse(BaseModel):
    filename: str
    status: str
    message: Optional[str] = None
    chunks_upserted: Optional[int] = None
    task_id: Optional[str] = None # To correlate with Celery task if needed, though Celery is now just a caller
    error_message: Optional[str] = None
