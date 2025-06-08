import json
from pathlib import Path
from typing import List, Optional, Dict, Any

from fastapi import APIRouter, HTTPException, Query, Depends, Request, status
from celery.result import AsyncResult

from entrenai_refactor.api import modelos as modelos_api
from entrenai_refactor.nucleo.clientes.cliente_moodle import ClienteMoodle, ErrorAPIMoodle
from entrenai_refactor.nucleo.clientes.cliente_n8n import ClienteN8N, ErrorClienteN8N
from entrenai_refactor.nucleo.bd.envoltorio_pgvector import EnvoltorioPgVector, ErrorEnvoltorioPgVector
from entrenai_refactor.nucleo.ia.proveedor_inteligencia import ProveedorInteligencia, ErrorProveedorInteligencia
from entrenai_refactor.celery.aplicacion_celery import aplicacion_celery # Importar la app Celery
from entrenai_refactor.celery.tareas import delegar_procesamiento_curso # Importar la tarea Celery
from entrenai_refactor.config.configuracion import configuracion_global
from entrenai_refactor.config.registrador import obtener_registrador

registrador = obtener_registrador(__name__)

enrutador = APIRouter(
    prefix="/api/v1", # Todas las rutas en este archivo tendrán este prefijo
    tags=["Configuración de Curso y Gestión de IA"], # Etiqueta para la documentación de Swagger/OpenAPI
)

# --- Funciones de Dependencia (Inyección) ---

def obtener_cliente_moodle() -> ClienteMoodle:
    try:
        return ClienteMoodle()
    except Exception as e:
        registrador.error(f"Error al crear instancia de ClienteMoodle: {e}")
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"No se pudo conectar con Moodle: {str(e)}")

def obtener_envoltorio_pgvector() -> EnvoltorioPgVector:
    try:
        return EnvoltorioPgVector()
    except Exception as e:
        registrador.error(f"Error al crear instancia de EnvoltorioPgVector: {e}")
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"No se pudo conectar con la base de datos vectorial: {str(e)}")

def obtener_cliente_n8n() -> ClienteN8N:
    try:
        return ClienteN8N()
    except Exception as e:
        registrador.error(f"Error al crear instancia de ClienteN8N: {e}")
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"No se pudo conectar con N8N: {str(e)}")

def obtener_proveedor_inteligencia() -> ProveedorInteligencia:
    try:
        return ProveedorInteligencia()
    except ErrorProveedorInteligencia as e: # Captura específica para errores de inicialización del proveedor
        registrador.error(f"Error al crear instancia de ProveedorInteligencia: {e}")
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"No se pudo inicializar el proveedor de IA: {str(e)}")
    except Exception as e: # Captura genérica para otros errores inesperados
        registrador.error(f"Error inesperado al crear ProveedorInteligencia: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error interno al configurar el proveedor de IA.")


