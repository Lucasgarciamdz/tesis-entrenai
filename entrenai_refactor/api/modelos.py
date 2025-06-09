from pydantic import BaseModel, Field, HttpUrl
from typing import List, Optional, Dict, Any
import uuid # Para generar IDs únicos para fragmentos

# --- Modelos para la Interacción con Moodle ---

class CursoMoodle(BaseModel):
    """Representa la estructura de datos de un curso tal como se obtiene de Moodle."""
    id: int = Field(description="ID único del curso en la plataforma Moodle.")
    nombre_corto: str = Field(alias="shortname", description="Nombre corto identificador y único del curso.")
    nombre_completo: str = Field(alias="fullname", description="Nombre completo y descriptivo del curso.")
    nombre_a_mostrar: str = Field(alias="displayname", description="Nombre del curso tal como se visualiza al usuario final en listados.")
    resumen: Optional[str] = Field(default=None, alias="summary", description="Descripción o resumen del contenido del curso (puede contener HTML).")
    # Se podrían añadir más campos si son necesarios, como 'categoryid', 'startdate', 'enddate', etc.

class SeccionCursoMoodle(BaseModel): # Nombre clarificado: SeccionCursoMoodle
    """Representa una sección temática o semanal dentro de un curso de Moodle."""
    id: int = Field(description="ID único de la sección dentro del curso en Moodle.")
    nombre: str = Field(alias="name", description="Nombre de la sección (ej. 'Tema 1', 'Semana del 5 de Octubre').")
    resumen: Optional[str] = Field(default=None, alias="summary", description="Resumen o descripción de la sección (usualmente en HTML).")
    formato_resumen: Optional[int] = Field(default=1, alias="summaryformat", description="Formato del resumen (1=HTML, 0=MOODLE, 2=PLAIN, 4=MARKDOWN).")
    numero_seccion_curso: Optional[int] = Field(default=None, alias="section", description="Número ordinal que identifica la posición de la sección dentro del curso (no siempre presente o fiable).") # Nombre clarificado
    visible: Optional[bool] = Field(default=True, description="Indica si la sección es visible para los estudiantes en el curso.")
    # 'modules' (módulos de la sección) se maneja por separado si es necesario, ya que puede ser una lista grande.

class ModuloDeCursoMoodle(BaseModel): # Nombre clarificado: ModuloDeCursoMoodle
    """
    Representa un módulo o recurso individual dentro de una sección de un curso de Moodle.
    Un módulo puede ser una tarea, un archivo, una URL, un foro, una carpeta, etc.
    """
    id: int = Field(description="ID único del módulo del curso (conocido como 'cmid' o ID de Course Module). Este ID es único en toda la instancia de Moodle.")
    url: Optional[HttpUrl] = Field(default=None, description="URL directa al módulo dentro de Moodle, si aplica (ej. para un recurso de tipo URL o la página principal de una tarea).")
    nombre: str = Field(alias="name", description="Nombre del módulo tal como se muestra en la página del curso (ej. 'Documento de Requisitos', 'Enlace a Normativa').")
    nombre_instancia: Optional[str] = Field(default=None, alias="instancename", description="Nombre específico de la instancia de este tipo de módulo (ej. el nombre de un foro particular, o el título de una página). A veces es igual a 'name'.")
    id_instancia_especifica: Optional[int] = Field(default=None, alias="instance", description="ID de la instancia específica del tipo de módulo (ej. el ID del recurso 'page', 'url', 'folder', 'forum', etc. No es el 'cmid').") # Nombre clarificado
    tipo_modulo: str = Field(alias="modname", description="Tipo de módulo según Moodle (ej. 'folder', 'url', 'resource', 'page', 'assign', 'forum', 'quiz').")
    nombre_plural_modulo: Optional[str] = Field(default=None, alias="modplural", description="Nombre en plural del tipo de módulo (ej. 'Carpetas', 'Recursos', 'Tareas').")
    descripcion: Optional[str] = Field(default=None, description="Descripción del módulo (usualmente en HTML), si está disponible y es aplicable (ej. para un recurso 'page' o 'assign').")
    visible: Optional[bool] = Field(default=True, description="Indica si el módulo es visible para los estudiantes en la página del curso.")
    # 'contents' (para módulos tipo 'folder' o 'resource' con múltiples archivos) se maneja por separado.

