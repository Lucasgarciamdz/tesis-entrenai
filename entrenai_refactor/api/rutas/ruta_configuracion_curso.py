import json # No parece usarse json directamente aquí, pero es común en APIs. Se puede quitar si no es necesario.
from pathlib import Path
from typing import List, Optional, Dict, Any # Dict y Any no se usan directamente, pero podrían ser útiles para extensiones futuras.

from fastapi import APIRouter, HTTPException, Query, Depends, Request, status, Path as FastAPIPath # Path renombrado para evitar colisión con pathlib.Path
from celery.result import AsyncResult # Para consultar resultados de tareas Celery

# Importar modelos Pydantic refactorizados
from entrenai_refactor.api import modelos as modelos_api
# Importar clases refactorizadas del núcleo
from entrenai_refactor.nucleo.clientes import ClienteMoodle, ErrorAPIMoodle
from entrenai_refactor.nucleo.clientes import ClienteN8N, ErrorClienteN8N
from entrenai_refactor.nucleo.bd import EnvoltorioPgVector, ErrorBaseDeDatosVectorial
from entrenai_refactor.nucleo.ia import ProveedorInteligencia, ErrorProveedorInteligencia
# Celery y tareas (asumiendo que los nombres de tareas también podrían ser refactorizados si es necesario)
from entrenai_refactor.celery.aplicacion_celery import aplicacion_celery_instancia # Nombre de instancia de app Celery refactorizado
from entrenai_refactor.celery.tareas import tarea_delegar_procesamiento_curso # Nombre de tarea Celery refactorizado
# Configuración y logging
from entrenai_refactor.config.configuracion import configuracion_global
from entrenai_refactor.config.registrador import obtener_registrador

registrador = obtener_registrador(__name__)

enrutador_config_curso = APIRouter(
    prefix="/v1/cursos", # Prefijo común para los endpoints de configuración de cursos
    tags=["Configuración de Cursos y Gestión de IA para Cursos"], # Etiqueta para OpenAPI
)

# --- Funciones de Dependencia (Inyección de Dependencias de FastAPI) ---
# Estas funciones proveen instancias de los clientes y servicios del núcleo a los endpoints.

def obtener_dependencia_cliente_moodle() -> ClienteMoodle: # Nombre más explícito
    """Dependencia para obtener una instancia del ClienteMoodle. Maneja errores de inicialización."""
    try:
        return ClienteMoodle()
    except ErrorAPIMoodle as e_moodle:
        registrador.error(f"Error específico al crear instancia de ClienteMoodle: {e_moodle}")
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"No se pudo conectar o inicializar el cliente de Moodle: {str(e_moodle)}")
    except Exception as e_inesperado:
        registrador.exception(f"Error inesperado al crear instancia de ClienteMoodle: {e_inesperado}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error interno del servidor al configurar la conexión con Moodle.")

def obtener_dependencia_envoltorio_pgvector() -> EnvoltorioPgVector: # Nombre más explícito
    """Dependencia para obtener una instancia del EnvoltorioPgVector. Maneja errores."""
    try:
        return EnvoltorioPgVector()
    except ErrorBaseDeDatosVectorial as e_bd_vec:
        registrador.error(f"Error específico al crear instancia de EnvoltorioPgVector: {e_bd_vec}")
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"No se pudo conectar o inicializar la base de datos vectorial: {str(e_bd_vec)}")
    except Exception as e_inesperado:
        registrador.exception(f"Error inesperado al crear instancia de EnvoltorioPgVector: {e_inesperado}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error interno del servidor al configurar el acceso a la base de datos vectorial.")

def obtener_dependencia_cliente_n8n() -> ClienteN8N: # Nombre más explícito
    """Dependencia para obtener una instancia del ClienteN8N. Maneja errores."""
    try:
        return ClienteN8N()
    except ErrorClienteN8N as e_n8n:
        registrador.error(f"Error específico al crear instancia de ClienteN8N: {e_n8n}")
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"No se pudo conectar o inicializar el cliente de N8N: {str(e_n8n)}")
    except Exception as e_inesperado:
        registrador.exception(f"Error inesperado al crear instancia de ClienteN8N: {e_inesperado}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error interno del servidor al configurar la conexión con N8N.")

def obtener_dependencia_proveedor_inteligencia() -> ProveedorInteligencia: # Nombre más explícito
    """Dependencia para obtener una instancia del ProveedorInteligencia. Maneja errores."""
    try:
        return ProveedorInteligencia()
    except ErrorProveedorInteligencia as e_prov_ia:
        registrador.error(f"Error específico al crear instancia de ProveedorInteligencia: {e_prov_ia}")
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"No se pudo inicializar el proveedor de IA configurado: {str(e_prov_ia)}")
    except Exception as e_inesperado:
        registrador.exception(f"Error inesperado al crear instancia de ProveedorInteligencia: {e_inesperado}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error interno del servidor al configurar el proveedor de IA.")

