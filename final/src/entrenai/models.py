"""Modelos de datos simplificados para EntrenAI."""

from typing import List, Optional, Dict, Any
from pydantic import BaseModel


class MoodleCourse(BaseModel):
    """Modelo de curso de Moodle."""
    id: int
    fullname: str
    shortname: str
    categoryid: Optional[int] = None


class MoodleSection(BaseModel):
    """Modelo de sección de Moodle."""
    id: int
    name: str
    section: int
    course: int


class MoodleModule(BaseModel):
    """Modelo de módulo de Moodle."""
    id: int
    name: str
    modname: str
    url: Optional[str] = None


class MoodleFile(BaseModel):
    """Modelo de archivo de Moodle."""
    filename: str
    filepath: str
    filesize: int
    mimetype: str
    fileurl: str


class SetupResponse(BaseModel):
    """Respuesta del setup de IA."""
    course_id: int
    status: str
    message: str
    vector_table: str
    workflow_url: Optional[str] = None


class ChatMessage(BaseModel):
    """Mensaje de chat."""
    content: str
    role: str = "user"  # user, assistant, system


class ChatResponse(BaseModel):
    """Respuesta de chat."""
    message: str
    sources: List[str] = []