class ArchivoContenidoEnMoodle(BaseModel): # Nombre clarificado: ArchivoContenidoEnMoodle
    """Representa un archivo almacenado en Moodle, usualmente contenido dentro de un módulo de tipo 'resource' o 'folder'."""
    tipo_item: str = Field(alias="type", description="Tipo de contenido, comúnmente 'file' para archivos, pero puede ser 'url' para enlaces externos dentro de una carpeta.") # Nombre clarificado
    nombre_original_archivo: str = Field(alias="filename", description="Nombre original del archivo con su extensión.") # Nombre clarificado
    ruta_relativa_archivo: str = Field(alias="filepath", description="Ruta relativa del archivo dentro de la estructura de archivos de Moodle (ej. '/' para raíz de carpeta, '/subcarpeta/').") # Nombre clarificado
    tamano_archivo_en_bytes: int = Field(alias="filesize", description="Tamaño del archivo en bytes.") # Nombre clarificado
    url_descarga_directa_archivo: HttpUrl = Field(alias="fileurl", description="URL completa y directa para descargar el archivo desde Moodle (puede requerir token).") # Nombre clarificado
    timestamp_ultima_modificacion: int = Field(alias="timemodified", description="Timestamp Unix de la última vez que el archivo fue modificado en Moodle.") # Nombre clarificado
    autor_archivo: Optional[str] = Field(default=None, alias="author", description="Autor del archivo, si esta información está disponible en Moodle.") # Nombre clarificado
    licencia_archivo: Optional[str] = Field(default=None, alias="license", description="Licencia de uso del archivo, si se especifica en Moodle.") # Nombre clarificado

class ConfiguracionChatN8NMoodle(BaseModel): # Nombre definitivo
    """
    Configuraciones específicas para la interfaz de chat de N8N, que pueden ser
    obtenidas desde Moodle (por ejemplo, a través de un plugin local o campos personalizados).
    """
    mensajes_iniciales_chat: Optional[str] = Field(default=None, alias="initial_message", description="Mensajes de bienvenida o introductorios para mostrar en la interfaz de chat de N8N.") # Nombre clarificado
    anexo_prompt_sistema_ia: Optional[str] = Field(default=None, alias="system_message_append", description="Texto adicional para adjuntar al mensaje de sistema base del agente de IA en N8N, permitiendo personalización por curso.") # Nombre clarificado
    titulo_ventana_chat: Optional[str] = Field(default=None, alias="chat_title", description="Título que se mostrará en la ventana o cabecera de la interfaz de chat.") # Nombre clarificado
    placeholder_campo_entrada_chat: Optional[str] = Field(default=None, alias="input_placeholder", description="Texto de ejemplo o placeholder para la caja de entrada de texto del chat.") # Nombre clarificado
    class Config:
        extra = "ignore" # Ignorar campos extra que puedan venir de Moodle y no estén definidos aquí.
        populate_by_name = True # Permitir poblar campos usando tanto el nombre del campo como su alias.

# --- Modelos para la Interacción con N8N ---

class ParametrosDeNodoN8N(BaseModel): # Nombre definitivo
    """
    Modelo flexible para representar los parámetros de configuración de un nodo
    dentro de un flujo de trabajo de N8N. Los campos son opcionales y variados.
    """
    # Campos comunes observados en nodos de N8N, permitir flexibilidad y campos extra.
    initialMessages: Optional[str] = Field(default=None, description="Mensajes iniciales para nodos de tipo Chat Trigger.")
    options: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Contenedor genérico para opciones variadas del nodo.")
    public: Optional[bool] = Field(default=None, description="Indicador de visibilidad pública (ej. para webhooks).")
    webhookId: Optional[str] = Field(default=None, description="ID del webhook asociado al nodo (ej. en Chat Trigger).")
    mode: Optional[str] = Field(default=None, description="Modo de operación o subtipo del nodo.")
    toolName: Optional[str] = Field(default=None, description="Nombre de la herramienta (ej. en nodos de Agente IA que usan herramientas).")
    toolDescription: Optional[str] = Field(default=None, description="Descripción de la herramienta para el Agente IA.")
    tableName: Optional[str] = Field(default=None, description="Nombre de tabla (ej. en nodos de Vector Store para PGVector).")
    modelName: Optional[str] = Field(default=None, description="Nombre del modelo de IA (usado por algunos nodos de IA).")
    model: Optional[str] = Field(default=None, description="Nombre del modelo de IA (alternativa común para 'modelName').")
    baseUrl: Optional[HttpUrl] = Field(default=None, description="URL base para servicios externos como Ollama.")
    # Se pueden añadir más campos comunes si se identifican patrones.
    class Config:
        extra = "allow" # Permitir campos extra ya que los nodos N8N varían mucho en sus parámetros.
        # alias_generator no es necesario si los nombres de campo coinciden con los JSON de N8N o se usan Field(alias=...).
        populate_by_name = True # Permitir poblar por alias y nombre de campo.

