from pydantic import BaseModel, Field, HttpUrl
from typing import List, Optional

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


class N8NWorkflow(BaseModel):
    id: str
    name: str
    active: bool
    webhook_url: Optional[HttpUrl] = None


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


# Add other models as needed for API interactions, internal data structures, etc.

if __name__ == "__main__":
    # Example usage for quick validation
    course_example = MoodleCourse(
        id=1,
        shortname="CS101",
        fullname="Introduction to Computer Science",
        displayname="CS101 Intro",
    )
    print(course_example.model_dump_json(indent=2))

    chunk_example = DocumentChunk(
        id="chunk_123",
        course_id=101,
        document_id="doc_abc",
        text="This is a sample chunk of text.",
        metadata={"page": 1, "source": "lecture1.pdf"},
    )
    print(chunk_example.model_dump_json(indent=2))