# --- Función Auxiliar Interna ---
async def _obtener_nombre_curso_para_operaciones(id_curso: int, cliente_moodle: ClienteMoodle) -> str: # Nombre más explícito
    """
    Obtiene el nombre del curso para un id_curso dado. Este nombre se usa para
    nombrar tablas en la BD vectorial y flujos en N8N.
    Lanza HTTPException si el curso no se encuentra o hay errores.
    """
    nombre_curso_obtenido: Optional[str] = None
    registrador.debug(f"Función auxiliar: Obteniendo nombre del curso con ID {id_curso} desde Moodle.")
    try:
        # Intentar obtener el nombre del curso a través de los cursos del profesor por defecto, si está configurado.
        id_profesor_defecto_moodle = configuracion_global.moodle.id_profesor_por_defecto # Nombre de campo refactorizado
        if id_profesor_defecto_moodle:
            cursos_del_profesor = cliente_moodle.obtener_cursos_de_usuario(id_usuario=id_profesor_defecto_moodle)
            curso_encontrado_via_profesor = next((c for c in cursos_del_profesor if c.id == id_curso), None)
            if curso_encontrado_via_profesor:
                nombre_curso_obtenido = curso_encontrado_via_profesor.nombre_a_mostrar or curso_encontrado_via_profesor.nombre_completo

        # Si no se encontró por profesor o no hay profesor por defecto, buscar en todos los cursos.
        if not nombre_curso_obtenido:
            todos_los_cursos_instancia_moodle = cliente_moodle.obtener_todos_los_cursos_disponibles()
            curso_encontrado_en_todos = next((c for c in todos_los_cursos_instancia_moodle if c.id == id_curso), None)
            if curso_encontrado_en_todos:
                nombre_curso_obtenido = curso_encontrado_en_todos.nombre_a_mostrar or curso_encontrado_en_todos.nombre_completo

        if not nombre_curso_obtenido:
            registrador.warning(f"No se pudo encontrar el curso con ID {id_curso} en Moodle para obtener su nombre.")
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"El curso con ID {id_curso} no fue encontrado en la instancia de Moodle.")

        registrador.info(f"Nombre del curso ID {id_curso} obtenido de Moodle para operaciones: '{nombre_curso_obtenido}'.")
        return nombre_curso_obtenido
    except ErrorAPIMoodle as e_error_api_moodle: # Error específico de la API de Moodle
        registrador.error(f"Error de API Moodle al intentar obtener el nombre del curso {id_curso}: {e_error_api_moodle}")
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Error de comunicación con Moodle al obtener el nombre del curso {id_curso}: {str(e_error_api_moodle)}")
    except HTTPException: # Re-lanzar HTTPExceptions (ej. 404 de arriba) para que FastAPI las maneje.
        raise
    except Exception as e_error_inesperado: # Otros errores no previstos
        registrador.exception(f"Error inesperado al obtener el nombre del curso {id_curso} desde Moodle: {e_error_inesperado}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"No se pudo determinar el nombre del curso {id_curso} debido a un error interno del servidor.")

# --- Endpoints de la API para Configuración de Cursos ---

@enrutador_config_curso.get("/estado-api", # Ruta en español
                             summary="Chequeo de Salud del Enrutador de Configuración de Cursos",
                             description="Endpoint simple para verificar que el enrutador de configuración de cursos IA está operativo y responde.")
async def chequear_estado_salud_enrutador_config_cursos(): # Nombre de función más descriptivo
    """Verifica la operatividad del enrutador de configuración de cursos."""
    registrador.info("Chequeo de salud solicitado para el enrutador de configuración de cursos.")
    return {"estado_enrutador_config_curso": "saludable", "mensaje": "El servicio de configuración de IA para cursos está operativo."}

@enrutador_config_curso.get("/moodle/cursos", # Ruta en español
                             response_model=List[modelos_api.CursoMoodle], # Usar modelo Pydantic refactorizado
                             summary="Listar Cursos Disponibles en Moodle",
                             description="Obtiene una lista de cursos desde Moodle. Si se especifica 'id_usuario_moodle', filtra los cursos para ese usuario (generalmente un profesor). Si no, intenta usar un ID de profesor por defecto configurado en el servidor. Como último recurso, podría listar todos los cursos disponibles en la instancia de Moodle.")
async def obtener_lista_cursos_moodle( # Nombre de función más descriptivo
    id_usuario_moodle: Optional[int] = Query(None, description="ID de Usuario de Moodle (ej. profesor) para filtrar los cursos a los que está asociado.", alias="idUsuarioMoodle"),
    cliente_moodle: ClienteMoodle = Depends(obtener_dependencia_cliente_moodle) # Inyección de dependencia
):
    """Obtiene y devuelve una lista de cursos desde Moodle, filtrada opcionalmente por ID de usuario."""
    id_profesor_consulta_moodle = id_usuario_moodle if id_usuario_moodle is not None else configuracion_global.moodle.id_profesor_por_defecto # Usar campo refactorizado

    if id_profesor_consulta_moodle is None:
        registrador.warning("No se proporcionó ID de profesor y el ID por defecto no está configurado. Se procederá a listar todos los cursos disponibles en Moodle.")
        try:
            registrador.info("Obteniendo todos los cursos disponibles de la instancia de Moodle.")
            cursos_moodle = cliente_moodle.obtener_todos_los_cursos_disponibles() # Método refactorizado
            return cursos_moodle
        except ErrorAPIMoodle as e_error_api_moodle_todos:
            registrador.error(f"Error de API Moodle al obtener todos los cursos: {e_error_api_moodle_todos}")
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Error de API Moodle al intentar obtener todos los cursos: {str(e_error_api_moodle_todos)}")
        except Exception as e_error_inesperado_todos:
            registrador.exception(f"Error inesperado obteniendo todos los cursos de Moodle: {e_error_inesperado_todos}")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error interno del servidor al obtener todos los cursos: {str(e_error_inesperado_todos)}")

    registrador.info(f"Obteniendo cursos de Moodle para el ID de profesor/usuario: {id_profesor_consulta_moodle}.")
    try:
        cursos_moodle_usuario = cliente_moodle.obtener_cursos_de_usuario(id_usuario=id_profesor_consulta_moodle) # Método refactorizado
        return cursos_moodle_usuario
    except ErrorAPIMoodle as e_error_api_moodle_usuario:
        registrador.error(f"Error de API Moodle al obtener cursos para el usuario {id_profesor_consulta_moodle}: {e_error_api_moodle_usuario}")
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Error de API Moodle al obtener cursos del usuario: {str(e_error_api_moodle_usuario)}")
    except Exception as e_error_inesperado_usuario:
        registrador.exception(f"Error inesperado obteniendo cursos de Moodle para el usuario {id_profesor_consulta_moodle}: {e_error_inesperado_usuario}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error interno del servidor al obtener cursos del usuario: {str(e_error_inesperado_usuario)}")


@enrutador_config_curso.post("/{id_curso}/configurar-ia", # Ruta en español, id_curso como path parameter
                              response_model=modelos_api.RespuestaConfiguracionCursoEntrenAI, # Modelo de respuesta refactorizado
                              summary="Configurar o Reconfigurar la Inteligencia Artificial para un Curso",
                              description="Establece o actualiza la configuración completa de la IA para un curso de Moodle específico. Esto incluye: la creación/verificación de una tabla dedicada en la base de datos vectorial (PGVector), la configuración y despliegue de un flujo de chat en N8N, y la creación/actualización de los elementos necesarios en Moodle (sección del curso, carpeta de recursos IA, enlaces al chat y a la función de refresco).")
async def configurar_inteligencia_artificial_para_curso( # Nombre de función más descriptivo
    peticion_http_actual: Request, # Necesario para construir URLs absolutas para los enlaces en Moodle, inyectado por FastAPI
    id_curso: int = FastAPIPath(..., description="ID numérico del curso de Moodle a configurar o reconfigurar."), # Path parameter
    nombre_curso_opcional: Optional[str] = Query(None, alias="nombreCurso", description="Nombre del curso para la IA (opcional; si no se provee, se intentará obtener de Moodle). Este nombre se usa para identificar recursos como la tabla vectorial o el flujo de N8N."), # Query parameter
    # Parámetros opcionales para personalizar el chat N8N
    mensajes_bienvenida_chat_n8n: Optional[str] = Query(None, alias="mensajesBienvenidaChat", description="Mensajes iniciales personalizados para el chat de IA (formato JSON string o texto plano). Sobrescribe configuraciones previas."),
    anexo_prompt_sistema_agente_n8n: Optional[str] = Query(None, alias="anexoPromptSistemaAgente", description="Texto adicional para el mensaje de sistema del agente IA en N8N. Se añade al prompt base."),
    placeholder_entrada_chat_n8n: Optional[str] = Query(None, alias="placeholderEntradaChat", description="Texto de ejemplo o placeholder para el campo de entrada del chat del usuario."),
    titulo_ventana_chat_n8n: Optional[str] = Query(None, alias="tituloVentanaChat", description="Título personalizado para la ventana o widget del chat de IA."),
    # Inyección de dependencias de los clientes y servicios del núcleo
    cliente_moodle: ClienteMoodle = Depends(obtener_dependencia_cliente_moodle),
    envoltorio_bd: EnvoltorioPgVector = Depends(obtener_dependencia_envoltorio_pgvector), # Renombrado para claridad local
    cliente_n8n: ClienteN8N = Depends(obtener_dependencia_cliente_n8n),
    proveedor_ia: ProveedorInteligencia = Depends(obtener_dependencia_proveedor_inteligencia)
):
    """Configura todos los componentes de EntrenAI para un curso específico."""
    registrador.info(f"Recibida solicitud para configurar IA para el curso ID: {id_curso}.")

    # Obtener el nombre del curso, necesario para varios componentes.
    nombre_curso_efectivo = nombre_curso_opcional or await _obtener_nombre_curso_para_operaciones(id_curso, cliente_moodle)
    if not nombre_curso_efectivo: # Seguridad adicional, aunque _obtener_nombre_curso_para_operaciones debería lanzar excepción
        registrador.critical(f"El nombre del curso para el ID {id_curso} no pudo ser determinado. No se puede continuar con la configuración.")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"No se pudo determinar el nombre del curso {id_curso} para la configuración. Operación abortada.")

    # Nombre de la tabla en PGVector para este curso.
    nombre_tabla_pgvector_curso_actual = envoltorio_bd.obtener_nombre_tabla_curso_normalizado(nombre_curso_efectivo) # Método refactorizado
    # Dimensión del vector de embeddings (debe coincidir con el modelo de IA usado).
    dimension_embeddings_configurada = configuracion_global.db.dimension_embedding_defecto # Campo refactorizado

    # Inicializar objeto de respuesta.
    respuesta_config_api = modelos_api.RespuestaConfiguracionCursoEntrenAI(
        id_curso=id_curso,
        estado_general_operacion="pendiente", # Estado inicial de la operación
        mensaje_informativo_operacion=f"Configuración de IA iniciada para el curso ID {id_curso} ('{nombre_curso_efectivo}').",
        nombre_tabla_vectorial_asignada_curso=nombre_tabla_pgvector_curso_actual
    )

    try:
        # Paso 1: Asegurar la existencia de la tabla en PGVector para el curso.
        if not envoltorio_bd.asegurar_existencia_tabla_curso(nombre_curso_efectivo, dimension_embeddings_configurada): # Método refactorizado
            raise ErrorBaseDeDatosVectorial(f"Falló la creación o verificación de la tabla PgVector '{nombre_tabla_pgvector_curso_actual}' para el curso.")
        registrador.info(f"Tabla PgVector '{nombre_tabla_pgvector_curso_actual}' asegurada para el curso '{nombre_curso_efectivo}'.")

        # Paso 2: Obtener configuración de chat existente de Moodle (si existe, a través de un plugin local).
        config_chat_moodle_actual = cliente_moodle.obtener_configuracion_n8n_de_curso(id_curso) or {} # Método refactorizado

        # Paso 3: Determinar configuración final del chat, priorizando parámetros de la petición API.
        # Usar el modelo Pydantic para validación y estructura de la configuración del chat.
        config_chat_api_final = modelos_api.ConfiguracionPersonalizadaChatN8N( # Modelo refactorizado
            mensajes_iniciales_chat=mensajes_bienvenida_chat_n8n or config_chat_moodle_actual.get("initial_message"), # Campo refactorizado
            mensaje_sistema_personalizado_ia=anexo_prompt_sistema_agente_n8n or config_chat_moodle_actual.get("system_message_append"), # Campo refactorizado
            placeholder_campo_entrada_chat=placeholder_entrada_chat_n8n or config_chat_moodle_actual.get("input_placeholder"), # Campo refactorizado
            titulo_ventana_chat=titulo_ventana_chat_n8n or config_chat_moodle_actual.get("chat_title") # Campo refactorizado
        )

        # Paso 4: Configurar y desplegar el flujo de N8N para el chat del curso.
        nombre_proveedor_ia_activo = proveedor_ia.nombre_proveedor_ia_configurado # Campo refactorizado
        registrador.debug(f"Proveedor de IA activo para la configuración del flujo N8N: '{nombre_proveedor_ia_activo}'.")

        url_chat_n8n_string_obtenida = cliente_n8n.configurar_y_desplegar_flujo_de_chat_para_curso( # Método refactorizado
            id_curso=id_curso, nombre_curso=nombre_curso_efectivo,
            nombre_coleccion_pgvector_curso=nombre_tabla_pgvector_curso_actual, # Nombre de tabla/colección
            proveedor_ia_configurado=nombre_proveedor_ia_activo, # String del proveedor
            config_ollama_proveedor=configuracion_global.ollama if nombre_proveedor_ia_activo == "ollama" else None, # Pasar config específica
            config_gemini_proveedor=configuracion_global.gemini if nombre_proveedor_ia_activo == "gemini" else None, # Pasar config específica
            mensajes_iniciales_chat=config_chat_api_final.mensajes_iniciales_chat, # Usar valor del modelo
            mensaje_sistema_agente_ia=config_chat_api_final.mensaje_sistema_personalizado_ia, # Usar valor del modelo
            placeholder_entrada_chat=config_chat_api_final.placeholder_campo_entrada_chat, # Usar valor del modelo
            titulo_ventana_chat=config_chat_api_final.titulo_ventana_chat # Usar valor del modelo
        )
        respuesta_config_api.url_chat_n8n_especifico_curso = HttpUrl(url_chat_n8n_string_obtenida) if url_chat_n8n_string_obtenida else None # Campo refactorizado
        registrador.info(f"URL del chat N8N para el curso '{nombre_curso_efectivo}': {respuesta_config_api.url_chat_n8n_especifico_curso}")
        if not respuesta_config_api.url_chat_n8n_especifico_curso:
             registrador.warning(f"No se pudo obtener una URL de chat N8N válida para el curso {id_curso}. El enlace en Moodle podría no funcionar.")
             # Considerar si esto es un error fatal o se puede continuar. Por ahora, se continúa.

        # Paso 5: Crear/actualizar los elementos necesarios en Moodle (sección, carpeta de recursos, enlaces URL).
        nombre_seccion_recursos_ia_moodle = configuracion_global.moodle.nombre_carpeta_recursos_ia # Nombre de la SECCIÓN, campo refactorizado
        seccion_recursos_ia_en_moodle = cliente_moodle.asegurar_seccion_curso(id_curso, nombre_seccion_recursos_ia_moodle) # Método refactorizado
        if not seccion_recursos_ia_en_moodle or not seccion_recursos_ia_en_moodle.id: # Verificar que la sección y su ID existan
            raise ErrorAPIMoodle(f"Falló la creación o aseguramiento de la sección '{nombre_seccion_recursos_ia_moodle}' en Moodle para el curso {id_curso}.")
        respuesta_config_api.id_seccion_entrenai_moodle = seccion_recursos_ia_en_moodle.id # Campo refactorizado

        # Construir URLs absolutas para los enlaces que se crearán en Moodle.
        url_base_api_absoluta_actual = str(peticion_http_actual.base_url).rstrip("/")

        # TODO: La URL para la interfaz de gestión de archivos es un placeholder.
        # Debería ser configurable o construirse de forma más robusta y dinámica.
        # Por ahora, se mantiene como un ejemplo conceptual.
        url_placeholder_interfaz_gestion_archivos = f"{url_base_api_absoluta_actual}/frontend/gestor_archivos_curso.html?id_curso={id_curso}"
        registrador.warning(f"URL para 'Gestionar Archivos Indexados' es un placeholder: {url_placeholder_interfaz_gestion_archivos}")

        # URL para el endpoint de refresco de archivos de este curso.
        # El nombre de la función para url_path_for debe ser el nombre de la función Python del endpoint.
        ruta_api_refresco_archivos = enrutador_config_curso.url_path_for("solicitar_refresco_archivos_de_curso", id_curso=id_curso) # Nombre de función refactorizado
        url_absoluta_api_refresco_archivos = f"{url_base_api_absoluta_actual}{ruta_api_refresco_archivos}"

        # Crear/actualizar el sumario (descripción) de la sección en Moodle con información y enlaces.
        sumario_html_seccion_moodle = f"""
<h4>Recursos de Inteligencia Artificial EntrenAI</h4>
<p>Utilice esta sección para interactuar con la Inteligencia Artificial de asistencia para este curso y gestionar sus fuentes de información.</p>
<ul>
    <li><a href="{respuesta_config_api.url_chat_n8n_especifico_curso if respuesta_config_api.url_chat_n8n_especifico_curso else '#'}" target="_blank">{configuracion_global.moodle.nombre_enlace_chat_ia}</a>: Acceda aquí para conversar con la IA del curso.</li>
    <li>Carpeta "<strong>{nombre_seccion_recursos_ia_moodle}</strong>": Deposite aquí los documentos (PDF, DOCX, TXT, etc.) que la IA utilizará como base de conocimiento. Es crucial que los archivos estén en esta carpeta para ser procesados.</li>
    <li><a href="{url_absoluta_api_refresco_archivos}" target="_blank">{configuracion_global.moodle.nombre_enlace_refrescar_ia}</a>: Haga clic en este enlace <strong>después de añadir, modificar o eliminar archivos</strong> en la carpeta de recursos para que la IA actualice su base de conocimiento. Este proceso puede tardar unos minutos.</li>
    <li><a href="{url_placeholder_interfaz_gestion_archivos}" target="_blank" title="Esta funcionalidad está en desarrollo y podría no estar disponible.">Gestionar Archivos Indexados (Interfaz de Usuario)</a> (Funcionalidad futura)</li>
</ul>
<p><strong>Nota para el profesor:</strong> Puede personalizar las interacciones del chat (mensajes de bienvenida, título, etc.) y el comportamiento específico del agente de IA contactando al administrador del sistema o, si está habilitado, a través de una interfaz de configuración avanzada para este curso.</p>
        """
        if not cliente_moodle.actualizar_sumario_de_seccion(id_curso, seccion_recursos_ia_en_moodle.id, sumario_html_seccion_moodle): # Método refactorizado
            registrador.warning(f"No se pudo actualizar el sumario de la sección {seccion_recursos_ia_en_moodle.id} para el curso {id_curso} en Moodle.")

        # Crear la carpeta de Moodle para los recursos de IA (si no existe).
        # El nombre de la carpeta podría ser el mismo que la sección para consistencia.
        modulo_carpeta_recursos_ia = cliente_moodle.crear_carpeta_en_seccion(id_curso, seccion_recursos_ia_en_moodle.id, nombre_seccion_recursos_ia_moodle) # Método refactorizado
        if modulo_carpeta_recursos_ia: respuesta_config_api.id_carpeta_recursos_ia_moodle = modulo_carpeta_recursos_ia.id # Campo refactorizado

        # Crear el enlace URL al chat de N8N en la sección de Moodle.
        if respuesta_config_api.url_chat_n8n_especifico_curso:
            modulo_enlace_chat_ia = cliente_moodle.crear_url_en_seccion(id_curso, seccion_recursos_ia_en_moodle.id, configuracion_global.moodle.nombre_enlace_chat_ia, str(respuesta_config_api.url_chat_n8n_especifico_curso)) # Método refactorizado
            if modulo_enlace_chat_ia: respuesta_config_api.id_enlace_chat_ia_moodle = modulo_enlace_chat_ia.id # Campo refactorizado

        # Crear el enlace URL para el refresco manual de la IA en la sección de Moodle.
        modulo_enlace_refresco_ia = cliente_moodle.crear_url_en_seccion(id_curso, seccion_recursos_ia_en_moodle.id, configuracion_global.moodle.nombre_enlace_refrescar_ia, url_absoluta_api_refresco_archivos) # Método refactorizado
        if modulo_enlace_refresco_ia: respuesta_config_api.id_enlace_refresco_manual_moodle = modulo_enlace_refresco_ia.id # Campo refactorizado

        # Actualizar estado final de la operación.
        respuesta_config_api.estado_general_operacion = "exitoso"
        respuesta_config_api.mensaje_informativo_operacion = f"Configuración de EntrenAI completada exitosamente para el curso {id_curso} ('{nombre_curso_efectivo}'). La IA está lista para ser alimentada con archivos."
        registrador.info(respuesta_config_api.mensaje_informativo_operacion)
        return respuesta_config_api

    except HTTPException as e_http_controlada: # Re-lanzar HTTPExceptions controladas (ej. 404, 502 de auxiliares)
        raise e_http_controlada
    except (ErrorAPIMoodle, ErrorBaseDeDatosVectorial, ErrorClienteN8N, ErrorProveedorInteligencia) as e_error_servicio_nucleo:
        registrador.error(f"Error de un servicio del núcleo durante la configuración de IA para el curso {id_curso}: {e_error_servicio_nucleo}")
        respuesta_config_api.estado_general_operacion = "fallido_parcialmente" # O "fallido_critico"
        respuesta_config_api.mensaje_informativo_operacion = f"Error de servicio del núcleo durante la configuración: {str(e_error_servicio_nucleo)}"
        # Se podría devolver la respuesta parcial con el error, o lanzar una HTTPException más genérica.
        # Lanzar HTTPException para informar al cliente del error de forma estándar.
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=respuesta_config_api.mensaje_informativo_operacion)
    except Exception as e_error_inesperado_config: # Capturar cualquier otra excepción no prevista
        registrador.exception(f"Error inesperado durante la configuración de IA para el curso {id_curso}: {e_error_inesperado_config}")
        respuesta_config_api.estado_general_operacion = "fallido_critico"
        respuesta_config_api.mensaje_informativo_operacion = f"Error interno del servidor durante la configuración del curso: {str(e_error_inesperado_config)}"
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=respuesta_config_api.mensaje_informativo_operacion)


