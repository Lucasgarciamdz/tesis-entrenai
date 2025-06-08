from typing import List, Optional, Dict, Any

from pydantic import BaseModel, Field, HttpUrl


# --- Modelos Específicos de Moodle ---


class CursoMoodle(BaseModel):
    id: int
    nombre_corto: str = Field(alias="shortname")
    nombre_completo: str = Field(alias="fullname")
    nombre_mostrar: str = Field(alias="displayname")
    resumen: Optional[str] = None

    class Config:
        populate_by_name = True

class SeccionMoodle(BaseModel):
    id: int
    nombre: str
    section: Optional[int] = None

    class Config:
        populate_by_name = True

class ModuloMoodle(BaseModel):
    id: int
    nombre: str
    nombre_modulo: str = Field(alias="modname")
    instancia: Optional[int] = None

    class Config:
        populate_by_name = True

class ArchivoMoodle(BaseModel):
    nombre_archivo: str = Field(alias="filename")
    ruta_archivo: str = Field(alias="filepath")
    tamano_archivo: int = Field(alias="filesize")
    url_archivo: HttpUrl = Field(alias="fileurl")
    tiempo_modificacion: int = Field(alias="timemodified")
    tipo_mime: Optional[str] = Field(None, alias="mimetype")

    class Config:
        populate_by_name = True


# --- Modelos Específicos de PgVector ---


class FragmentoDocumento(BaseModel):
    id: str
    id_curso: int
    id_documento: str
    texto: str
    embedding: Optional[List[float]] = None
    metadata: dict = Field(default_factory=dict)


# --- Modelos Específicos de N8N ---


class NodoN8N(BaseModel):
    id: str
    nombre: str = Field(alias="name")
    tipo: str = Field(alias="type")

    class Config:
        populate_by_name = True

class FlujoTrabajoN8N(BaseModel):
    id: str
    nombre: str = Field(alias="name")
    activo: bool = Field(alias="active")
    nodos: List[NodoN8N] = Field(default_factory=list, alias="nodes")

    class Config:
        populate_by_name = True


# --- Modelos de Solicitud/Respuesta de API ---

class SolicitudProcesarArchivo(BaseModel):
    id_curso: int
    nombre_curso: str
    info_archivo_moodle: Dict[str, Any]

class RespuestaConfiguracionCurso(BaseModel):
    id_curso: int
    estado: str
    mensaje: str
    nombre_coleccion_qdrant: str
    id_seccion_moodle: Optional[int] = None
    url_chat_n8n: Optional[HttpUrl] = None

class ArchivoIndexado(BaseModel):
    nombre_archivo: str
    ultima_modificacion_moodle: int

class RespuestaEliminarArchivo(BaseModel):
    mensaje: str
    detalle: Optional[str] = None
