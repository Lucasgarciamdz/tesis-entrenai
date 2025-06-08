import json
from pathlib import Path
from typing import List, Optional, Dict, Any

from fastapi import APIRouter, HTTPException, Query, Depends, Request, status
from celery.result import AsyncResult

# Importar modelos Pydantic refactorizados (usando sus nuevos nombres en español)
from entrenai_refactor.api import modelos as modelos_api_traducidos
# Importar clases refactorizadas del núcleo
from entrenai_refactor.nucleo.clientes import ClienteMoodle, ErrorAPIMoodle
from entrenai_refactor.nucleo.clientes import ClienteN8N, ErrorClienteN8N
from entrenai_refactor.nucleo.bd import EnvoltorioPgVector, ErrorBaseDeDatosVectorial
from entrenai_refactor.nucleo.ia import ProveedorInteligencia, ErrorProveedorInteligencia
# Celery y tareas
from entrenai_refactor.celery.aplicacion_celery import aplicacion_celery
from entrenai_refactor.celery.tareas import delegar_procesamiento_curso # Asumiendo que este nombre se mantiene o se traduce también
# Configuración y logging
from entrenai_refactor.config.configuracion import configuracion_global
from entrenai_refactor.config.registrador import obtener_registrador

registrador = obtener_registrador(__name__)

enrutador_config_curso = APIRouter( # Renombrado para mayor claridad
    prefix="/api/v1",
    tags=["Configuración de Cursos y Gestión de IA"],
)

# --- Funciones de Dependencia (Inyección de Dependencias de FastAPI) ---

def dependencia_cliente_moodle() -> ClienteMoodle:
    """Dependencia para obtener una instancia del ClienteMoodle."""
    try:
        return ClienteMoodle()
    except ErrorAPIMoodle as e_moodle: # Captura la excepción personalizada del cliente
        registrador.error(f"Error específico al crear instancia de ClienteMoodle: {e_moodle}")
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"No se pudo conectar con Moodle: {str(e_moodle)}")
    except Exception as e_inesperado:
        registrador.exception(f"Error inesperado al crear instancia de ClienteMoodle: {e_inesperado}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error interno al configurar la conexión con Moodle.")

def dependencia_envoltorio_pgvector() -> EnvoltorioPgVector:
    """Dependencia para obtener una instancia del EnvoltorioPgVector."""
    try:
        return EnvoltorioPgVector()
    except ErrorBaseDeDatosVectorial as e_bd_vec:
        registrador.error(f"Error específico al crear instancia de EnvoltorioPgVector: {e_bd_vec}")
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"No se pudo conectar con la base de datos vectorial: {str(e_bd_vec)}")
    except Exception as e_inesperado:
        registrador.exception(f"Error inesperado al crear instancia de EnvoltorioPgVector: {e_inesperado}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error interno al configurar el acceso a la base de datos vectorial.")

def dependencia_cliente_n8n() -> ClienteN8N:
    """Dependencia para obtener una instancia del ClienteN8N."""
    try:
        return ClienteN8N()
    except ErrorClienteN8N as e_n8n:
        registrador.error(f"Error específico al crear instancia de ClienteN8N: {e_n8n}")
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"No se pudo conectar con el servicio N8N: {str(e_n8n)}")
    except Exception as e_inesperado:
        registrador.exception(f"Error inesperado al crear instancia de ClienteN8N: {e_inesperado}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error interno al configurar la conexión con N8N.")

def dependencia_proveedor_inteligencia() -> ProveedorInteligencia:
    """Dependencia para obtener una instancia del ProveedorInteligencia."""
    try:
        return ProveedorInteligencia()
    except ErrorProveedorInteligencia as e_prov_ia:
        registrador.error(f"Error específico al crear instancia de ProveedorInteligencia: {e_prov_ia}")
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"No se pudo inicializar el proveedor de IA configurado: {str(e_prov_ia)}")
    except Exception as e_inesperado:
        registrador.exception(f"Error inesperado al crear instancia de ProveedorInteligencia: {e_inesperado}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error interno al configurar el proveedor de IA.")