@enrutador_config_curso.post("/{id_curso}/refrescar-archivos", # Nombre de función Python es 'solicitar_refresco_archivos_de_curso'
                              summary="Solicitar Refresco/Procesamiento de Archivos del Curso (Tarea Asíncrona)",
                              description="Inicia el proceso asíncrono (tarea Celery) de escaneo y procesamiento de todos los archivos de un curso específico. Esta operación se ejecuta en segundo plano. Devuelve el ID de la tarea Celery para seguimiento.")
async def solicitar_refresco_archivos_de_curso(id_curso: int = FastAPIPath(..., description="ID numérico del curso de Moodle cuyos archivos se van a refrescar.")): # Nombre de función para url_path_for
    """Inicia una tarea Celery para procesar los archivos del curso."""
    # Usar un ID de usuario por defecto o uno específico si la lógica lo permitiera (ej. del token JWT).
    # Este ID de usuario es importante para que la tarea Celery pueda actuar en nombre de alguien en Moodle.
    id_usuario_solicitante_para_tarea = configuracion_global.moodle.id_profesor_por_defecto # Campo refactorizado
    if id_usuario_solicitante_para_tarea is None:
        registrador.error("ID de profesor por defecto (para tareas asíncronas de Celery) no está configurado en el servidor. No se puede iniciar la tarea de refresco.")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="La configuración del servidor no permite iniciar esta tarea de refresco (falta ID de usuario por defecto para operaciones asíncronas).")

    registrador.info(f"Solicitud HTTP para iniciar refresco/procesamiento de archivos para curso ID: {id_curso}, por usuario (defecto) ID: {id_usuario_solicitante_para_tarea}")
    try:
        # Despachar la tarea Celery. 'tarea_delegar_procesamiento_curso' es el nombre de la tarea importada.
        # Se pasan los IDs necesarios para que la tarea Celery pueda instanciar sus propias dependencias.
        resultado_tarea_celery_despachada = tarea_delegar_procesamiento_curso.delay(id_curso=id_curso, id_usuario_solicitante=id_usuario_solicitante_para_tarea)
        id_tarea_celery_despachada = resultado_tarea_celery_despachada.id

        registrador.info(f"Tarea Celery '{id_tarea_celery_despachada}' despachada para procesar archivos del curso ID: {id_curso}")
        return {"id_tarea": id_tarea_celery_despachada, "mensaje": f"Procesamiento de archivos para el curso {id_curso} ha sido iniciado en segundo plano. Puede consultar el estado de la tarea usando el ID proporcionado.", "estado_inicial_tarea": "PENDIENTE"}
    except Exception as e_error_despacho_celery: # Capturar errores al intentar encolar la tarea en Celery/Broker
        registrador.exception(f"Error al despachar la tarea Celery para el procesamiento del curso {id_curso}: {e_error_despacho_celery}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error interno del servidor al intentar iniciar la tarea de procesamiento de archivos. Verifique la conexión con el sistema de colas (Celery/Redis).")


