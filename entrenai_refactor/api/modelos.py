from pydantic import BaseModel, Field, HttpUrl
from typing import List, Optional, Dict, Any
import uuid

# --- Modelos para Moodle ---

class CursoMoodle(BaseModel):
    """Representa un curso en Moodle."""
    id: int = Field(description="ID único del curso en la plataforma Moodle.")
    nombre_corto: str = Field(alias="shortname", description="Nombre corto identificador del curso.")
    nombre_completo: str = Field(alias="fullname", description="Nombre completo y descriptivo del curso.")
    nombre_a_mostrar: str = Field(alias="displayname", description="Nombre del curso tal como se visualiza al usuario final.")
    resumen: Optional[str] = Field(default=None, alias="summary", description="Descripción o resumen del contenido del curso.")

class SeccionMoodle(BaseModel):
    """Representa una sección dentro de un curso de Moodle."""
    id: int = Field(description="ID único de la sección en Moodle.")
    nombre: str = Field(alias="name", description="Nombre de la sección.")
    resumen: Optional[str] = Field(default=None, alias="summary", description="Resumen o descripción (usualmente en HTML) de la sección.")
    formato_resumen: Optional[int] = Field(default=1, alias="summaryformat", description="Formato del resumen (1=HTML, 0=MOODLE, 2=PLAIN, 4=MARKDOWN).")
    numero_seccion: Optional[int] = Field(default=None, alias="section", description="Número ordinal que identifica la posición de la sección dentro del curso.")
    visible: Optional[bool] = Field(default=True, description="Indica si la sección es visible para los estudiantes.")

class ModuloCursoMoodle(BaseModel): # Renombrado de ModuloMoodle para evitar posible confusión con "módulo Python"
    """Representa un módulo o recurso dentro de un curso de Moodle (ej. una tarea, un archivo, una URL)."""
    id: int = Field(description="ID único del módulo del curso (conocido como 'cmid' o ID de Course Module).")
    url: Optional[HttpUrl] = Field(default=None, description="URL asociada al módulo, si aplica (ej. para un recurso de tipo URL).")
    nombre: str = Field(alias="name", description="Nombre del módulo como se muestra en el curso.")
    nombre_instancia: Optional[str] = Field(default=None, alias="instancename", description="Nombre específico de la instancia de este tipo de módulo (ej. el nombre de un foro o tarea particular).")
    id_instancia: Optional[int] = Field(default=None, alias="instance", description="ID de la instancia del módulo (ej. el ID del foro, no el ID del módulo del curso).")
    tipo_modulo: str = Field(alias="modname", description="Tipo de módulo (ej. 'folder', 'url', 'resource', 'page', 'assign', 'forum').")
    nombre_plural_modulo: Optional[str] = Field(default=None, alias="modplural", description="Nombre en plural del tipo de módulo (ej. 'Carpetas', 'Recursos').")
    descripcion: Optional[str] = Field(default=None, description="Descripción del módulo (usualmente en HTML), si está disponible.")
    visible: Optional[bool] = Field(default=True, description="Indica si el módulo es visible para los estudiantes.")

class ArchivoMoodle(BaseModel):
    """Representa un archivo dentro de Moodle, usualmente contenido en un módulo de tipo 'resource' o 'folder'."""
    tipo: str = Field(alias="type", description="Tipo de contenido, comúnmente 'file' para archivos.")
    nombre_archivo: str = Field(alias="filename", description="Nombre original del archivo con su extensión.")
    ruta_archivo: str = Field(alias="filepath", description="Ruta relativa del archivo dentro de la estructura de archivos de Moodle.")
    tamano_archivo_bytes: int = Field(alias="filesize", description="Tamaño del archivo en bytes.")
    url_descarga_archivo: HttpUrl = Field(alias="fileurl", description="URL completa para descargar el archivo directamente desde Moodle.")
    timestamp_modificacion: int = Field(alias="timemodified", description="Timestamp Unix de la última modificación del archivo.")
    autor: Optional[str] = Field(default=None, description="Autor del archivo, si está disponible.")
    licencia: Optional[str] = Field(default=None, description="Licencia de uso del archivo, si se especifica.")