# --- Función Auxiliar ---
async def _aux_obtener_nombre_curso(id_curso: int, cliente_moodle: ClienteMoodle) -> str:
    """Obtiene el nombre del curso para un id_curso dado, usado en operaciones de BD y N8N. Lanza HTTPException si no se encuentra."""
    nombre_curso_para_operaciones: Optional[str] = None
    registrador.debug(f"Auxiliar: Obteniendo nombre del curso con ID {id_curso}.")
    try:
        id_profesor_por_defecto = configuracion_global.moodle.id_profesor_defecto

        if id_profesor_por_defecto:
            cursos_profesor = cliente_moodle.obtener_cursos_de_usuario(id_usuario=id_profesor_por_defecto) # Método refactorizado
            curso_encontrado_profesor = next((c for c in cursos_profesor if c.id == id_curso), None)
            if curso_encontrado_profesor:
                nombre_curso_para_operaciones = curso_encontrado_profesor.nombre_a_mostrar or curso_encontrado_profesor.nombre_completo

        if not nombre_curso_para_operaciones:
            todos_los_cursos_moodle = cliente_moodle.obtener_todos_los_cursos_disponibles() # Método refactorizado
            curso_encontrado_todos = next((c for c in todos_los_cursos_moodle if c.id == id_curso), None)
            if curso_encontrado_todos:
                nombre_curso_para_operaciones = curso_encontrado_todos.nombre_a_mostrar or curso_encontrado_todos.nombre_completo

        if not nombre_curso_para_operaciones:
            registrador.warning(f"No se pudo encontrar el curso con ID {id_curso} en Moodle para obtener su nombre.")
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"El curso con ID {id_curso} no fue encontrado en Moodle.")

        registrador.info(f"Nombre del curso ID {id_curso} obtenido para operaciones: '{nombre_curso_para_operaciones}'.")
        return nombre_curso_para_operaciones
    except ErrorAPIMoodle as e_moodle_api:
        registrador.error(f"Error de API Moodle al obtener nombre del curso {id_curso}: {e_moodle_api}")
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Error de comunicación con Moodle al obtener el nombre del curso {id_curso}: {str(e_moodle_api)}")
    except HTTPException: # Re-lanzar HTTPExceptions (ej. 404 de arriba)
        raise
    except Exception as e_inesperado:
        registrador.exception(f"Error inesperado al obtener nombre del curso {id_curso}: {e_inesperado}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"No se pudo determinar el nombre del curso {id_curso} debido a un error interno.")

# --- Endpoints de la API ---

@enrutador_config_curso.get("/salud",
                             summary="Chequeo de Salud de la API de Configuración",
                             description="Endpoint simple para verificar que la API de configuración de cursos está operativa.")
async def chequear_salud_api_config_curso():
    registrador.info("Chequeo de salud solicitado para la API de configuración de cursos.")
    return {"estado_api_config_curso": "saludable", "mensaje": "Servicio de configuración de cursos operativo."}

@enrutador_config_curso.get("/cursos-moodle",
                             response_model=List[modelos_api_traducidos.CursoMoodle],
                             summary="Listar Cursos Disponibles en Moodle",
                             description="Obtiene una lista de cursos de Moodle. Si no se especifica 'id_usuario_moodle', se utiliza el ID del profesor por defecto configurado en el servidor para buscar sus cursos. Si aun así no se encuentran o no hay ID por defecto, podría intentar listar todos los cursos (comportamiento a definir).")
async def obtener_cursos_de_moodle(
    id_usuario_moodle: Optional[int] = Query(None, description="ID de Usuario de Moodle (profesor) para filtrar los cursos.", alias="idUsuarioMoodle"),
    cliente_moodle: ClienteMoodle = Depends(dependencia_cliente_moodle)
):
    id_profesor_para_consulta = id_usuario_moodle if id_usuario_moodle is not None else configuracion_global.moodle.id_profesor_defecto

    if id_profesor_para_consulta is None:
        registrador.warning("No se proporcionó ID de profesor y el ID por defecto no está configurado. Se listarán todos los cursos.")
        # Alternativa: lanzar error si se requiere un ID de profesor.
        # raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Debe proporcionar un ID de profesor o configurar uno por defecto en el servidor.")
        try:
            registrador.info("Obteniendo todos los cursos disponibles de Moodle.")
            cursos = cliente_moodle.obtener_todos_los_cursos_disponibles() # Método refactorizado
            return cursos
        except ErrorAPIMoodle as e_moodle_api:
            registrador.error(f"Error de API Moodle al obtener todos los cursos: {e_moodle_api}")
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Error de API Moodle al obtener todos los cursos: {str(e_moodle_api)}")
        except Exception as e_inesperado:
            registrador.exception(f"Error inesperado obteniendo todos los cursos de Moodle: {e_inesperado}")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error interno del servidor al obtener todos los cursos: {str(e_inesperado)}")


    registrador.info(f"Obteniendo cursos de Moodle para el ID de profesor: {id_profesor_para_consulta}.")
    try:
        cursos = cliente_moodle.obtener_cursos_de_usuario(id_usuario=id_profesor_para_consulta) # Método refactorizado
        return cursos
    except ErrorAPIMoodle as e_moodle_api:
        registrador.error(f"Error de API Moodle al obtener cursos para el usuario {id_profesor_para_consulta}: {e_moodle_api}")
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Error de API Moodle: {str(e_moodle_api)}")
    except Exception as e_inesperado:
        registrador.exception(f"Error inesperado obteniendo cursos de Moodle para el usuario {id_profesor_para_consulta}: {e_inesperado}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error interno del servidor: {str(e_inesperado)}")


@enrutador_config_curso.post("/cursos/{id_curso}/configurar-inteligencia-artificial",
                              response_model=modelos_api_traducidos.RespuestaConfiguracionCurso,
                              summary="Configurar o Reconfigurar la Inteligencia Artificial para un Curso",
                              description="Establece o actualiza la configuración de IA para un curso específico. Esto incluye la creación/verificación de una tabla vectorial, la configuración de un flujo de chat en N8N, y la creación/actualización de los elementos necesarios en Moodle (sección, carpeta, enlaces).")
async def configurar_inteligencia_artificial_curso(
    peticion_http: Request, # Necesario para construir URLs absolutas para los enlaces en Moodle
    id_curso: int = Path(..., description="ID numérico del curso de Moodle a configurar."),
    nombre_curso_parametro: Optional[str] = Query(None, alias="nombreCurso", description="Nombre del curso para la IA (opcional; si no se provee, se intentará obtener de Moodle)."),
    # Parámetros para personalizar el chat N8N (opcionales)
    mensajes_bienvenida_chat: Optional[str] = Query(None, alias="mensajesBienvenida", description="Mensajes iniciales personalizados para el chat de IA (formato JSON string o texto plano)."),
    anexo_mensaje_sistema_agente: Optional[str] = Query(None, alias="anexoMensajeSistema", description="Texto adicional para el mensaje de sistema del agente IA en N8N."),
    placeholder_entrada_chat_usuario: Optional[str] = Query(None, alias="placeholderEntrada", description="Texto de ejemplo o placeholder para el campo de entrada del chat."),
    titulo_ventana_chat_ia: Optional[str] = Query(None, alias="tituloChat", description="Título personalizado para la ventana del chat de IA."),
    # Inyección de dependencias de los clientes y servicios del núcleo
    cliente_moodle: ClienteMoodle = Depends(dependencia_cliente_moodle),
    envoltorio_bd_pgvector: EnvoltorioPgVector = Depends(dependencia_envoltorio_pgvector),
    cliente_n8n: ClienteN8N = Depends(dependencia_cliente_n8n),
    proveedor_ia: ProveedorInteligencia = Depends(dependencia_proveedor_inteligencia)
):
    registrador.info(f"Recibida solicitud para configurar IA para el curso ID: {id_curso}.")

    nombre_curso_para_usar = nombre_curso_parametro or await _aux_obtener_nombre_curso(id_curso, cliente_moodle)
    if not nombre_curso_para_usar: # Seguridad adicional, aunque _aux_obtener_nombre_curso debería lanzar excepción
        registrador.critical(f"El nombre del curso para el ID {id_curso} no pudo ser determinado. No se puede continuar.")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"No se pudo determinar el nombre del curso {id_curso} para la configuración.")

    nombre_tabla_pgvector_curso = envoltorio_bd_pgvector.obtener_nombre_tabla_para_curso(nombre_curso_para_usar) # Método refactorizado
    dimension_vector_ia = configuracion_global.db.dimension_embedding_defecto # CAMBIADO # Asumir tamaño por defecto; podría ser dinámico basado en proveedor_ia.modelo_embedding

    respuesta_config = modelos_api_traducidos.RespuestaConfiguracionCurso(
        id_curso=id_curso,
        estado_operacion="pendiente", # Estado inicial
        mensaje_informativo=f"Configuración de IA iniciada para el curso ID {id_curso} ('{nombre_curso_para_usar}').",
        nombre_tabla_vectorial_curso=nombre_tabla_pgvector_curso
    )

    try:
        # 1. Asegurar tabla en PGVector
        if not envoltorio_bd_pgvector.asegurar_existencia_tabla_curso(nombre_curso_para_usar, dimension_vector_ia): # Método refactorizado
            raise ErrorBaseDeDatosVectorial(f"Falló la creación o verificación de la tabla PgVector '{nombre_tabla_pgvector_curso}'.")
        registrador.info(f"Tabla PgVector '{nombre_tabla_pgvector_curso}' asegurada para el curso '{nombre_curso_para_usar}'.")

        # 2. Obtener configuración de chat existente de Moodle (si existe)
        config_chat_existente_moodle = cliente_moodle.obtener_configuracion_n8n_del_curso(id_curso) or {} # Método refactorizado

        # 3. Determinar configuración final del chat (priorizando parámetros de la petición)
        # Usar el modelo Pydantic para validación y estructura
        config_chat_api = modelos_api_traducidos.ConfiguracionChatN8NUsuario(
            mensajes_iniciales=mensajes_bienvenida_chat or config_chat_existente_moodle.get("initial_message"),
            mensaje_sistema=anexo_mensaje_sistema_agente or config_chat_existente_moodle.get("system_message_append"), # Alias 'mensaje_sistema' mapea a 'mensaje_sistema_personalizado'
            placeholder_entrada=placeholder_entrada_chat_usuario or config_chat_existente_moodle.get("input_placeholder"),
            titulo_chat=titulo_ventana_chat_ia or config_chat_existente_moodle.get("chat_title")
        )

        # 4. Configurar y desplegar flujo de N8N
        nombre_proveedor_activo = proveedor_ia.nombre_proveedor_ia_configurado
        registrador.debug(f"Proveedor de IA activo para N8N: {nombre_proveedor_activo}")

        url_chat_n8n_string = cliente_n8n.configurar_y_desplegar_flujo_de_chat_para_curso( # Método refactorizado
            id_curso=id_curso, nombre_curso=nombre_curso_para_usar,
            nombre_coleccion_pgvector=nombre_tabla_pgvector_curso,
            proveedor_ia_seleccionado=nombre_proveedor_activo, # Pasar el string del proveedor
            config_ollama=configuracion_global.ollama if nombre_proveedor_activo == "ollama" else None,
            config_gemini=configuracion_global.gemini if nombre_proveedor_activo == "gemini" else None,
            mensajes_iniciales_chat=config_chat_api.mensajes_iniciales,
            mensaje_sistema_agente_ia=config_chat_api.mensaje_sistema_personalizado, # Usar el campo correcto del modelo
            placeholder_entrada_chat=config_chat_api.placeholder_entrada_chat, # Usar el campo correcto
            titulo_ventana_chat=config_chat_api.titulo_ventana_chat # Usar el campo correcto
        )
        respuesta_config.url_chat_n8n_curso = HttpUrl(url_chat_n8n_string) if url_chat_n8n_string else None
        registrador.info(f"URL del chat N8N para '{nombre_curso_para_usar}': {respuesta_config.url_chat_n8n_curso}")
        if not respuesta_config.url_chat_n8n_curso:
             registrador.warning(f"No se pudo obtener una URL de chat N8N para el curso {id_curso}.")
             # Considerar si esto es un error fatal o se puede continuar sin el enlace del chat.

        # 5. Crear/actualizar elementos en Moodle (sección, carpeta, URLs)
        nombre_seccion_entrenai_moodle = configuracion_global.moodle.nombre_carpeta_recursos_ia # CAMBIADO # Ej: "EntrenAI - Recursos IA"
        seccion_entrenai = cliente_moodle.asegurar_seccion_curso(id_curso, nombre_seccion_entrenai_moodle) # Método refactorizado
        if not seccion_entrenai or not seccion_entrenai.id:
            raise ErrorAPIMoodle(f"Falló la creación o aseguramiento de la sección '{nombre_seccion_entrenai_moodle}' en Moodle para el curso {id_curso}.")
        respuesta_config.id_seccion_moodle_entrenai = seccion_entrenai.id

        # Construir URLs para los enlaces en Moodle
        url_base_api_absoluta = str(peticion_http.base_url).rstrip("/")
        # Asumiendo que la UI para gestionar archivos está en una ruta relativa al frontend/base_url
        # TODO: Esta URL de UI debe ser configurable o construirse de forma más robusta.
        url_interfaz_gestion_archivos = f"{url_base_api_absoluta}/frontend/gestor_archivos.html?id_curso={id_curso}" # Ejemplo placeholder

        # El nombre de la función para url_path_for debe ser el nombre de la función del endpoint.
        # Si 'solicitar_refresco_archivos_curso' es el nombre de la función Python, está bien.
        ruta_api_refresco = enrutador_config_curso.url_path_for("solicitar_refresco_archivos_curso", id_curso=id_curso)
        url_absoluta_refresco_api = f"{url_base_api_absoluta}{ruta_api_refresco}"

        sumario_html_seccion = f"""
<h4>Recursos de Inteligencia Artificial EntrenAI</h4>
<p>Utilice esta sección para interactuar con la Inteligencia Artificial de asistencia para este curso y gestionar sus fuentes de información.</p>
<ul>
    <li><a href="{respuesta_config.url_chat_n8n_curso if respuesta_config.url_chat_n8n_curso else '#'}" target="_blank">{configuracion_global.moodle.nombre_enlace_chat_ia}</a>: Acceda aquí para conversar con la IA del curso.</li> # CAMBIADO
    <li>Carpeta "<strong>{nombre_seccion_entrenai_moodle}</strong>": Deposite aquí los documentos (PDF, DOCX, TXT, etc.) que la IA utilizará como base de conocimiento.</li>
    <li><a href="{url_absoluta_refresco_api}" target="_blank">{configuracion_global.moodle.nombre_enlace_refrescar_ia}</a>: Haga clic en este enlace <strong>después de añadir, modificar o eliminar archivos</strong> en la carpeta para que la IA actualice su conocimiento.</li> # CAMBIADO
    <li><a href="{url_interfaz_gestion_archivos}" target="_blank">Gestionar Archivos Indexados (Interfaz de Usuario)</a> (Funcionalidad futura)</li>
</ul>
<p><strong>Nota para el profesor:</strong> Puede personalizar las interacciones del chat (mensajes de bienvenida, título, etc.) y el comportamiento específico del agente de IA contactando al administrador del sistema o, si está habilitado, a través de una interfaz de configuración avanzada para este curso.</p>
        """
        if not cliente_moodle.actualizar_sumario_de_seccion(id_curso, seccion_entrenai.id, sumario_html_seccion): # Método refactorizado
            registrador.warning(f"No se pudo actualizar el sumario de la sección {seccion_entrenai.id} para el curso {id_curso}.")

        # Crear carpeta con el mismo nombre que la sección para consistencia
        modulo_carpeta = cliente_moodle.crear_carpeta_en_seccion(id_curso, seccion_entrenai.id, nombre_seccion_entrenai_moodle) # Método refactorizado
        if modulo_carpeta: respuesta_config.id_carpeta_moodle_entrenai = modulo_carpeta.id

        if respuesta_config.url_chat_n8n_curso:
            modulo_chat_url = cliente_moodle.crear_url_en_seccion(id_curso, seccion_entrenai.id, configuracion_global.moodle.nombre_enlace_chat_ia, str(respuesta_config.url_chat_n8n_curso)) # CAMBIADO # Método refactorizado
            if modulo_chat_url: respuesta_config.id_chat_moodle_entrenai = modulo_chat_url.id

        modulo_refresco_url = cliente_moodle.crear_url_en_seccion(id_curso, seccion_entrenai.id, configuracion_global.moodle.nombre_enlace_refrescar_ia, url_absoluta_refresco_api) # CAMBIADO # Método refactorizado
        if modulo_refresco_url: respuesta_config.id_enlace_refresco_moodle_entrenai = modulo_refresco_url.id

        respuesta_config.estado_operacion = "exitoso"
        respuesta_config.mensaje_informativo = f"Configuración de EntrenAI completada exitosamente para el curso {id_curso} ('{nombre_curso_para_usar}')."
        registrador.info(respuesta_config.mensaje_informativo)
        return respuesta_config

    except HTTPException as e_http: # Re-lanzar HTTPExceptions controladas
        raise e_http
    except (ErrorAPIMoodle, ErrorBaseDeDatosVectorial, ErrorClienteN8N, ErrorProveedorInteligencia) as e_servicio_nucleo:
        registrador.error(f"Error de un servicio del núcleo durante la configuración de IA para el curso {id_curso}: {e_servicio_nucleo}")
        # respuesta_config ya tiene valores iniciales, actualizamos solo estado y mensaje
        respuesta_config.estado_operacion = "fallido"
        respuesta_config.mensaje_informativo = f"Error de servicio del núcleo: {str(e_servicio_nucleo)}"
        # Devolver la respuesta parcial con el error en lugar de solo HTTPException para dar más contexto.
        # Opcionalmente, se podría lanzar HTTPException(status_code=502 o 503, detail=respuesta_config.model_dump_json())
        # Por ahora, se lanza HTTPException con el mensaje del error.
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=respuesta_config.mensaje_informativo)
    except Exception as e_inesperado_config:
        registrador.exception(f"Error inesperado durante la configuración de IA para el curso {id_curso}: {e_inesperado_config}")
        respuesta_config.estado_operacion = "fallido"
        respuesta_config.mensaje_informativo = f"Error interno del servidor durante la configuración: {str(e_inesperado_config)}"
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=respuesta_config.mensaje_informativo)