@enrutador_config_curso.get("/tareas/{id_tarea_celery}/estado", # Ruta en español, parámetro de path con guion bajo
                             response_model=modelos_api.RespuestaEstadoTareaAsincronaCelery, # Modelo Pydantic refactorizado
                             summary="Consultar Estado de Tarea Asíncrona Celery",
                             description="Consulta y devuelve el estado actual de una tarea Celery específica, identificada por su ID. Permite hacer seguimiento a procesos largos como el procesamiento de archivos de un curso.")
async def consultar_estado_tarea_celery_asincrona(id_tarea_celery: str = FastAPIPath(..., description="ID único de la tarea Celery a consultar.")): # Nombre de función y parámetro refactorizados
    """Consulta y devuelve el estado de una tarea Celery."""
    registrador.debug(f"Consultando estado para la tarea Celery con ID: {id_tarea_celery}")
    resultado_asincrono_de_celery = AsyncResult(id_tarea_celery, app=aplicacion_celery_instancia) # Usar instancia de app Celery refactorizada

    # Mapear el resultado de Celery al modelo Pydantic de respuesta de la API.
    respuesta_estado_tarea_api = modelos_api.RespuestaEstadoTareaAsincronaCelery( # Modelo refactorizado
        id_tarea_asincrona=id_tarea_celery, # Campo refactorizado
        estado_actual_tarea=resultado_asincrono_de_celery.status, # Estado: PENDING, STARTED, SUCCESS, FAILURE, RETRY, REVOKED. Campo refactorizado
        resultado_final_tarea=resultado_asincrono_de_celery.result if resultado_asincrono_de_celery.successful() else None, # Campo refactorizado
        informacion_error_tarea=resultado_asincrono_de_celery.traceback if resultado_asincrono_de_celery.failed() else None # Campo refactorizado
    )
    # Si la tarea falló, el campo 'resultado' podría contener la excepción. Convertirlo a string para asegurar serialización JSON.
    if resultado_asincrono_de_celery.failed() and respuesta_estado_tarea_api.resultado_final_tarea is None: # Campo refactorizado
        respuesta_estado_tarea_api.resultado_final_tarea = str(resultado_asincrono_de_celery.result)

    registrador.debug(f"Estado de la tarea Celery {id_tarea_celery}: {respuesta_estado_tarea_api.model_dump_json(indent=2, exclude_none=True)}")
    return respuesta_estado_tarea_api