class ConfiguracionChatN8NEnMoodle(BaseModel): # Renombrado para mayor claridad
    """Configuraciones específicas del chat de N8N que se pueden obtener de Moodle (a través de un plugin local, por ejemplo)."""
    mensajes_iniciales: Optional[str] = Field(default=None, description="Mensajes de bienvenida o introductorios para mostrar en la interfaz de chat.")
    anexo_mensaje_sistema: Optional[str] = Field(default=None, description="Texto adicional para adjuntar al mensaje de sistema del agente de IA en N8N.")
    titulo_chat: Optional[str] = Field(default=None, description="Título que se mostrará en la ventana o cabecera del chat.")
    placeholder_entrada_chat: Optional[str] = Field(default=None, alias="placeholder_entrada", description="Texto de ejemplo o placeholder para la caja de entrada de texto del chat.")
    class Config:
        extra = "ignore" # Ignorar campos extra que puedan venir de Moodle
        populate_by_name = True # Permitir poblar por alias y por nombre de campo

# --- Modelos para N8N ---

class ParametrosNodoFlujoN8N(BaseModel): # Renombrado para mayor claridad
    """Modelo flexible para los parámetros de un nodo en un flujo de trabajo de N8N."""
    # Campos comunes observados en nodos de N8N, permitir flexibilidad
    initialMessages: Optional[str] = Field(default=None, description="Mensajes iniciales para nodos de chat.")
    options: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Opciones generales del nodo.")
    public: Optional[bool] = Field(default=None, description="Indicador de visibilidad pública (ej. para webhooks).")
    webhookId: Optional[str] = Field(default=None, description="ID del webhook asociado al nodo.")
    mode: Optional[str] = Field(default=None, description="Modo de operación del nodo.")
    toolName: Optional[str] = Field(default=None, description="Nombre de la herramienta (ej. en nodos de agente IA).")
    toolDescription: Optional[str] = Field(default=None, description="Descripción de la herramienta.")
    tableName: Optional[str] = Field(default=None, description="Nombre de tabla (ej. en nodos de base de datos vectorial).")
    modelName: Optional[str] = Field(default=None, description="Nombre del modelo de IA.")
    model: Optional[str] = Field(default=None, description="Nombre del modelo de IA (alternativo).")
    baseUrl: Optional[HttpUrl] = Field(default=None, description="URL base para servicios externos (ej. Ollama).")
    class Config:
        extra = "allow" # Permitir campos extra ya que los nodos N8N varían mucho
        alias_generator = lambda string: string # Usar nombres de campo tal cual para alias por defecto
        populate_by_name = True # Permitir poblar por alias y nombre de campo

class NodoFlujoN8N(BaseModel): # Renombrado para mayor claridad
    """Representa un nodo individual dentro de un flujo de trabajo de N8N."""
    id: str = Field(description="ID único del nodo dentro del flujo de trabajo.")
    name: str = Field(description="Nombre del nodo tal como se muestra en la interfaz de N8N.")
    type: str = Field(description="Tipo de nodo (ej. '@n8n/n8n-nodes-base.start').")
    typeVersion: float = Field(description="Versión del tipo de nodo.") # Puede ser int o float, float es más seguro
    position: List[float] = Field(description="Coordenadas [x, y] de la posición del nodo en el lienzo de N8N.")
    parameters: ParametrosNodoFlujoN8N = Field(default_factory=ParametrosNodoFlujoN8N, description="Parámetros específicos de configuración del nodo.")
    credentials: Optional[Dict[str, Any]] = Field(default=None, description="Credenciales asociadas o configuradas para el nodo.")