@enrutador_config_curso.post("/cursos/{id_curso}/refrescar-archivos", # Nombre de función Python es 'solicitar_refresco_archivos_curso'
                              summary="Solicitar Refresco/Procesamiento de Archivos del Curso",
                              description="Inicia el proceso asíncrono de escaneo y procesamiento de archivos para un curso específico. Esta operación se ejecuta en segundo plano y se registra una tarea Celery.")
async def solicitar_refresco_archivos_curso(id_curso: int): # Nombre de función para url_path_for
    # Usar un ID de usuario por defecto o uno específico si la lógica lo permitiera.
    id_usuario_solicitante_defecto = configuracion_global.moodle.id_profesor_defecto
    if id_usuario_solicitante_defecto is None:
        registrador.error("ID de profesor por defecto (para tareas asíncronas) no configurado en el servidor.")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="La configuración del servidor no permite iniciar esta tarea (falta ID de usuario por defecto).")

    registrador.info(f"Solicitud para iniciar refresco de archivos para curso ID: {id_curso}, por usuario ID: {id_usuario_solicitante_defecto}")
    try:
        # Despachar la tarea Celery. 'delegar_procesamiento_curso' es el nombre de la tarea importada.
        resultado_tarea_celery = delegar_procesamiento_curso.delay(id_curso=id_curso, id_usuario=id_usuario_solicitante_defecto)
        id_tarea_despachada = resultado_tarea_celery.id

        registrador.info(f"Tarea Celery '{id_tarea_despachada}' despachada para procesar archivos del curso ID: {id_curso}")
        return {"id_tarea": id_tarea_despachada, "mensaje": f"Procesamiento de archivos para el curso {id_curso} ha sido iniciado en segundo plano. ID de tarea: {id_tarea_despachada}."}
    except Exception as e_celery: # Capturar errores al intentar encolar la tarea
        registrador.exception(f"Error al despachar la tarea Celery para el procesamiento del curso {id_curso}: {e_celery}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error interno del servidor al intentar iniciar la tarea de procesamiento de archivos.")