@enrutador_config_curso.get("/{id_curso}/archivos-procesados", # Ruta en español
                             response_model=List[modelos_api.InfoArchivoProcesado], # Modelo Pydantic refactorizado
                             summary="Listar Archivos Procesados e Indexados de un Curso",
                             description="Obtiene una lista de los archivos que han sido procesados e incorporados a la base de conocimiento de IA para un curso específico, junto con su última fecha de modificación registrada.")
async def obtener_lista_archivos_procesados_curso( # Nombre de función más descriptivo
    id_curso: int = FastAPIPath(..., description="ID numérico del curso de Moodle."),
    envoltorio_bd: EnvoltorioPgVector = Depends(obtener_dependencia_envoltorio_pgvector) # Inyección de dependencia
):
    """Obtiene y devuelve la lista de archivos procesados para un curso."""
    registrador.info(f"Solicitud para obtener la lista de archivos procesados para el curso ID: {id_curso}")
    try:
        # El método refactorizado en EnvoltorioPgVector es 'obtener_marcas_de_tiempo_archivos_procesados_curso'
        marcas_tiempo_archivos_procesados = envoltorio_bd.obtener_marcas_de_tiempo_archivos_procesados_curso(id_curso=id_curso)

        if not marcas_tiempo_archivos_procesados: # Devuelve dict vacío si no hay archivos o si ocurre un error manejado internamente
            registrador.info(f"No se encontraron archivos procesados registrados para el curso ID: {id_curso} en la tabla de seguimiento.")
            return [] # Devolver lista vacía es apropiado si no hay archivos

        # Mapear el diccionario a la lista de modelos Pydantic para la respuesta.
        lista_archivos_procesados_api = [
            modelos_api.InfoArchivoProcesado( # Modelo refactorizado
                nombre_identificador_archivo=identificador_archivo, # Campo refactorizado
                timestamp_modificacion_origen=timestamp_modificacion # Campo refactorizado
            )
            for identificador_archivo, timestamp_modificacion in marcas_tiempo_archivos_procesados.items()
        ]
        registrador.info(f"Encontrados {len(lista_archivos_procesados_api)} archivos procesados para el curso ID: {id_curso}.")
        return lista_archivos_procesados_api
    except ErrorBaseDeDatosVectorial as e_error_bd_archivos:
        registrador.error(f"Error de base de datos al obtener archivos procesados para el curso {id_curso}: {e_error_bd_archivos}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error de acceso a la base de datos al listar archivos procesados del curso: {str(e_error_bd_archivos)}")
    except Exception as e_error_inesperado_archivos:
        registrador.exception(f"Error inesperado al obtener archivos procesados para el curso {id_curso}: {e_error_inesperado_archivos}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error interno del servidor al listar los archivos procesados del curso.")


