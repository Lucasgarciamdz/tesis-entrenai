"""Router para cursos."""

from fastapi import APIRouter
from typing import List, Dict, Any

from ...core.clients import MoodleClient

router = APIRouter(prefix="/courses", tags=["courses"])


@router.get("/", response_model=List[Dict[str, Any]])
async def get_courses():
    """Obtiene lista de cursos."""
    moodle_client = MoodleClient()
    return moodle_client.get_courses()


@router.get("/{course_id}/content", response_model=List[Dict[str, Any]])
async def get_course_content(course_id: int):
    """Obtiene contenido de un curso."""
    moodle_client = MoodleClient()
    return moodle_client.get_course_content(course_id)