# --- Función Auxiliar ---
async def _obtener_nombre_curso_operaciones(id_curso: int, cliente_moodle: ClienteMoodle) -> str:
    """Obtiene el nombre del curso para un id_curso dado, usado en operaciones de BD y N8N."""
    nombre_curso_para_ops: Optional[str] = None
    try:
        registrador.info(f"Obteniendo nombre del curso {id_curso} para operaciones...")
        id_profesor_defecto = configuracion_global.moodle.id_profesor_defecto

        if id_profesor_defecto:
            cursos = cliente_moodle.obtener_cursos_usuario(id_usuario=id_profesor_defecto)
            curso_encontrado = next((c for c in cursos if c.id == id_curso), None)
            if curso_encontrado:
                nombre_curso_para_ops = curso_encontrado.nombre_a_mostrar or curso_encontrado.nombre_completo

        if not nombre_curso_para_ops: # Si no se encontró con el profesor por defecto o no hay profesor por defecto
            todos_los_cursos = cliente_moodle.obtener_todos_los_cursos()
            curso_encontrado = next((c for c in todos_los_cursos if c.id == id_curso), None)
            if curso_encontrado:
                nombre_curso_para_ops = curso_encontrado.nombre_a_mostrar or curso_encontrado.nombre_completo

        if not nombre_curso_para_ops:
            registrador.warning(f"No se pudo encontrar el curso {id_curso} en Moodle para obtener su nombre.")
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Curso con ID {id_curso} no encontrado en Moodle.")

        registrador.info(f"Nombre del curso para operaciones: '{nombre_curso_para_ops}'")
        return nombre_curso_para_ops
    except ErrorAPIMoodle as e:
        registrador.error(f"Error API Moodle obteniendo nombre del curso {id_curso}: {e}")
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Error API Moodle al obtener nombre del curso {id_curso}.")
    except HTTPException: # Re-lanzar HTTPException (ej. 404 de arriba)
        raise
    except Exception as e:
        registrador.exception(f"Error inesperado obteniendo nombre del curso {id_curso}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"No se pudo determinar nombre del curso {id_curso}.")

# --- Endpoints ---

@enrutador.get("/salud", summary="Chequeo de Salud de la API", description="Endpoint simple para verificar que la API está operativa.")
async def verificar_salud_api():
    registrador.info("Chequeo de salud de la API solicitado.")
    return {"estado": "saludable"}

@enrutador.get("/cursos",
                response_model=List[modelos_api.CursoMoodle],
                summary="Listar Cursos de Moodle",
                description="Obtiene la lista de cursos de Moodle para un profesor. Si no se provee `id_usuario_moodle`, se utiliza el ID del profesor por defecto configurado en el servidor.")
async def listar_cursos_moodle(
    id_usuario_moodle: Optional[int] = Query(None, description="ID de Usuario de Moodle del profesor.", alias="idUsuarioMoodle"),
    cliente_moodle: ClienteMoodle = Depends(obtener_cliente_moodle)
):
    id_profesor_a_usar = id_usuario_moodle if id_usuario_moodle is not None else configuracion_global.moodle.id_profesor_defecto

    if id_profesor_a_usar is None:
        registrador.error("No se proporcionó ID de profesor y MOODLE_DEFAULT_TEACHER_ID no está configurado.")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Debe proporcionar un ID de profesor o configurar uno por defecto.")

    registrador.info(f"Obteniendo cursos de Moodle para ID de profesor: {id_profesor_a_usar}")
    try:
        cursos = cliente_moodle.obtener_cursos_usuario(id_usuario=id_profesor_a_usar)
        # Si se quisiera obtener todos los cursos si el usuario no tiene:
        # if not cursos:
        #     registrador.info(f"No se encontraron cursos para el usuario {id_profesor_a_usar}, obteniendo todos los cursos.")
        #     cursos = cliente_moodle.obtener_todos_los_cursos()
        return cursos
    except ErrorAPIMoodle as e:
        registrador.error(f"Error de API Moodle al obtener cursos: {e}")
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Error API Moodle: {str(e)}")
    except Exception as e:
        registrador.exception(f"Error inesperado obteniendo cursos de Moodle: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error interno del servidor: {str(e)}")

@enrutador.post("/cursos/{id_curso}/configurar-ia",
                 response_model=modelos_api.RespuestaConfiguracionCurso,
                 summary="Configurar IA para un Curso",
                 description="Configura la IA para un curso específico, incluyendo la creación de tabla vectorial, flujo N8N y elementos en Moodle.")
async def configurar_ia_para_curso(
    request: Request, # Necesario para construir URLs absolutas para Moodle
    id_curso: int,
    nombre_curso_query: Optional[str] = Query(None, alias="nombreCurso", description="Nombre del curso para la IA (opcional, se intentará obtener de Moodle)."),
    mensajes_iniciales: Optional[str] = Query(None, alias="mensajesIniciales", description="Mensajes iniciales para el chat de IA."),
    mensaje_sistema: Optional[str] = Query(None, alias="mensajeSistema", description="Mensaje del sistema para el agente de IA (se añadirá al mensaje por defecto)."),
    placeholder_entrada: Optional[str] = Query(None, alias="placeholderEntrada", description="Texto de marcador de posición para el campo de entrada del chat."),
    titulo_chat: Optional[str] = Query(None, alias="tituloChat", description="Título del chat de IA."),
    cliente_moodle: ClienteMoodle = Depends(obtener_cliente_moodle),
    bd_pgvector: EnvoltorioPgVector = Depends(obtener_envoltorio_pgvector),
    cliente_n8n: ClienteN8N = Depends(obtener_cliente_n8n),
    proveedor_ia: ProveedorInteligencia = Depends(obtener_proveedor_inteligencia)
):
    registrador.info(f"Iniciando configuración de IA para el curso ID: {id_curso}")
    nombre_curso_efectivo = nombre_curso_query or await _obtener_nombre_curso_operaciones(id_curso, cliente_moodle)

    if not nombre_curso_efectivo: # Doble chequeo por si _obtener_nombre_curso_operaciones falló de alguna manera no esperada
        registrador.error(f"El nombre del curso para el ID {id_curso} no pudo ser determinado.")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"No se pudo determinar el nombre del curso {id_curso}.")

    nombre_tabla_pgv = bd_pgvector.obtener_nombre_tabla_curso(nombre_curso_efectivo)
    tamano_vector = configuracion_global.db.tamano_vector_defecto # Podría obtenerse del proveedor_ia si es dinámico

    respuesta = modelos_api.RespuestaConfiguracionCurso(
        id_curso=id_curso, estado="pendiente",
        mensaje=f"Configuración iniciada para curso {id_curso} ('{nombre_curso_efectivo}').",
        nombre_tabla_vectorial=nombre_tabla_pgv
    )

    try:
        if not bd_pgvector.asegurar_tabla_curso(nombre_curso_efectivo, tamano_vector):
            raise ErrorEnvoltorioPgVector(f"Falló al asegurar tabla PgVector '{nombre_tabla_pgv}'.")
        registrador.info(f"Tabla PgVector '{nombre_tabla_pgv}' asegurada.")

        config_chat_moodle = cliente_moodle.obtener_configuracion_n8n_curso(id_curso) or {}

        # Priorizar query params sobre config de Moodle para personalización inmediata
        cfg_chat_final = modelos_api.ConfiguracionChatN8N(
            mensajes_iniciales=mensajes_iniciales or config_chat_moodle.get("initial_message"),
            mensaje_sistema=mensaje_sistema or config_chat_moodle.get("system_message_append"), # 'mensaje_sistema' en el modelo es 'anexo_mensaje_sistema'
            placeholder_entrada=placeholder_entrada or config_chat_moodle.get("input_placeholder"),
            titulo_chat=titulo_chat or config_chat_moodle.get("chat_title")
        )

        # Parámetros de configuración de IA para N8N
        # Estos se obtienen de la configuración global porque el proveedor ya está inicializado con ellos
        proveedor_activo = proveedor_ia.proveedor_ia_activo_nombre

        url_chat_n8n_str = cliente_n8n.configurar_y_desplegar_flujo_chat(
            id_curso=id_curso, nombre_curso=nombre_curso_efectivo,
            nombre_coleccion_pgvector=nombre_tabla_pgv,
            proveedor_ia_seleccionado=proveedor_activo,
            config_ollama=configuracion_global.ollama if proveedor_activo == "ollama" else None,
            config_gemini=configuracion_global.gemini if proveedor_activo == "gemini" else None,
            mensajes_iniciales=cfg_chat_final.mensajes_iniciales,
            mensaje_sistema_agente=cfg_chat_final.mensaje_sistema_oculto, # Usar el campo correcto del modelo
            placeholder_entrada=cfg_chat_final.placeholder_entrada,
            titulo_chat=cfg_chat_final.titulo_chat
        )
        respuesta.url_chat_n8n = HttpUrl(url_chat_n8n_str) if url_chat_n8n_str else None
        registrador.info(f"URL del chat N8N para '{nombre_curso_efectivo}': {respuesta.url_chat_n8n}")

        nombre_seccion_moodle = configuracion_global.moodle.nombre_carpeta_curso # Ej: "Documentos EntrenAI"
        seccion = cliente_moodle.crear_seccion_curso(id_curso, nombre_seccion_moodle)
        if not seccion or not seccion.id:
            raise ErrorAPIMoodle(f"Falló creación de sección Moodle para curso {id_curso}.")
        respuesta.id_seccion_moodle = seccion.id

        # URL para gestionar archivos (frontend simple) y para refrescar (endpoint API)
        url_base_str = str(request.base_url).rstrip("/")
        url_gestionar_archivos_ui = f"{url_base_str}/ui/gestionar_archivos.html?id_curso={id_curso}" # Placeholder UI
        url_refrescar_api = enrutador.url_path_for("refrescar_archivos_curso", id_curso=id_curso)
        url_refrescar_absoluta = f"{url_base_str}{url_refrescar_api}"

        sumario_html = f"""
<h4>Recursos de EntrenAI</h4>
<p>Utilice esta sección para interactuar con la Inteligencia Artificial de asistencia para este curso.</p>
<ul>
    <li><a href="{respuesta.url_chat_n8n if respuesta.url_chat_n8n else '#'}" target="_blank">{configuracion_global.moodle.nombre_enlace_chat}</a>: Acceda aquí para chatear con la IA.</li>
    <li>Carpeta "<strong>{configuracion_global.moodle.nombre_carpeta_curso}</strong>": Suba aquí los documentos que la IA utilizará.</li>
    <li><a href="{url_refrescar_absoluta}" target="_blank">{configuracion_global.moodle.nombre_enlace_refrescar}</a>: Haga clic aquí después de subir/modificar archivos.</li>
    <li><a href="{url_gestionar_archivos_ui}" target="_blank">Gestionar Archivos Indexados</a> (UI)</li>
</ul>
<p><strong>Nota para el profesor:</strong> Puede personalizar los textos del chat (bienvenida, título, etc.) y el comportamiento del agente IA contactando al administrador o, si está habilitado, mediante una interfaz de configuración avanzada.</p>
        """
        if not cliente_moodle.actualizar_sumario_seccion(id_curso, seccion.id, sumario_html): # Pasar id_curso
            registrador.warning(f"No se pudo actualizar el sumario de la sección {seccion.id} para el curso {id_curso}.")

        carpeta = cliente_moodle.crear_carpeta_en_seccion(id_curso, seccion.id, nombre_seccion_moodle) # Usar el mismo nombre para la carpeta
        if carpeta: respuesta.id_carpeta_moodle = carpeta.id

        if respuesta.url_chat_n8n:
            mod_chat_url = cliente_moodle.crear_url_en_seccion(id_curso, seccion.id, configuracion_global.moodle.nombre_enlace_chat, str(respuesta.url_chat_n8n))
            if mod_chat_url: respuesta.id_chat_moodle = mod_chat_url.id

        mod_refresco_url = cliente_moodle.crear_url_en_seccion(id_curso, seccion.id, configuracion_global.moodle.nombre_enlace_refrescar, url_refrescar_absoluta)
        if mod_refresco_url: respuesta.id_enlace_refresco_moodle = mod_refresco_url.id

        respuesta.estado = "exitoso"
        respuesta.mensaje = f"Configuración de EntrenAI IA completada para curso {id_curso} ('{nombre_curso_efectivo}')."
        registrador.info(respuesta.mensaje)
        return respuesta

    except HTTPException as e: # Re-lanzar HTTPExceptions
        raise e
    except (ErrorAPIMoodle, ErrorEnvoltorioPgVector, ErrorClienteN8N, ErrorProveedorInteligencia) as e_servicio:
        registrador.error(f"Error de servicio durante configuración de IA para curso {id_curso}: {e_servicio}")
        respuesta.estado = "fallido"
        respuesta.mensaje = f"Error de servicio: {str(e_servicio)}"
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=respuesta.mensaje)
    except Exception as e_inesperado:
        registrador.exception(f"Error inesperado durante configuración de IA para curso {id_curso}: {e_inesperado}")
        respuesta.estado = "fallido"
        respuesta.mensaje = f"Error interno del servidor: {str(e_inesperado)}"
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=respuesta.mensaje)