class FlujoDeTrabajoN8N(BaseModel): # Renombrado para mayor claridad
    """Representa un flujo de trabajo completo de N8N."""
    id: Optional[str] = Field(default=None, description="ID único del flujo de trabajo en la instancia de N8N (asignado por N8N).")
    name: str = Field(description="Nombre descriptivo del flujo de trabajo.")
    active: bool = Field(default=False, description="Indica si el flujo de trabajo está activo y escuchando eventos.")
    nodes: List[NodoFlujoN8N] = Field(default_factory=list, description="Lista de todos los nodos que componen el flujo.")
    connections: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Define las conexiones (edges) entre los nodos del flujo.") # N8N usa 'connections' o 'edges'
    settings: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Configuraciones generales del flujo de trabajo.")
    staticData: Optional[Dict[str, Any]] = Field(default=None, description="Datos estáticos asociados con el flujo (poco común).")
    meta: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Metadatos adicionales sobre el flujo (ej. timezone, template).")
    tags: Optional[List[Dict[str, Any]]] = Field(default_factory=list, description="Etiquetas asociadas al flujo para organización (N8N >=1.0 usa lista de objetos).")


# --- Modelos para Almacenamiento de Vectores (PGVector) ---

class FragmentoDeDocumento(BaseModel): # Renombrado para mayor claridad
    """Representa un fragmento de texto de un documento, con su embedding y metadatos, listo para ser almacenado."""
    id_fragmento: str = Field(default_factory=lambda: str(uuid.uuid4()), description="ID único universalmente identificable para el fragmento.")
    id_curso: int = Field(description="ID del curso al que pertenece este fragmento de documento.")
    id_documento: str = Field(description="Identificador único del documento original del cual proviene el fragmento (ej. hash del archivo o ID de Moodle).")
    texto: str = Field(description="Contenido textual original del fragmento.")
    embedding: Optional[List[float]] = Field(default=None, description="Vector de embedding que representa semánticamente el texto del fragmento.")
    metadatos: Dict[str, Any] = Field(default_factory=dict, description="Metadatos adicionales asociados al fragmento (ej. nombre de archivo, título del documento, número de página).")

# --- Modelos para Búsqueda Semántica ---

class SolicitudBusquedaContextual(BaseModel):
    """Cuerpo de la petición para realizar una búsqueda contextual o semántica."""
    consulta_usuario: str = Field(alias="consulta", description="Texto de la consulta o pregunta formulada por el usuario.")
    id_curso: int = Field(description="ID del curso específico en el cual se realizará la búsqueda.")
    numero_resultados: Optional[int] = Field(default=5, ge=1, le=20, alias="limite", description="Número máximo de fragmentos relevantes a devolver.")
    # Considerar añadir filtros adicionales si es necesario, como id_documento_especifico.

class ItemResultadoBusqueda(BaseModel): # Renombrado para mayor claridad
    """Representa un único fragmento de documento devuelto como resultado de una búsqueda."""
    id_fragmento: str = Field(description="ID del fragmento de documento encontrado.")
    similitud: float = Field(description="Puntuación de similitud o relevancia entre la consulta y el fragmento (un valor mayor usualmente indica mayor similitud).")
    texto_fragmento: str = Field(description="Contenido textual del fragmento relevante.")
    metadatos: Dict[str, Any] = Field(description="Metadatos asociados al fragmento (ej. nombre de archivo, título del documento, etc.).")

class RespuestaBusquedaContextual(BaseModel): # Renombrado para mayor claridad
    """Respuesta devuelta por el endpoint de búsqueda contextual, conteniendo los resultados."""
    consulta_original_usuario: str = Field(alias="consulta_original", description="La consulta original tal como fue ingresada por el usuario.")
    resultados_busqueda: List[ItemResultadoBusqueda] = Field(alias="resultados", description="Lista de los fragmentos de documento más relevantes encontrados.")
    total_resultados_devueltos: int = Field(alias="total_resultados", description="Número total de resultados devueltos en esta respuesta.")
    # Se podría añadir información adicional como el tiempo que tomó la búsqueda, etc.

# --- Modelos Generales para la API ---