@enrutador_config_curso.delete("/{id_curso}/archivos-procesados/{identificador_archivo:path}", # Path parameter para capturar nombres de archivo con '/'
                                response_model=modelos_api.RespuestaEliminacionRecursosArchivo, # Modelo Pydantic refactorizado
                                summary="Eliminar Archivo Procesado y sus Datos Asociados de la IA",
                                description="Elimina un archivo específico de la base de conocimiento de IA para un curso. Esto incluye la eliminación de todos sus fragmentos vectoriales de la base de datos y la eliminación de su registro de seguimiento para que pueda ser reprocesado si se añade de nuevo.")
async def eliminar_datos_archivo_procesado_curso( # Nombre de función más descriptivo
    id_curso: int = FastAPIPath(..., description="ID numérico del curso de Moodle."),
    identificador_archivo: str = FastAPIPath(..., description="Identificador único del archivo a eliminar (ej. nombre del archivo como 'documento.pdf' o una ruta si es más complejo). FastAPI decodifica automáticamente el path parameter."),
    cliente_moodle: ClienteMoodle = Depends(obtener_dependencia_cliente_moodle), # Necesario para obtener el nombre del curso para la tabla
    envoltorio_bd: EnvoltorioPgVector = Depends(obtener_dependencia_envoltorio_pgvector) # Inyección de dependencia
):
    """Elimina un archivo y todos sus datos asociados (fragmentos, embeddings, seguimiento) del sistema de IA."""
    registrador.info(f"Solicitud para eliminar el archivo '{identificador_archivo}' y sus datos asociados del sistema de IA para el curso ID: {id_curso}.")
    try:
        # Obtener el nombre del curso para construir el nombre de la tabla donde están los fragmentos.
        nombre_curso_efectivo_para_tabla = await _obtener_nombre_curso_para_operaciones(id_curso, cliente_moodle)

        registrador.info(f"Procediendo a eliminar fragmentos vectoriales para el documento ID (identificador archivo) '{identificador_archivo}' de la tabla del curso '{nombre_curso_efectivo_para_tabla}'.")
        # El método refactorizado es 'eliminar_fragmentos_por_id_documento'.
        exito_eliminacion_fragmentos_bd = envoltorio_bd.eliminar_fragmentos_por_id_documento(nombre_curso_efectivo_para_tabla, identificador_archivo)

        registrador.info(f"Procediendo a eliminar el archivo '{identificador_archivo}' (curso {id_curso}) de la tabla de seguimiento de archivos procesados.")
        # El método refactorizado es 'eliminar_registro_de_archivo_en_seguimiento'.
        exito_eliminacion_registro_seguimiento = envoltorio_bd.eliminar_registro_de_archivo_en_seguimiento(id_curso, identificador_archivo)

        if exito_eliminacion_fragmentos_bd and exito_eliminacion_registro_seguimiento:
            # Ambos fueron exitosos (o no encontraron nada que eliminar, lo cual también es un éxito en este contexto).
            mensaje_exito_eliminacion = f"El archivo '{identificador_archivo}' y todos sus datos asociados (fragmentos y seguimiento) han sido eliminados exitosamente del sistema de IA para el curso {id_curso} ('{nombre_curso_efectivo_para_tabla}')."
            registrador.info(mensaje_exito_eliminacion)
            return modelos_api.RespuestaEliminacionRecursosArchivo(mensaje_resultado_eliminacion=mensaje_exito_eliminacion) # Modelo y campo refactorizados
        else:
            # Si alguna de las operaciones no fue completamente exitosa (ej. encontró y eliminó fragmentos pero no el registro de seguimiento, o viceversa).
            detalle_fallo_parcial = f"Resultado de eliminación de fragmentos vectoriales: {'éxito o no encontrado' if exito_eliminacion_fragmentos_bd else 'fallo'}. Resultado de eliminación de registro de seguimiento: {'éxito o no encontrado' if exito_eliminacion_registro_seguimiento else 'fallo'}."
            registrador.error(f"Falló la eliminación completa de los datos del archivo '{identificador_archivo}' para el curso {id_curso}. {detalle_fallo_parcial}")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error al eliminar completamente los datos del archivo. {detalle_fallo_parcial}")

    except HTTPException: # Re-lanzar HTTPExceptions (ej. de _obtener_nombre_curso_para_operaciones si el curso no se encuentra)
        raise
    except ErrorBaseDeDatosVectorial as e_error_bd_eliminar: # Errores específicos de la BD no cubiertos arriba
        registrador.error(f"Error de BD eliminando el archivo '{identificador_archivo}' para el curso {id_curso}: {e_error_bd_eliminar}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error de base de datos al intentar eliminar el archivo y sus datos: {str(e_error_bd_eliminar)}")
    except Exception as e_error_inesperado_eliminar: # Otros errores inesperados
        registrador.exception(f"Error inesperado al eliminar el archivo '{identificador_archivo}' para el curso {id_curso}: {e_error_inesperado_eliminar}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error interno del servidor durante la eliminación del archivo y sus datos: {str(e_error_inesperado_eliminar)}")