@enrutador_config_curso.get("/tareas/{id_tarea}/estado",
                             response_model=modelos_api_traducidos.RespuestaEstadoTareaAsincrona, # Usar modelo traducido
                             summary="Consultar Estado de Tarea Asíncrona (Celery)",
                             description="Consulta y devuelve el estado actual de una tarea Celery específica, identificada por su ID.")
async def consultar_estado_tarea_asincrona(id_tarea: str): # Nombre de función traducido
    registrador.debug(f"Consultando estado para la tarea Celery con ID: {id_tarea}")
    resultado_asincrono_celery = AsyncResult(id_tarea, app=aplicacion_celery)

    # Mapear el resultado de Celery al modelo Pydantic de respuesta.
    respuesta_estado_api = modelos_api_traducidos.RespuestaEstadoTareaAsincrona(
        id_tarea=id_tarea,
        estado_tarea=resultado_asincrono_celery.status, # Estado: PENDING, STARTED, SUCCESS, FAILURE, RETRY, REVOKED
        resultado_tarea=resultado_asincrono_celery.result if resultado_asincrono_celery.successful() else None,
        info_error_tarea=resultado_asincrono_celery.traceback if resultado_asincrono_celery.failed() else None
    )
    # Si la tarea falló, el resultado podría contener la excepción. Convertirlo a string para JSON.
    if resultado_asincrono_celery.failed() and respuesta_estado_api.resultado_tarea is None:
        respuesta_estado_api.resultado_tarea = str(resultado_asincrono_celery.result)

    registrador.debug(f"Estado de la tarea {id_tarea}: {respuesta_estado_api.model_dump_json(indent=2)}")
    return respuesta_estado_api

