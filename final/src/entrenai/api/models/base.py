from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime


class ConfiguracionIAResponse(BaseModel):
    """Respuesta para la configuración de IA de un curso."""
    curso_id: int
    estado: str
    mensaje: str
    nombre_tabla_vectores: str
    url_chat: Optional[str] = None


class MoodleCourse(BaseModel):
    """Modelo básico para cursos de Moodle."""
    id: int
    fullname: str
    shortname: str
    displayname: Optional[str] = None
    summary: Optional[str] = None


class DocumentChunk(BaseModel):
    """Modelo para chunks de documentos."""
    content: str
    embedding: List[float]
    metadata: Dict[str, Any] = {}
    filename: Optional[str] = None


class ProcessFileRequest(BaseModel):
    """Request para procesar archivos."""
    course_id: int
    filename: str
    force_reprocess: bool = False


class ProcessFileResponse(BaseModel):
    """Respuesta del procesamiento de archivos."""
    success: bool
    message: str
    chunks_processed: int = 0
    filename: str