@enrutador.get("/cursos/{id_curso}/refrescar-archivos",
                summary="Refrescar Archivos del Curso",
                description="Inicia el procesamiento asíncrono de archivos para un curso, registrando una tarea Celery.")
async def refrescar_archivos_curso(id_curso: int):
    id_usuario_defecto = configuracion_global.moodle.id_profesor_defecto
    if id_usuario_defecto is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="ID de profesor por defecto no configurado.")

    registrador.info(f"Iniciando refresco de archivos para curso ID: {id_curso} por usuario ID: {id_usuario_defecto}")
    try:
        # Despachar la tarea Celery
        resultado_tarea = delegar_procesamiento_curso.delay(id_curso=id_curso, id_usuario=id_usuario_defecto)
        id_tarea = resultado_tarea.id
        registrador.info(f"Tarea Celery {id_tarea} despachada para procesar curso ID: {id_curso}")
        return {"id_tarea": id_tarea, "mensaje": f"Procesamiento de archivos para curso {id_curso} iniciado."}
    except Exception as e:
        registrador.exception(f"Error al despachar tarea Celery para curso {id_curso}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error al iniciar tarea de procesamiento.")


@enrutador.get("/tareas/{id_tarea}/estado",
                response_model=modelos_api.RespuestaEstadoTarea,
                summary="Consultar Estado de Tarea Asíncrona",
                description="Consulta el estado de una tarea Celery específica por su ID.")