@enrutador_config_curso.get("/cursos/{id_curso}/archivos-procesados", # Renombrado de "archivos-indexados"
                             response_model=List[modelos_api_traducidos.ArchivoProcesadoInfo], # Usar modelo traducido
                             summary="Listar Archivos Procesados e Indexados de un Curso",
                             description="Obtiene una lista de los archivos que han sido procesados e incorporados a la base de conocimiento de IA para un curso específico.")
async def obtener_archivos_procesados_del_curso( # Nombre de función traducido
    id_curso: int,
    envoltorio_bd_pgvector: EnvoltorioPgVector = Depends(dependencia_envoltorio_pgvector)
):
    registrador.info(f"Solicitud para obtener la lista de archivos procesados para el curso ID: {id_curso}")
    try:
        # El método refactorizado en EnvoltorioPgVector es 'obtener_marcas_de_tiempo_archivos_procesados_curso'
        marcas_de_tiempo_archivos = envoltorio_bd_pgvector.obtener_marcas_de_tiempo_archivos_procesados_curso(id_curso=id_curso)

        if not marcas_de_tiempo_archivos: # Devuelve dict vacío si no hay archivos o si ocurre un error manejado internamente
            registrador.info(f"No se encontraron archivos procesados registrados para el curso ID: {id_curso}.")
            return [] # Devolver lista vacía es apropiado

        archivos_procesados_respuesta = [
            modelos_api_traducidos.ArchivoProcesadoInfo(nombre_archivo=identificador_archivo, timestamp_ultima_modificacion=timestamp_modificacion)
            for identificador_archivo, timestamp_modificacion in marcas_de_tiempo_archivos.items()
        ]
        registrador.info(f"Encontrados {len(archivos_procesados_respuesta)} archivos procesados para el curso ID: {id_curso}.")
        return archivos_procesados_respuesta
    except ErrorBaseDeDatosVectorial as e_bd_vec:
        registrador.error(f"Error de base de datos al obtener archivos procesados para el curso {id_curso}: {e_bd_vec}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error de acceso a la base de datos al listar archivos procesados: {str(e_bd_vec)}")
    except Exception as e_inesperado:
        registrador.exception(f"Error inesperado al obtener archivos procesados para el curso {id_curso}: {e_inesperado}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error interno del servidor al listar archivos procesados.")


