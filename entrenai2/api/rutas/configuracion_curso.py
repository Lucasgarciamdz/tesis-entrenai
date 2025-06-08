from typing import List, Optional, Dict, Any, Union
from datetime import datetime

from celery.result import AsyncResult
from fastapi import APIRouter, HTTPException, Depends

from entrenai2.api.modelos import (
    CursoMoodle,
    RespuestaConfiguracionCurso,
    HttpUrl,
    ArchivoIndexado,
    RespuestaEliminarArchivo,
    SeccionMoodle,
)
from entrenai2.celery.aplicacion_celery_minimal import aplicacion as aplicacion_celery
from entrenai2.configuracion.configuracion import config
from entrenai2.configuracion.registrador import obtener_registrador
from entrenai2.nucleo.ia.proveedor_ia import ProveedorIA, ErrorProveedorIA
from entrenai2.nucleo.ia.envoltorio_ollama import EnvoltorioOllama
from entrenai2.nucleo.ia.envoltorio_gemini import EnvoltorioGemini
from entrenai2.nucleo.clientes.cliente_moodle import ClienteMoodle, ErrorAPIMoodle
from entrenai2.nucleo.clientes.cliente_n8n import ClienteN8N, ErrorClienteN8N
from entrenai2.nucleo.bd.envoltorio_pgvector import EnvoltorioPgvector, ErrorEnvoltorioPgvector
from entrenai2.celery.tareas_minimal import procesar_contenido_curso_moodle_minimal

registrador = obtener_registrador(__name__)

enrutador = APIRouter(
    prefix="/api/v1",
    tags=["Configuración de Curso y Gestión de IA"],
)

# --- Inyección de Dependencias ---

def obtener_cliente_moodle() -> ClienteMoodle:
    try:
        return ClienteMoodle()
    except Exception as e:
        registrador.error(f"Error al crear ClienteMoodle: {e}")
        raise HTTPException(status_code=503, detail="No se pudo conectar con Moodle.")

def obtener_envoltorio_pgvector() -> EnvoltorioPgvector:
    try:
        return EnvoltorioPgvector()
    except Exception as e:
        registrador.error(f"Error al crear EnvoltorioPgvector: {e}")
        raise HTTPException(status_code=503, detail="No se pudo conectar con la base de datos vectorial.")

def obtener_cliente_ia() -> Union[EnvoltorioOllama, EnvoltorioGemini]:
    try:
        return ProveedorIA.obtener_envoltorio_ia_por_proveedor(config.proveedor_ia)
    except ErrorProveedorIA as e:
        registrador.error(f"Error al obtener el cliente de IA: {e}")
        raise HTTPException(status_code=500, detail="No se pudo inicializar el proveedor de IA.")

def obtener_cliente_n8n() -> ClienteN8N:
    try:
        return ClienteN8N()
    except Exception as e:
        registrador.error(f"Error al crear ClienteN8N: {e}")
        raise HTTPException(status_code=503, detail="No se pudo conectar con n8n.")

# --- Funciones Auxiliares ---

async def _obtener_nombre_curso(id_curso: int, cliente_moodle: ClienteMoodle) -> str:
    """Obtiene el nombre de un curso desde Moodle."""
    try:
        cursos = cliente_moodle.obtener_todos_los_cursos()
        curso = next((c for c in cursos if c.id == id_curso), None)
        if not curso:
            raise HTTPException(status_code=404, detail=f"Curso con ID {id_curso} no encontrado.")
        return curso.nombre_completo
    except ErrorAPIMoodle as e:
        raise HTTPException(status_code=502, detail=f"Error de API de Moodle: {e}")

# --- Endpoints ---

@enrutador.get("/cursos", response_model=List[CursoMoodle])
async def listar_cursos_moodle(cliente: ClienteMoodle = Depends(obtener_cliente_moodle)):
    """Obtiene la lista de todos los cursos de Moodle."""
    try:
        return cliente.obtener_todos_los_cursos()
    except ErrorAPIMoodle as e:
        raise HTTPException(status_code=502, detail=f"Error de API de Moodle: {e}")

