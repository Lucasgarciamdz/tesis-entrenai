from pydantic import BaseModel, Field, HttpUrl
from typing import List, Optional, Dict, Any

class Curso(BaseModel):
    id: int
    nombre_corto: str
    nombre_completo: str
    nombre_mostrar: str
    resumen: Optional[str] = None

class RespuestaConfiguracionCurso(BaseModel):
    id_curso: int
    estado: str
    mensaje: str
    nombre_coleccion_vectorial: Optional[str] = None
    id_seccion_moodle: Optional[int] = None
    id_carpeta_moodle: Optional[int] = None
    id_chat_moodle: Optional[int] = None
    id_enlace_refresco: Optional[int] = None
    url_chat_n8n: Optional[HttpUrl] = None

class ArchivoProcesado(BaseModel):
    nombre: str
    ultima_modificacion_moodle: int

class RespuestaEliminacionArchivo(BaseModel):
    mensaje: str
    detalle: Optional[str] = None

# Aquí se agregarán más modelos según se migren los endpoints. 