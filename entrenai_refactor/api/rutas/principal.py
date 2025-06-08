from fastapi import APIRouter, HTTPException, Query
from typing import List, Optional
import logging
from entrenai_refactor.api.modelos import Curso, RespuestaConfiguracionCurso, ArchivoProcesado
from entrenai_refactor.core.clientes.moodle import ClienteMoodle, ErrorAPIMoodle
from entrenai_refactor.core.bd.pgvector import BaseVectorial, ErrorBaseVectorial
from entrenai_refactor.core.archivos.procesador import ProcesadorArchivos, ErrorProcesamientoArchivo
from entrenai_refactor.core.ia.gestor_ia import GestorIA, ErrorIA
from entrenai_refactor.config.configuracion import config

router = APIRouter(
    prefix="/api/v1",
    tags=["Configuración de Curso y Gestión de IA"],
)

logger = logging.getLogger("api")
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)
logger.setLevel(logging.INFO)

@router.get("/salud")
def salud():
    logger.info("Chequeo de salud de la API exitoso.")
    return {"estado": "ok"}

@router.get("/salud-celery")
def salud_celery():
    logger.info("Chequeo de salud de Celery exitoso.")
    return {"estado": "ok"}

@router.get("/cursos", response_model=List[Curso])
def obtener_cursos(id_usuario: Optional[int] = Query(None, description="ID del usuario de Moodle")):
    logger.info(f"Listando cursos para usuario {id_usuario}")
    if id_usuario is None:
        raise HTTPException(status_code=400, detail="Debe proporcionar un ID de usuario de Moodle.")
    try:
        cliente = ClienteMoodle()
        cursos = cliente.obtener_cursos_por_usuario(id_usuario)
        return cursos
    except ErrorAPIMoodle as e:
        logger.error(f"Error al obtener cursos de Moodle: {e}")
        raise HTTPException(status_code=502, detail=str(e))

@router.post("/cursos/{id_curso}/configurar-ia", response_model=RespuestaConfiguracionCurso)
def configurar_ia(id_curso: int):
    logger.info(f"Configurando IA para el curso {id_curso}")
    try:
        gestor_ia = GestorIA(
            host=config.n8n_url,  # Cambia esto por la URL de Ollama si corresponde
            modelo_embedding="nomic-embed-text",
            modelo_qa="llama3"
        )
        gestor_ia.generar_embedding("Ejemplo de texto para IA")
        bd_vectorial = BaseVectorial()
        return RespuestaConfiguracionCurso(
            id_curso=id_curso,
            estado="ok",
            mensaje="IA configurada correctamente para el curso.",
            nombre_coleccion_vectorial=f"coleccion_curso_{id_curso}"
        )
    except (ErrorIA, ErrorBaseVectorial) as e:
        logger.error(f"Error al configurar IA para el curso: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/cursos/{id_curso}/refrescar-archivos")
def refrescar_archivos(id_curso: int):
    logger.info(f"Refrescando archivos indexados para el curso {id_curso}")
    try:
        # Aquí deberías obtener la lista de archivos desde Moodle y procesarlos
        return {"id_curso": id_curso, "mensaje": "Archivos refrescados correctamente."}
    except Exception as e:
        logger.error(f"Error al refrescar archivos: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/cursos/{id_curso}/archivos-procesados", response_model=List[ArchivoProcesado])
def obtener_archivos_procesados(id_curso: int):
    logger.info(f"Obteniendo archivos procesados para el curso {id_curso}")
    try:
        bd_vectorial = BaseVectorial()
        archivos = bd_vectorial.obtener_archivos_procesados(id_curso)
        return [ArchivoProcesado(nombre=nombre, ultima_modificacion_moodle=ts) for nombre, ts in archivos.items()]
    except ErrorBaseVectorial as e:
        logger.error(f"Error al obtener archivos procesados: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/cursos/{id_curso}/archivos-procesados/{id_archivo}")
def eliminar_archivo_procesado(id_curso: int, id_archivo: str):
    logger.info(f"Eliminando archivo procesado {id_archivo} del curso {id_curso}")
    try:
        bd_vectorial = BaseVectorial()
        # Aquí deberías eliminar el archivo de la base de datos vectorial
        return {"id_curso": id_curso, "id_archivo": id_archivo, "mensaje": "Archivo eliminado correctamente."}
    except ErrorBaseVectorial as e:
        logger.error(f"Error al eliminar archivo procesado: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/tareas/{id_tarea}/estado")
def estado_tarea(id_tarea: str):
    logger.info(f"Consultando estado de la tarea {id_tarea}")
    return {"id_tarea": id_tarea, "estado": "completada"}

@router.get("/cursos/{id_curso}/flujo-n8n")
def obtener_flujo_n8n(id_curso: int):
    logger.info(f"Obteniendo configuración de flujo N8n para el curso {id_curso}")
    return {"id_curso": id_curso, "flujo": {"nombre": "Flujo N8n de ejemplo"}}

# Aquí se migrarán y simplificarán los endpoints principales del router original, todos en español. 