@enrutador_config_curso.get("/{id_curso}/configuracion-chat-n8n", # Ruta en español
                             response_model=modelos_api.ConfiguracionPersonalizadaChatN8N, # Modelo Pydantic refactorizado
                             summary="Obtener Configuración Actual del Chat N8N para un Curso",
                             description="Recupera la configuración actual del flujo de chat de N8N asociado a un curso. Esto incluye elementos como los mensajes iniciales, el título de la ventana de chat, y el mensaje de sistema del agente de IA, si es posible extraerlos de la estructura del flujo de N8N.")
async def obtener_configuracion_chat_n8n_para_curso( # Nombre de función más descriptivo
    id_curso: int = FastAPIPath(..., description="ID numérico del curso de Moodle."),
    cliente_moodle: ClienteMoodle = Depends(obtener_dependencia_cliente_moodle), # Para obtener el nombre del curso
    cliente_n8n: ClienteN8N = Depends(obtener_dependencia_cliente_n8n) # Para interactuar con N8N
):
    """Obtiene y devuelve la configuración actual del chat de N8N para un curso, si existe."""
    registrador.info(f"Solicitud para obtener la configuración del chat N8N para el curso ID: {id_curso}.")
    try:
        # Paso 1: Obtener el nombre del curso para identificar el flujo de N8N correspondiente.
        nombre_curso_efectivo = await _obtener_nombre_curso_para_operaciones(id_curso, cliente_moodle)
        # El nombre del flujo en N8N se construye de una forma específica durante la configuración.
        nombre_flujo_n8n_buscado = f"EntrenAI Chat - Curso: {nombre_curso_efectivo} (ID: {id_curso})"
        registrador.debug(f"Buscando flujo de N8N con nombre esperado: '{nombre_flujo_n8n_buscado}'.")

        # Paso 2: Obtener todos los flujos de N8N y buscar el que coincida con el nombre y esté activo.
        lista_completa_flujos_n8n = cliente_n8n.obtener_lista_de_flujos_de_trabajo() # Método refactorizado
        flujo_n8n_objetivo_encontrado = next((flujo for flujo in lista_completa_flujos_n8n if flujo.name == nombre_flujo_n8n_buscado and flujo.active), None)

        # Fallback: si no se encuentra por nombre exacto, buscar uno activo que empiece con el prefijo y contenga el ID.
        if not flujo_n8n_objetivo_encontrado:
            registrador.debug(f"No se encontró flujo N8N por nombre exacto. Buscando por prefijo 'EntrenAI Chat - Curso: ... (ID: {id_curso})' y que esté activo.")
            flujo_n8n_objetivo_encontrado = next((flujo_alt for flujo_alt in lista_completa_flujos_n8n if flujo_alt.name and flujo_alt.name.startswith(f"EntrenAI Chat - Curso: ") and f"(ID: {id_curso})" in flujo_alt.name and flujo_alt.active), None)

        if not flujo_n8n_objetivo_encontrado or not flujo_n8n_objetivo_encontrado.id: # Asegurar que el ID del flujo exista
            registrador.warning(f"No se encontró un flujo de N8N activo y correspondiente para el curso {id_curso} (nombre buscado: '{nombre_flujo_n8n_buscado}').")
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"No se encontró un flujo de chat N8N activo y configurado para el curso {id_curso}. Es posible que la configuración inicial no se haya completado o el flujo haya sido modificado o desactivado.")

        registrador.info(f"Flujo N8N encontrado para el curso {id_curso}: '{flujo_n8n_objetivo_encontrado.name}' (ID: {flujo_n8n_objetivo_encontrado.id}). Obteniendo sus detalles completos...")
        # Paso 3: Obtener los detalles completos del flujo encontrado.
        detalles_flujo_n8n_completo = cliente_n8n.obtener_detalles_de_flujo_de_trabajo(flujo_n8n_objetivo_encontrado.id) # Método refactorizado
        if not detalles_flujo_n8n_completo:
            registrador.error(f"No se pudieron obtener los detalles completos del flujo de N8N con ID '{flujo_n8n_objetivo_encontrado.id}', aunque el flujo fue listado previamente.")
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Error al obtener los detalles del flujo de N8N con ID '{flujo_n8n_objetivo_encontrado.id}'. El flujo podría estar corrupto o inaccesible.")

        # Paso 4: Extraer la configuración relevante de los nodos del flujo.
        config_chat_extraida_api = modelos_api.ConfiguracionPersonalizadaChatN8N() # Inicializar con valores por defecto
        for nodo_del_flujo in detalles_flujo_n8n_completo.nodes:
            if nodo_del_flujo.type == "@n8n/n8n-nodes-langchain.chatTrigger" and nodo_del_flujo.parameters:
                config_chat_extraida_api.mensajes_iniciales_chat = nodo_del_flujo.parameters.initialMessages # Campo refactorizado
                if nodo_del_flujo.parameters.options: # 'options' es un sub-diccionario en parameters
                    config_chat_extraida_api.placeholder_campo_entrada_chat = nodo_del_flujo.parameters.options.get("inputPlaceholder") # Campo refactorizado
                    config_chat_extraida_api.titulo_ventana_chat = nodo_del_flujo.parameters.options.get("title") # Campo refactorizado
            elif nodo_del_flujo.type == "@n8n/n8n-nodes-langchain.agent" and nodo_del_flujo.parameters and nodo_del_flujo.parameters.options:
                # El alias en el modelo Pydantic ('mensaje_sistema') mapea a 'mensaje_sistema_personalizado_ia'.
                config_chat_extraida_api.mensaje_sistema_personalizado_ia = nodo_del_flujo.parameters.options.get("systemMessage") # Campo refactorizado

        registrador.info(f"Configuración de chat N8N extraída del flujo para el curso {id_curso}: {config_chat_extraida_api.model_dump_json(exclude_none=True, by_alias=True)}")
        return config_chat_extraida_api

    except HTTPException: # Re-lanzar HTTPExceptions (ej. 404 de _obtener_nombre_curso o de flujo no encontrado)
        raise
    except ErrorClienteN8N as e_error_cliente_n8n: # Errores específicos del cliente N8N
        registrador.error(f"Error del cliente N8N al obtener configuración de chat para el curso {id_curso}: {e_error_cliente_n8n}")
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Error de comunicación con el servicio N8N: {str(e_error_cliente_n8n)}")
    except Exception as e_error_inesperado_chat_config: # Otros errores inesperados
        registrador.exception(f"Error inesperado al obtener la configuración del chat N8N para el curso {id_curso}: {e_error_inesperado_chat_config}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error interno del servidor al obtener la configuración del chat: {str(e_error_inesperado_chat_config)}")

[end of entrenai_refactor/api/rutas/ruta_configuracion_curso.py]