@enrutador_config_curso.delete("/cursos/{id_curso}/archivos-procesados/{identificador_archivo:path}", # Renombrado
                                response_model=modelos_api_traducidos.RespuestaEliminacionArchivo, # Usar modelo traducido
                                summary="Eliminar Archivo Procesado y sus Datos Asociados",
                                description="Elimina un archivo específico de la base de conocimiento de IA, incluyendo sus fragmentos vectoriales y su registro de seguimiento.")
async def eliminar_archivo_procesado_del_curso( # Nombre de función traducido
    id_curso: int,
    identificador_archivo: str, # FastAPI decodifica automáticamente el path param (ej. nombre de archivo)
    cliente_moodle: ClienteMoodle = Depends(dependencia_cliente_moodle), # Necesario para obtener el nombre del curso para la tabla
    envoltorio_bd_pgvector: EnvoltorioPgVector = Depends(dependencia_envoltorio_pgvector)
):
    registrador.info(f"Solicitud para eliminar el archivo '{identificador_archivo}' y sus datos asociados del curso ID: {id_curso}.")
    try:
        # Obtener el nombre del curso para construir el nombre de la tabla donde están los fragmentos.
        nombre_curso_actual = await _aux_obtener_nombre_curso(id_curso, cliente_moodle)

        registrador.info(f"Procediendo a eliminar fragmentos para el documento ID (identificador archivo) '{identificador_archivo}' de la tabla del curso '{nombre_curso_actual}'.")
        # El método refactorizado es 'eliminar_fragmentos_por_id_documento'
        exito_eliminacion_fragmentos = envoltorio_bd_pgvector.eliminar_fragmentos_por_id_documento(nombre_curso_actual, identificador_archivo)

        registrador.info(f"Procediendo a eliminar el archivo '{identificador_archivo}' (curso {id_curso}) de la tabla de seguimiento de archivos.")
        # El método refactorizado es 'eliminar_registro_de_archivo_en_seguimiento'
        exito_eliminacion_seguimiento = envoltorio_bd_pgvector.eliminar_registro_de_archivo_en_seguimiento(id_curso, identificador_archivo)

        if exito_eliminacion_fragmentos and exito_eliminacion_seguimiento:
            mensaje_exito = f"El archivo '{identificador_archivo}' y todos sus datos asociados han sido eliminados exitosamente para el curso {id_curso} ('{nombre_curso_actual}')."
            registrador.info(mensaje_exito)
            return modelos_api_traducidos.RespuestaEliminacionArchivo(mensaje=mensaje_exito)
        else:
            detalle_fallo = f"Resultado de eliminación de fragmentos vectoriales: {'éxito' if exito_eliminacion_fragmentos else 'fallo/no encontrado'}. Resultado de eliminación de registro de seguimiento: {'éxito' if exito_eliminacion_seguimiento else 'fallo/no encontrado'}."
            registrador.error(f"Falló la eliminación completa de los datos del archivo '{identificador_archivo}' para el curso {id_curso}. {detalle_fallo}")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error al eliminar completamente los datos del archivo. {detalle_fallo}")

    except HTTPException: # Re-lanzar HTTPExceptions (ej. de _aux_obtener_nombre_curso si el curso no se encuentra)
        raise
    except ErrorBaseDeDatosVectorial as e_bd: # Errores específicos de la BD no cubiertos arriba
        registrador.error(f"Error de BD eliminando archivo '{identificador_archivo}' para curso {id_curso}: {e_bd}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error de base de datos al eliminar archivo: {str(e_bd)}")
    except Exception as e_inesperado:
        registrador.exception(f"Error inesperado al eliminar el archivo '{identificador_archivo}' para el curso {id_curso}: {e_inesperado}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error interno del servidor durante la eliminación del archivo: {str(e_inesperado)}")