async def obtener_estado_tarea(id_tarea: str):
    registrador.debug(f"Consultando estado para tarea ID: {id_tarea}")
    resultado_async = AsyncResult(id_tarea, app=aplicacion_celery)

    respuesta_estado = modelos_api.RespuestaEstadoTarea(
        id_tarea=id_tarea,
        estado=resultado_async.status,
        resultado=resultado_async.result if resultado_async.successful() else None,
        traceback=resultado_async.traceback if resultado_async.failed() else None
    )
    if resultado_async.failed() and respuesta_estado.resultado is None: # Resultado puede ser la excepción misma
        respuesta_estado.resultado = str(resultado_async.result)

    registrador.debug(f"Estado de tarea {id_tarea}: {respuesta_estado.model_dump_json()}")
    return respuesta_estado

@enrutador.get("/cursos/{id_curso}/archivos-indexados",
                response_model=List[modelos_api.ArchivoProcesado],
                summary="Listar Archivos Indexados de un Curso",
                description="Obtiene una lista de archivos que han sido procesados e indexados para un curso.")
async def listar_archivos_indexados_curso(
    id_curso: int,
    bd_pgvector: EnvoltorioPgVector = Depends(obtener_envoltorio_pgvector)
):
    registrador.info(f"Solicitud para obtener archivos indexados para curso ID: {id_curso}")
    try:
        marcas_tiempo_archivos = bd_pgvector.obtener_marcas_tiempo_archivos_procesados(id_curso=id_curso)
        if not marcas_tiempo_archivos: # Devuelve dict vacío si no hay o hay error, manejar error más explícito si es necesario
            # Considerar si 404 es apropiado o lista vacía. Lista vacía es más simple.
            registrador.info(f"No se encontraron archivos indexados para curso ID: {id_curso}.")
            return []

        archivos_procesados = [
            modelos_api.ArchivoProcesado(nombre=identificador, ultima_modificacion_moodle=ts)
            for identificador, ts in marcas_tiempo_archivos.items()
        ]
        return archivos_procesados
    except ErrorEnvoltorioPgVector as e:
        registrador.error(f"Error de BD obteniendo archivos indexados para curso {id_curso}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error de base de datos: {str(e)}")
    except Exception as e:
        registrador.exception(f"Error inesperado obteniendo archivos indexados para curso {id_curso}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error interno del servidor.")