@enrutador.post("/cursos/{id_curso}/configurar-ia", response_model=RespuestaConfiguracionCurso)
async def configurar_ia_para_curso(
    id_curso: int,
    cliente_moodle: ClienteMoodle = Depends(obtener_cliente_moodle),
    bd_pgvector: EnvoltorioPgvector = Depends(obtener_envoltorio_pgvector),
    cliente_n8n: ClienteN8N = Depends(obtener_cliente_n8n),
):
    """Configura la IA para un curso, incluyendo la base de datos y el flujo de chat."""
    nombre_curso = await _obtener_nombre_curso(id_curso, cliente_moodle)
    nombre_tabla_pgvector = bd_pgvector.obtener_nombre_tabla(nombre_curso)
    
    try:
        bd_pgvector.asegurar_tabla(nombre_curso, config.db.tamano_vector_defecto)
        
        url_chat = cliente_n8n.configurar_y_desplegar_flujo_chat(id_curso, nombre_curso, nombre_tabla_pgvector)
        
        seccion = cliente_moodle.asegurar_existencia_recurso(
            id_curso, config.moodle.nombre_carpeta_curso,
            lambda: cliente_moodle.crear_seccion_curso(id_curso, config.moodle.nombre_carpeta_curso)
        )
        if not seccion or not isinstance(seccion, SeccionMoodle):
            raise HTTPException(status_code=500, detail="No se pudo crear o encontrar la sección en Moodle.")

        cliente_moodle.asegurar_existencia_recurso(id_curso, "Documentos Entrenai", lambda: cliente_moodle.crear_carpeta_en_seccion(id_curso, seccion.id, "Documentos Entrenai"))
        if url_chat:
            cliente_moodle.asegurar_existencia_recurso(id_curso, config.moodle.nombre_enlace_chat, lambda: cliente_moodle.crear_url_en_seccion(id_curso, seccion.id, config.moodle.nombre_enlace_chat, url_chat))

        return RespuestaConfiguracionCurso(
            id_curso=id_curso,
            estado="exitoso",
            mensaje=f"Configuración completada para el curso '{nombre_curso}'.",
            nombre_coleccion_qdrant=nombre_tabla_pgvector,
            url_chat_n8n=HttpUrl(url=url_chat) if url_chat else None,
            id_seccion_moodle=seccion.id
        )

    except (ErrorAPIMoodle, ErrorClienteN8N, ErrorEnvoltorioPgvector) as e:
        raise HTTPException(status_code=500, detail=str(e))

@enrutador.get("/cursos/{id_curso}/refrescar-archivos")
async def refrescar_archivos_curso(id_curso: int):
    """Inicia el procesamiento asíncrono de archivos para un curso."""
    if not config.moodle.id_profesor_defecto:
        raise HTTPException(status_code=400, detail="ID de profesor por defecto no configurado.")
    
    tarea = procesar_contenido_curso_moodle_minimal.delay(id_curso, config.moodle.id_profesor_defecto) # type: ignore
    return {"mensaje": "Proceso de refresco iniciado.", "id_tarea": tarea.id}

@enrutador.get("/tarea/{id_tarea}/estado")
async def obtener_estado_tarea(id_tarea: str):
    """Consulta el estado de una tarea Celery."""
    resultado = AsyncResult(id_tarea, app=aplicacion_celery)
    return {"id_tarea": id_tarea, "estado": resultado.status, "resultado": resultado.result}

@enrutador.get("/cursos/{id_curso}/archivos-indexados", response_model=List[ArchivoIndexado])
async def obtener_archivos_indexados(id_curso: int, bd_pgvector: EnvoltorioPgvector = Depends(obtener_envoltorio_pgvector)):
    """Obtiene la lista de archivos procesados para un curso."""
    try:
        archivos = bd_pgvector.obtener_marcas_tiempo_archivos_procesados(id_curso)
        return [ArchivoIndexado(nombre_archivo=nombre, ultima_modificacion_moodle=ts) for nombre, ts in archivos.items()]
    except ErrorEnvoltorioPgvector as e:
        raise HTTPException(status_code=500, detail=str(e))

@enrutador.delete("/cursos/{id_curso}/archivos-indexados/{identificador_archivo}", response_model=RespuestaEliminarArchivo)
async def eliminar_archivo_indexado(
    id_curso: int,
    identificador_archivo: str,
    cliente_moodle: ClienteMoodle = Depends(obtener_cliente_moodle),
    bd_pgvector: EnvoltorioPgvector = Depends(obtener_envoltorio_pgvector),
):
    """Elimina un archivo y sus datos asociados del sistema."""
    nombre_curso = await _obtener_nombre_curso(id_curso, cliente_moodle)
    id_documento = f"{id_curso}_{identificador_archivo}"
    
    try:
        bd_pgvector.eliminar_fragmentos_archivo(nombre_curso, id_documento)
        bd_pgvector.eliminar_archivo_de_seguimiento(id_curso, identificador_archivo)
        return RespuestaEliminarArchivo(mensaje=f"Archivo '{identificador_archivo}' eliminado exitosamente.")
    except ErrorEnvoltorioPgvector as e:
        raise HTTPException(status_code=500, detail=str(e))

@enrutador.get("/verificacion-salud")
async def verificacion_salud_api():
    """Endpoint simple de verificación de salud."""
    return {"estado": "ok", "marca_tiempo": str(datetime.now())}