class RespuestaConfiguracionCurso(BaseModel):
    """Respuesta detallada tras una operación de configuración o procesamiento de un curso."""
    id_curso: int = Field(description="ID del curso procesado.")
    estado_operacion: str = Field(alias="estado", description="Estado final de la operación de configuración (ej. 'completado', 'fallido', 'parcial').")
    mensaje_informativo: str = Field(alias="mensaje", description="Mensaje descriptivo sobre el resultado de la operación.")
    nombre_tabla_vectorial_curso: Optional[str] = Field(default=None, alias="nombre_tabla_vectorial", description="Nombre de la tabla en la base de datos vectorial asignada a este curso.")
    id_seccion_moodle_entrenai: Optional[int] = Field(default=None, alias="id_seccion_moodle", description="ID de la sección creada o utilizada en Moodle para los recursos de EntrenAI.")
    id_carpeta_moodle_entrenai: Optional[int] = Field(default=None, alias="id_carpeta_moodle", description="ID del módulo de tipo carpeta creado o utilizado en Moodle para EntrenAI.")
    id_chat_moodle_entrenai: Optional[int] = Field(default=None, alias="id_chat_moodle", description="ID del módulo de tipo URL que enlaza al chat de N8N, creado en Moodle.")
    id_enlace_refresco_moodle_entrenai: Optional[int] = Field(default=None, alias="id_enlace_refresco_moodle", description="ID del módulo de tipo URL para el refresco manual, creado en Moodle.")
    url_chat_n8n_curso: Optional[HttpUrl] = Field(default=None, alias="url_chat_n8n", description="URL del webhook del flujo de chat de N8N configurado para este curso.")

class ArchivoProcesadoInfo(BaseModel): # Renombrado para mayor claridad
    """Información sobre un archivo que ha sido procesado o está siendo rastreado."""
    nombre_archivo: str = Field(alias="nombre", description="Nombre o identificador único del archivo (ej. nombre de archivo en Moodle o hash).")
    timestamp_ultima_modificacion: int = Field(alias="ultima_modificacion_moodle", description="Timestamp Unix de la última modificación del archivo según Moodle u otra fuente.")

class RespuestaEliminacionArchivo(BaseModel):
    """Respuesta tras una solicitud de eliminación de un archivo y sus datos asociados."""
    mensaje: str = Field(description="Mensaje indicando el resultado de la operación de eliminación.")
    detalle_operacion: Optional[str] = Field(default=None, alias="detalle", description="Detalles adicionales sobre la operación (ej. número de fragmentos eliminados).")

class SolicitudProcesamientoArchivosCurso(BaseModel): # Renombrado para mayor claridad
    """Cuerpo de la petición para iniciar el procesamiento de los archivos de un curso."""
    id_curso: int = Field(description="ID del curso de Moodle cuyos archivos se van a procesar.")
    id_usuario_solicitante: int = Field(alias="id_usuario", description="ID del usuario de Moodle que inicia la operación de procesamiento.")

class RespuestaEstadoTareaAsincrona(BaseModel): # Renombrado para mayor claridad
    """Respuesta que informa sobre el estado de una tarea asíncrona (ej. tarea Celery)."""
    id_tarea: str = Field(description="ID único de la tarea Celery o similar.")
    estado_tarea: str = Field(alias="estado", description="Estado actual de la tarea (ej. 'PENDIENTE', 'EN_PROGRESO', 'EXITOSO', 'FALLIDO').")
    resultado_tarea: Optional[Any] = Field(default=None, alias="resultado", description="Resultado de la tarea si esta finalizó con éxito y produjo alguno.")
    info_error_tarea: Optional[str] = Field(default=None, alias="traceback", description="Información del error o traceback si la tarea falló.")

class ConfiguracionChatN8NUsuario(BaseModel): # Renombrado para mayor claridad
    """Modelo para que el usuario configure ciertos aspectos del chat N8N a través de la API."""
    mensajes_iniciales: Optional[str] = Field(default=None, description="Mensajes de bienvenida o introductorios para el chat.")
    placeholder_entrada_chat: Optional[str] = Field(default=None, alias="placeholder_entrada", description="Texto de ejemplo o placeholder para la caja de entrada de texto del chat.")
    titulo_ventana_chat: Optional[str] = Field(default=None, alias="titulo_chat", description="Título que se mostrará en la ventana o cabecera del chat.")
    mensaje_sistema_personalizado: Optional[str] = Field(default=None, alias="mensaje_sistema", description="Mensaje de sistema personalizado para guiar el comportamiento del agente de IA.")
    class Config:
        populate_by_name = True # Permite usar tanto el nombre del campo como el alias para poblar el modelo
        extra = "ignore" # Ignorar campos adicionales no definidos en el modelo
