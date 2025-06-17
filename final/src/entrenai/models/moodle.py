"""Modelos para objetos de Moodle."""

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class MoodleCourse(BaseModel):
    """Modelo simplificado de curso de Moodle."""
    id: int = Field(description="ID del curso")
    fullname: str = Field(description="Nombre completo del curso")
    shortname: str = Field(description="Nombre corto del curso")
    visible: bool = Field(default=True, description="Visibilidad del curso")
    categoryid: int = Field(description="ID de la categoría")


class MoodleSection(BaseModel):
    """Modelo de sección de curso de Moodle."""
    id: int = Field(description="ID de la sección")
    name: str = Field(description="Nombre de la sección")
    section: int = Field(description="Número de la sección")
    visible: bool = Field(default=True, description="Visibilidad de la sección")
    summary: str = Field(default="", description="Resumen de la sección")


class MoodleModule(BaseModel):
    """Modelo de módulo/actividad de Moodle."""
    id: int = Field(description="ID del módulo")
    name: str = Field(description="Nombre del módulo")
    modname: str = Field(description="Tipo de módulo (url, folder, etc.)")
    visible: bool = Field(default=True, description="Visibilidad del módulo")
    url: Optional[str] = Field(default=None, description="URL del módulo si aplica")


class MoodleFile(BaseModel):
    """Modelo de archivo de Moodle."""
    filename: str = Field(description="Nombre del archivo")
    filepath: str = Field(description="Ruta del archivo")
    filesize: int = Field(description="Tamaño del archivo en bytes")
    fileurl: str = Field(description="URL para descargar el archivo")
    mimetype: str = Field(description="Tipo MIME del archivo")
    timemodified: int = Field(description="Timestamp de modificación")


class MoodleUser(BaseModel):
    """Modelo básico de usuario de Moodle."""
    id: int = Field(description="ID del usuario")
    username: str = Field(description="Nombre de usuario")
    firstname: str = Field(description="Nombre")
    lastname: str = Field(description="Apellido")
    email: str = Field(description="Email del usuario")