class NodoDeFlujoN8N(BaseModel): # Nombre definitivo
    """Representa un nodo individual dentro de la estructura de un flujo de trabajo de N8N."""
    id: str = Field(description="ID único del nodo, asignado por N8N dentro del contexto del flujo.")
    name: str = Field(description="Nombre del nodo tal como se muestra en la interfaz gráfica de N8N.")
    type: str = Field(description="Tipo de nodo, identifica su funcionalidad (ej. '@n8n/n8n-nodes-base.start', '@n8n/n8n-nodes-langchain.agent').")
    typeVersion: float = Field(description="Versión del tipo de nodo (ej. 1.0, 2.1). Se usa float para mayor compatibilidad.")
    position: List[float] = Field(description="Coordenadas [x, y] de la posición del nodo en el lienzo de N8N.")
    parameters: ParametrosDeNodoN8N = Field(default_factory=ParametrosDeNodoN8N, description="Parámetros específicos de configuración del nodo.")
    credentials: Optional[Dict[str, Any]] = Field(default=None, description="Credenciales asociadas o configuradas para el nodo, si las requiere.")

class FlujoDeTrabajoN8N(BaseModel): # Nombre definitivo
    """Representa la estructura completa de un flujo de trabajo de N8N."""
    id: Optional[str] = Field(default=None, description="ID único del flujo de trabajo en la instancia de N8N (asignado por N8N al crear/importar).")
    name: str = Field(description="Nombre descriptivo y legible del flujo de trabajo.")
    active: bool = Field(default=False, description="Indica si el flujo de trabajo está activo y escuchando eventos o disparadores.")
    nodes: List[NodoDeFlujoN8N] = Field(default_factory=list, description="Lista de todos los nodos que componen el flujo de trabajo.")
    connections: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Define las conexiones (aristas o 'edges') entre las salidas y entradas de los nodos del flujo.")
    settings: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Configuraciones generales aplicables al flujo de trabajo (ej. zona horaria, manejo de errores).")
    staticData: Optional[Dict[str, Any]] = Field(default=None, description="Datos estáticos asociados con el flujo (uso menos común).")
    meta: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Metadatos adicionales sobre el flujo (ej. si es una plantilla, información de creación).")
    tags: Optional[List[Dict[str, Any]]] = Field(default_factory=list, description="Etiquetas asociadas al flujo para organización y filtrado en N8N (formato: lista de objetos con 'name').")


# --- Modelos para Almacenamiento de Vectores (usados con PGVector) ---

class FragmentoDocumentoParaVectorizar(BaseModel): # Nombre definitivo
    """
    Representa un fragmento de texto extraído de un documento, con su embedding vectorial
    y metadatos asociados, listo para ser almacenado en una base de datos vectorial.
    """
    id_fragmento: str = Field(default_factory=lambda: str(uuid.uuid4()), description="ID único universalmente identificable (UUID) para este fragmento.")
    id_curso: int = Field(description="ID del curso al que pertenece el documento de este fragmento.")
    id_documento: str = Field(description="Identificador único del documento original del cual proviene el fragmento (ej. hash del archivo, ID de recurso de Moodle).")
    texto_original_fragmento: str = Field(alias="texto", description="Contenido textual original y limpio del fragmento.") # Nombre clarificado
    embedding_vectorial: Optional[List[float]] = Field(alias="embedding", default=None, description="Vector de embedding que representa semánticamente el texto del fragmento.") # Nombre clarificado
    metadatos_fragmento: Dict[str, Any] = Field(alias="metadatos", default_factory=dict, description="Metadatos adicionales asociados al fragmento (ej. nombre de archivo, título del documento, número de página, tipo de contenido).") # Nombre clarificado
    # Considerar añadir 'fecha_creacion', 'fecha_modificacion' si es relevante para la gestión de fragmentos.
    class Config:
        populate_by_name = True # Permite usar alias al crear instancias del modelo

# --- Modelos para Búsqueda Semántica y Respuestas de la API ---