@enrutador.delete("/cursos/{id_curso}/archivos-indexados/{identificador_archivo:path}",
                   response_model=modelos_api.RespuestaEliminacionArchivo,
                   summary="Eliminar Archivo Indexado",
                   description="Elimina un archivo específico y sus datos asociados (fragmentos vectoriales y registro de seguimiento).")
async def eliminar_archivo_indexado(
    id_curso: int,
    identificador_archivo: str, # FastAPI decodifica automáticamente el path param
    cliente_moodle: ClienteMoodle = Depends(obtener_cliente_moodle), # Para obtener nombre_curso
    bd_pgvector: EnvoltorioPgVector = Depends(obtener_envoltorio_pgvector)
):
    registrador.info(f"Solicitud para eliminar archivo '{identificador_archivo}' del curso ID: {id_curso}")
    try:
        nombre_curso = await _obtener_nombre_curso_operaciones(id_curso, cliente_moodle)

        registrador.info(f"Eliminando fragmentos para doc ID '{identificador_archivo}' de tabla para curso '{nombre_curso}'.")
        exito_chunks = bd_pgvector.eliminar_fragmentos_por_id_documento(nombre_curso, identificador_archivo)

        registrador.info(f"Eliminando archivo '{identificador_archivo}' (curso {id_curso}) de tabla de seguimiento.")
        exito_tracker = bd_pgvector.eliminar_archivo_de_seguimiento(id_curso, identificador_archivo)

        if exito_chunks and exito_tracker:
            mensaje = f"Archivo '{identificador_archivo}' y sus datos asociados eliminados exitosamente para curso {id_curso}."
            registrador.info(mensaje)
            return modelos_api.RespuestaEliminacionArchivo(mensaje=mensaje)
        else:
            detalle_error = f"Resultado eliminación chunks: {'éxito' if exito_chunks else 'fallo'}. Resultado eliminación tracker: {'éxito' if exito_tracker else 'fallo'}."
            registrador.error(f"Falló la eliminación completa de '{identificador_archivo}' para curso {id_curso}. {detalle_error}")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error al eliminar datos del archivo. {detalle_error}")

    except HTTPException as e:
        raise e # Re-lanzar HTTPExceptions (ej. de _obtener_nombre_curso)
    except Exception as e:
        registrador.exception(f"Error inesperado eliminando archivo '{identificador_archivo}' para curso {id_curso}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error interno: {str(e)}")


