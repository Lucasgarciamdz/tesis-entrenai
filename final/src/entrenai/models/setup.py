"""Modelos para el setup y configuración de IA."""

from typing import Optional, Dict, Any
from pydantic import BaseModel, Field


class SetupRequest(BaseModel):
    """Solicitud para configurar IA en un curso."""
    course_id: int = Field(description="ID del curso en Moodle")
    course_name: Optional[str] = Field(default=None, description="Nombre del curso (opcional)")
    initial_messages: Optional[str] = Field(
        default="¡Hola! Soy el asistente de IA de este curso. ¿En qué puedo ayudarte?",
        description="Mensajes iniciales para el chat"
    )
    ai_provider: Optional[str] = Field(default=None, description="Proveedor de IA específico")


class SetupResponse(BaseModel):
    """Respuesta del setup de IA."""
    course_id: int = Field(description="ID del curso")
    status: str = Field(description="Estado: success, error, partial")
    message: str = Field(description="Mensaje descriptivo")
    vector_table: str = Field(description="Nombre de la tabla de vectores creada")
    workflow_url: Optional[str] = Field(default=None, description="URL del workflow de chat")
    section_id: Optional[int] = Field(default=None, description="ID de la sección creada en Moodle")
    details: Optional[Dict[str, Any]] = Field(default=None, description="Detalles adicionales")


class CourseStatus(BaseModel):
    """Estado de configuración de IA de un curso."""
    course_id: int = Field(description="ID del curso")
    has_vector_table: bool = Field(description="Tiene tabla de vectores")
    vector_table_name: str = Field(description="Nombre de la tabla de vectores")
    document_count: int = Field(default=0, description="Cantidad de documentos indexados")
    has_workflow: bool = Field(default=False, description="Tiene workflow de N8N")
    workflow_url: Optional[str] = Field(default=None, description="URL del workflow")
    has_moodle_section: bool = Field(default=False, description="Tiene sección en Moodle")
    section_id: Optional[int] = Field(default=None, description="ID de la sección")


class FileProcessRequest(BaseModel):
    """Solicitud para procesar archivos de un curso."""
    course_id: int = Field(description="ID del curso")
    folder_id: Optional[int] = Field(default=None, description="ID de carpeta específica")
    file_types: Optional[list] = Field(
        default=["pdf", "txt", "docx", "pptx"],
        description="Tipos de archivo a procesar"
    )
    force_reprocess: bool = Field(default=False, description="Forzar reprocesamiento")


class CleanupRequest(BaseModel):
    """Solicitud para limpiar configuración de IA."""
    course_id: int = Field(description="ID del curso")
    remove_vector_table: bool = Field(default=True, description="Eliminar tabla de vectores")
    remove_workflow: bool = Field(default=True, description="Eliminar workflow de N8N")
    remove_moodle_section: bool = Field(default=False, description="Eliminar sección de Moodle")