class SolicitudBusquedaSemantica(BaseModel): # Nombre definitivo
    """Define el cuerpo de la petición para realizar una búsqueda contextual o semántica en un curso."""
    consulta_usuario: str = Field(alias="consulta", description="Texto de la consulta o pregunta formulada por el usuario para la búsqueda.")
    id_curso: int = Field(description="ID del curso específico en el cual se realizará la búsqueda de fragmentos relevantes.")
    limite_resultados_similares: Optional[int] = Field(default=5, ge=1, le=20, alias="limite", description="Número máximo de fragmentos relevantes (similares) a devolver en la respuesta.") # Nombre clarificado
    # Podrían añadirse filtros adicionales si fuera necesario, como id_documento_especifico, umbral_similitud_minima, etc.

class ItemResultadoBusquedaSemantica(BaseModel): # Nombre definitivo
    """Representa un único fragmento de documento devuelto como resultado de una búsqueda semántica."""
    id_fragmento: str = Field(description="ID del fragmento de documento encontrado que es relevante para la consulta.")
    puntuacion_similitud: float = Field(alias="similitud", description="Puntuación de similitud o relevancia entre la consulta y el fragmento (un valor mayor usualmente indica mayor similitud).") # Nombre clarificado
    distancia_vectorial: Optional[float] = Field(alias="distancia", default=None, description="Distancia vectorial original (ej. L2) si está disponible. Menor es más similar.") # Nuevo campo opcional
    texto_completo_fragmento: str = Field(alias="texto_fragmento", description="Contenido textual completo del fragmento relevante.") # Nombre clarificado
    metadatos_asociados_fragmento: Dict[str, Any] = Field(alias="metadatos", description="Metadatos asociados al fragmento (ej. nombre de archivo, título del documento, etc.).") # Nombre clarificado
    class Config:
        populate_by_name = True

class RespuestaBusquedaSemantica(BaseModel): # Nombre definitivo
    """Define la estructura de la respuesta devuelta por el endpoint de búsqueda contextual/semántica."""
    consulta_original_del_usuario: str = Field(alias="consulta_original", description="La consulta original tal como fue ingresada por el usuario.") # Nombre clarificado
    resultados_de_la_busqueda: List[ItemResultadoBusquedaSemantica] = Field(alias="resultados", description="Lista de los fragmentos de documento más relevantes encontrados, ordenados por similitud.") # Nombre clarificado
    numero_total_resultados_devueltos: int = Field(alias="total_resultados", description="Número total de resultados devueltos en esta respuesta.") # Nombre clarificado
    # Se podría añadir información adicional como el tiempo que tomó la búsqueda, ID de la búsqueda, etc.
    class Config:
        populate_by_name = True

# --- Modelos Generales para Operaciones de la API ---

class RespuestaConfiguracionCursoEntrenAI(BaseModel): # Nombre definitivo
    """
    Respuesta detallada tras una operación de configuración inicial o procesamiento completo de un curso,
    indicando los resultados y los IDs de los recursos creados o gestionados.
    """
    id_curso: int = Field(description="ID del curso procesado o configurado.")
    estado_general_operacion: str = Field(alias="estado", description="Estado final de la operación de configuración (ej. 'completado_exitosamente', 'fallido_parcialmente', 'error_critico').") # Nombre clarificado
    mensaje_informativo_operacion: str = Field(alias="mensaje", description="Mensaje descriptivo sobre el resultado general de la operación.") # Nombre clarificado
    nombre_tabla_vectorial_asignada_curso: Optional[str] = Field(default=None, alias="nombre_tabla_vectorial", description="Nombre de la tabla en la base de datos vectorial que ha sido asignada o confirmada para este curso.") # Nombre clarificado
    id_seccion_entrenai_moodle: Optional[int] = Field(default=None, alias="id_seccion_moodle", description="ID de la sección creada o utilizada en Moodle para los recursos específicos de EntrenAI.") # Nombre clarificado
    id_carpeta_recursos_ia_moodle: Optional[int] = Field(default=None, alias="id_carpeta_moodle", description="ID del módulo de tipo carpeta creado o utilizado en Moodle para los archivos procesados por EntrenAI.") # Nombre clarificado
    id_enlace_chat_ia_moodle: Optional[int] = Field(default=None, alias="id_chat_moodle", description="ID del módulo de tipo URL que enlaza al chat de N8N, creado o verificado en Moodle para este curso.") # Nombre clarificado
    id_enlace_refresco_manual_moodle: Optional[int] = Field(default=None, alias="id_enlace_refresco_moodle", description="ID del módulo de tipo URL que permite el refresco manual del contenido IA, creado o verificado en Moodle.") # Nombre clarificado
    url_chat_n8n_especifico_curso: Optional[HttpUrl] = Field(default=None, alias="url_chat_n8n", description="URL del webhook del flujo de chat de N8N que ha sido configurado o verificado para este curso.") # Nombre clarificado
    class Config:
        populate_by_name = True