@enrutador_config_curso.get("/cursos/{id_curso}/configuracion-chat", # Ruta simplificada
                             response_model=modelos_api_traducidos.ConfiguracionChatN8NUsuario, # Usar modelo traducido
                             summary="Obtener Configuración Actual del Chat N8N para un Curso",
                             description="Recupera la configuración actual del flujo de chat de N8N asociado a un curso, como los mensajes iniciales, título, y mensaje de sistema del agente IA (si es posible extraerlos).")
async def obtener_configuracion_actual_chat_n8n_curso( # Nombre de función traducido
    id_curso: int,
    cliente_moodle: ClienteMoodle = Depends(dependencia_cliente_moodle), # Para obtener nombre del curso
    cliente_n8n: ClienteN8N = Depends(dependencia_cliente_n8n)
):
    registrador.info(f"Solicitud para obtener la configuración del chat N8N para el curso ID: {id_curso}.")
    try:
        # Obtener el nombre del curso para identificar el flujo de N8N.
        nombre_curso_actual = await _aux_obtener_nombre_curso(id_curso, cliente_moodle)
        # El nombre del flujo en N8N se construye de una forma específica.
        nombre_flujo_n8n_esperado = f"EntrenAI Chat - Curso: {nombre_curso_actual} (ID: {id_curso})"
        registrador.debug(f"Buscando flujo de N8N con nombre esperado: '{nombre_flujo_n8n_esperado}'.")

        # Obtener todos los flujos y buscar el que coincida.
        lista_flujos_n8n = cliente_n8n.obtener_lista_de_flujos_de_trabajo() # Método refactorizado
        flujo_objetivo_encontrado = next((flujo for flujo in lista_flujos_n8n if flujo.name == nombre_flujo_n8n_esperado and flujo.active), None)

        # Fallback: si no se encuentra por nombre exacto, buscar uno activo que empiece con el prefijo del curso.
        if not flujo_objetivo_encontrado:
            registrador.debug(f"No se encontró flujo por nombre exacto. Buscando por prefijo 'EntrenAI Chat - Curso: ... (ID: {id_curso})' y activo.")
            flujo_objetivo_encontrado = next((flujo for flujo in lista_flujos_n8n if flujo.name and flujo.name.startswith(f"EntrenAI Chat - Curso: ") and f"(ID: {id_curso})" in flujo.name and flujo.active), None)

        if not flujo_objetivo_encontrado or not flujo_objetivo_encontrado.id: # Asegurar que el ID del flujo exista
            registrador.warning(f"No se encontró un flujo de N8N activo y correspondiente para el curso {id_curso} (nombre esperado: '{nombre_flujo_n8n_esperado}').")
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"No se encontró un flujo de N8N activo y configurado para el curso {id_curso}.")

        registrador.info(f"Flujo N8N encontrado para el curso {id_curso}: '{flujo_objetivo_encontrado.name}' (ID: {flujo_objetivo_encontrado.id}). Obteniendo detalles...")
        detalles_completos_flujo = cliente_n8n.obtener_detalles_de_flujo_de_trabajo(flujo_objetivo_encontrado.id) # Método refactorizado
        if not detalles_completos_flujo:
            registrador.error(f"No se pudieron obtener los detalles completos del flujo de N8N con ID '{flujo_objetivo_encontrado.id}'.")
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"No se pudieron obtener los detalles del flujo de N8N ID '{flujo_objetivo_encontrado.id}'.")

        # Extraer la configuración relevante de los nodos del flujo.
        config_chat_extraida = modelos_api_traducidos.ConfiguracionChatN8NUsuario() # Inicializar con valores por defecto
        for nodo_flujo in detalles_completos_flujo.nodes:
            if nodo_flujo.type == "@n8n/n8n-nodes-langchain.chatTrigger" and nodo_flujo.parameters:
                config_chat_extraida.mensajes_iniciales = nodo_flujo.parameters.initialMessages
                if nodo_flujo.parameters.options:
                    config_chat_extraida.placeholder_entrada_chat = nodo_flujo.parameters.options.get("inputPlaceholder")
                    config_chat_extraida.titulo_ventana_chat = nodo_flujo.parameters.options.get("title")
            elif nodo_flujo.type == "@n8n/n8n-nodes-langchain.agent" and nodo_flujo.parameters and nodo_flujo.parameters.options:
                # El alias en el modelo Pydantic se encarga de mapear 'mensaje_sistema' a 'mensaje_sistema_personalizado'.
                config_chat_extraida.mensaje_sistema_personalizado = nodo_flujo.parameters.options.get("systemMessage")

        registrador.info(f"Configuración de chat N8N extraída para el curso {id_curso}: {config_chat_extraida.model_dump_json(exclude_none=True)}")
        return config_chat_extraida

    except HTTPException: # Re-lanzar HTTPExceptions (ej. 404)
        raise
    except ErrorClienteN8N as e_n8n_cliente:
        registrador.error(f"Error del cliente N8N al obtener configuración para el curso {id_curso}: {e_n8n_cliente}")
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Error de comunicación con N8N: {str(e_n8n_cliente)}")
    except Exception as e_inesperado:
        registrador.exception(f"Error inesperado al obtener la configuración del chat N8N para el curso {id_curso}: {e_inesperado}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error interno del servidor: {str(e_inesperado)}")

[end of entrenai_refactor/api/rutas/ruta_configuracion_curso.py]