@enrutador.get("/cursos/{id_curso}/configuracion-chat-n8n",
                response_model=modelos_api.ConfiguracionChatN8N,
                summary="Obtener Configuración del Chat N8N",
                description="Obtiene la configuración actual del flujo de N8N para un curso (mensajes iniciales, título, etc.).")
async def obtener_configuracion_chat_n8n_curso(
    id_curso: int,
    cliente_moodle: ClienteMoodle = Depends(obtener_cliente_moodle), # Para obtener nombre_curso
    cliente_n8n: ClienteN8N = Depends(obtener_cliente_n8n)
):
    registrador.info(f"Obteniendo configuración de chat N8N para curso ID: {id_curso}")
    try:
        nombre_curso = await _obtener_nombre_curso_operaciones(id_curso, cliente_moodle)
        nombre_flujo_esperado = f"Entrenai - {id_curso} - {nombre_curso}"

        flujos = cliente_n8n.obtener_lista_flujos_trabajo()
        flujo_objetivo = next((f for f in flujos if f.name == nombre_flujo_esperado and f.active), None)

        if not flujo_objetivo or not flujo_objetivo.id:
            flujo_objetivo = next((f for f in flujos if f.name and f.name.startswith(f"Entrenai - {id_curso}") and f.active), None) # Fallback a cualquier activo para el curso

        if not flujo_objetivo or not flujo_objetivo.id: # Asegurar que flujo_objetivo.id no sea None
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"No se encontró flujo N8N activo para curso {id_curso} con nombre '{nombre_flujo_esperado}'.")

        detalles_flujo = cliente_n8n.obtener_detalles_flujo_trabajo(flujo_objetivo.id)
        if not detalles_flujo:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"No se pudieron obtener detalles del flujo N8N ID '{flujo_objetivo.id}'.")

        config_chat = modelos_api.ConfiguracionChatN8N()
        for nodo in detalles_flujo.nodes:
            if nodo.type == "@n8n/n8n-nodes-langchain.chatTrigger" and nodo.parameters:
                config_chat.mensajes_iniciales = nodo.parameters.initialMessages
                if nodo.parameters.options:
                    config_chat.placeholder_entrada = nodo.parameters.options.get("inputPlaceholder")
                    config_chat.titulo_chat = nodo.parameters.options.get("title")
            elif nodo.type == "@n8n/n8n-nodes-langchain.agent" and nodo.parameters and nodo.parameters.options:
                # El alias en el modelo se encarga de mapear "mensaje_sistema" a "mensaje_sistema_oculto"
                config_chat.mensaje_sistema_oculto = nodo.parameters.options.get("systemMessage")

        return config_chat

    except HTTPException as e:
        raise e
    except ErrorClienteN8N as e:
        registrador.error(f"Error de cliente N8N para curso {id_curso}: {e}")
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Error N8N: {str(e)}")
    except Exception as e:
        registrador.exception(f"Error inesperado obteniendo config N8N para curso {id_curso}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error interno: {str(e)}")

[end of entrenai_refactor/api/rutas/ruta_configuracion_curso.py]