class InfoArchivoProcesado(BaseModel): # Nombre definitivo
    """Información concisa sobre un archivo que ha sido procesado o está siendo rastreado por el sistema."""
    nombre_identificador_archivo: str = Field(alias="nombre_archivo", description="Nombre o identificador único del archivo (ej. nombre de archivo en Moodle, hash de contenido).") # Nombre clarificado
    timestamp_modificacion_origen: int = Field(alias="ultima_modificacion_moodle", description="Timestamp Unix de la última modificación del archivo según su fuente original (ej. Moodle).") # Nombre clarificado
    class Config:
        populate_by_name = True

class RespuestaEliminacionRecursosArchivo(BaseModel): # Nombre definitivo
    """Respuesta tras una solicitud de eliminación de un archivo y todos sus datos asociados del sistema."""
    mensaje_resultado_eliminacion: str = Field(alias="mensaje", description="Mensaje indicando el resultado de la operación de eliminación del archivo y sus recursos.") # Nombre clarificado
    detalle_especifico_operacion: Optional[str] = Field(default=None, alias="detalle", description="Detalles adicionales sobre la operación (ej. número de fragmentos vectoriales eliminados, estado de eliminación en seguimiento).") # Nombre clarificado
    class Config:
        populate_by_name = True

class SolicitudProcesamientoArchivosDeCurso(BaseModel): # Nombre definitivo
    """Cuerpo de la petición para iniciar el procesamiento (o reprocesamiento) de los archivos de un curso."""
    id_curso: int = Field(description="ID del curso de Moodle cuyos archivos se van a procesar o actualizar.")
    id_usuario_moodle_solicitante: int = Field(alias="id_usuario", description="ID del usuario de Moodle (generalmente un profesor o administrador) que inicia la operación de procesamiento.") # Nombre clarificado
    # Se podría añadir un flag opcional como 'forzar_reprocesamiento_total: bool = False'
    class Config:
        populate_by_name = True

class RespuestaEstadoTareaAsincronaCelery(BaseModel): # Nombre definitivo
    """Respuesta que informa sobre el estado de una tarea asíncrona gestionada por Celery (u otro sistema similar)."""
    id_tarea_asincrona: str = Field(alias="id_tarea", description="ID único de la tarea Celery o del sistema de tareas asíncronas utilizado.") # Nombre clarificado
    estado_actual_tarea: str = Field(alias="estado", description="Estado actual de la tarea (ej. 'PENDIENTE', 'EN_PROGRESO', 'EXITOSO', 'FALLIDO', 'RECIBIDA').") # Nombre clarificado
    resultado_final_tarea: Optional[Any] = Field(default=None, alias="resultado", description="Resultado de la tarea si esta finalizó con éxito y produjo algún valor de retorno.") # Nombre clarificado
    informacion_error_tarea: Optional[str] = Field(default=None, alias="traceback", description="Información detallada del error o traceback completo si la tarea falló durante su ejecución.") # Nombre clarificado
    class Config:
        populate_by_name = True

class ConfiguracionPersonalizadaChatN8N(BaseModel): # Nombre definitivo
    """
    Modelo para que un usuario (ej. profesor) pueda configurar ciertos aspectos
    de la interfaz y comportamiento del chat de N8N para un curso específico, a través de la API.
    """
    mensajes_iniciales_chat: Optional[str] = Field(default=None, alias="mensajes_iniciales", description="Mensajes de bienvenida o introductorios para mostrar en la interfaz de chat.")
    placeholder_campo_entrada_chat: Optional[str] = Field(default=None, alias="placeholder_entrada", description="Texto de ejemplo o placeholder para la caja de entrada de texto del chat.")
    titulo_ventana_chat: Optional[str] = Field(default=None, alias="titulo_chat", description="Título que se mostrará en la ventana o cabecera de la interfaz de chat.")
    mensaje_sistema_personalizado_ia: Optional[str] = Field(default=None, alias="mensaje_sistema", description="Mensaje de sistema personalizado para guiar el comportamiento del agente de IA, que se añadirá al prompt base.") # Nombre clarificado
    class Config:
        populate_by_name = True # Permite usar tanto el nombre del campo como el alias para poblar el modelo
        extra = "ignore" # Ignorar campos adicionales no definidos en el modelo si se envían en la petición

[end of entrenai_refactor/api/modelos.py]
