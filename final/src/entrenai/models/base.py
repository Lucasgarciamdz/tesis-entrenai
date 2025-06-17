"""Modelos base para respuestas de la API."""

from typing import Any, Dict, Optional
from pydantic import BaseModel, Field


class BaseResponse(BaseModel):
    """Respuesta base para todas las operaciones."""
    success: bool = Field(description="Indica si la operación fue exitosa")
    message: str = Field(description="Mensaje descriptivo del resultado")
    data: Optional[Dict[str, Any]] = Field(default=None, description="Datos adicionales")


class ErrorResponse(BaseResponse):
    """Respuesta para errores."""
    success: bool = False
    error_code: Optional[str] = Field(default=None, description="Código de error específico")
    details: Optional[Dict[str, Any]] = Field(default=None, description="Detalles adicionales del error")


class ProcessingStatus(BaseModel):
    """Estado de procesamiento de tareas asíncronas."""
    task_id: str = Field(description="ID de la tarea")
    status: str = Field(description="Estado: pending, processing, completed, failed")
    progress: int = Field(default=0, description="Progreso en porcentaje (0-100)")
    message: str = Field(default="", description="Mensaje de estado")
    result: Optional[Dict[str, Any]] = Field(default=None, description="Resultado si está completado")
