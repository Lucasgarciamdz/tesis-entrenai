from pydantic import BaseModel, Field, HttpUrl
from typing import List, Optional, Dict, Any
import uuid

# --- Modelos para Moodle ---

class CursoMoodle(BaseModel):
    id: int = Field(description="ID del curso en Moodle.")
    nombre_corto: str = Field(alias="shortname", description="Nombre corto del curso.")
    nombre_completo: str = Field(alias="fullname", description="Nombre completo del curso.")
    nombre_a_mostrar: str = Field(alias="displayname", description="Nombre del curso tal como se muestra al usuario.")
    resumen: Optional[str] = Field(default=None, alias="summary", description="Resumen o descripción del curso.")

class SeccionMoodle(BaseModel):
    id: int = Field(description="ID de la sección en Moodle.")
    nombre: str = Field(alias="name", description="Nombre de la sección.")
    resumen: Optional[str] = Field(default=None, alias="summary", description="Resumen o descripción HTML de la sección.")
    formato_resumen: Optional[int] = Field(default=1, alias="summaryformat", description="Formato del resumen (1=HTML, 0=MOODLE, 2=PLAIN, 4=MARKDOWN).")
    numero_seccion: Optional[int] = Field(default=None, alias="section", description="Número ordinal de la sección dentro del curso.")
    visible: Optional[bool] = Field(default=True, alias="visible", description="Indica si la sección es visible para los estudiantes.")

class ModuloMoodle(BaseModel):
    id: int = Field(description="ID del módulo del curso (cmid).")
    url: Optional[HttpUrl] = Field(default=None, description="URL del módulo, si aplica (ej. para un recurso URL).")
    nombre: str = Field(alias="name", description="Nombre del módulo.")
    nombre_instancia: Optional[str] = Field(default=None, alias="instancename", description="Nombre de la instancia específica del módulo.")
    id_instancia: Optional[int] = Field(default=None, alias="instance", description="ID de la instancia del módulo.")
    tipo_mod: str = Field(alias="modname", description="Tipo de módulo (ej. 'folder', 'url', 'resource', 'page', 'assign').")
    nombre_plural_mod: Optional[str] = Field(default=None, alias="modplural", description="Nombre plural del tipo de módulo.")
    descripcion: Optional[str] = Field(default=None, description="Descripción del módulo (HTML).")
    visible: Optional[bool] = Field(default=True, description="Indica si el módulo es visible para los estudiantes.")

class ArchivoMoodle(BaseModel):
    tipo: str = Field(alias="type", description="Tipo de contenido, usualmente 'file'.")
    nombre_archivo: str = Field(alias="filename", description="Nombre del archivo.")
    ruta_archivo: str = Field(alias="filepath", description="Ruta del archivo dentro de Moodle.")
    tamano_archivo: int = Field(alias="filesize", description="Tamaño del archivo en bytes.")
    url_archivo: HttpUrl = Field(alias="fileurl", description="URL para descargar el archivo.")
    tiempo_modificacion: int = Field(alias="timemodified", description="Timestamp de última modificación.")
    autor: Optional[str] = Field(default=None, alias="author", description="Autor del archivo.")
    licencia: Optional[str] = Field(default=None, alias="license", description="Licencia del archivo.")

class ConfiguracionN8NCursoMoodle(BaseModel):
    mensajes_iniciales: Optional[str] = Field(default=None, description="Mensajes iniciales para mostrar en el chat.")
    anexo_mensaje_sistema: Optional[str] = Field(default=None, description="Texto para añadir al mensaje de sistema del agente IA.")
    titulo_chat: Optional[str] = Field(default=None, description="Título a mostrar en la ventana de chat.")
    placeholder_entrada: Optional[str] = Field(default=None, description="Texto placeholder para la caja de entrada del chat.")
    class Config:
        extra = "ignore"

# --- Modelos para N8N ---

class ParametrosNodoN8N(BaseModel):
    initialMessages: Optional[str] = None
    options: Optional[Dict[str, Any]] = Field(default_factory=dict)
    public: Optional[bool] = None
    webhookId: Optional[str] = None
    mode: Optional[str] = None
    toolName: Optional[str] = None
    toolDescription: Optional[str] = None
    tableName: Optional[str] = None
    modelName: Optional[str] = None
    model: Optional[str] = None
    baseUrl: Optional[HttpUrl] = None
    class Config:
        extra = "allow"
        alias_generator = lambda string: string
        populate_by_name = True

class NodoN8N(BaseModel):
    id: str = Field(description="ID único del nodo en el flujo.")
    name: str = Field(description="Nombre del nodo mostrado en la UI de N8N.")
    type: str = Field(description="Tipo de nodo.")
    typeVersion: float = Field(description="Versión del tipo de nodo.")
    position: List[float] = Field(description="Coordenadas [x, y] del nodo.")
    parameters: ParametrosNodoN8N = Field(default_factory=ParametrosNodoN8N, description="Parámetros del nodo.")
    credentials: Optional[Dict[str, Any]] = Field(default=None, description="Credenciales asociadas al nodo.")

class FlujoTrabajoN8N(BaseModel):
    id: Optional[str] = Field(default=None, description="ID del flujo de trabajo en N8N.")
    name: str = Field(description="Nombre del flujo de trabajo.")
    active: bool = Field(default=False, description="Indica si el flujo está activo.")
    nodes: List[NodoN8N] = Field(default_factory=list, description="Lista de nodos del flujo.")
    connections: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Conexiones entre nodos.")
    settings: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Configuraciones del flujo.")
    staticData: Optional[Dict[str, Any]] = Field(default=None, description="Datos estáticos del flujo.")
    meta: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Metadatos del flujo.")
    tags: Optional[List[str]] = Field(default_factory=list, description="Etiquetas del flujo.")

# --- Modelos para PgVector / Almacenamiento de Vectores ---

class FragmentoDocumento(BaseModel):
    id_fragmento: str = Field(default_factory=lambda: str(uuid.uuid4()), description="ID único del fragmento.")
    id_curso: int = Field(description="ID del curso al que pertenece el fragmento.")
    id_documento: str = Field(description="Identificador del documento original.")
    texto: str = Field(description="Contenido textual del fragmento.")
    embedding: Optional[List[float]] = Field(default=None, description="Vector de embedding del fragmento.")
    metadatos: Dict[str, Any] = Field(default_factory=dict, description="Metadatos adicionales.")

# --- Modelos para Búsqueda ---

class SolicitudBusquedaContextual(BaseModel):
    """Cuerpo de la petición para una búsqueda contextual."""
    consulta: str = Field(description="Texto de la consulta o pregunta del usuario.")
    # Usar id_curso para ser consistente con otras operaciones y evitar ambigüedades con nombres de curso.
    id_curso: int = Field(description="ID del curso en el cual realizar la búsqueda.")
    limite: Optional[int] = Field(default=5, ge=1, le=20, description="Número máximo de resultados a devolver.")
    # Se podría añadir un filtro de id_documento si se quisiera buscar dentro de un archivo específico.

class ResultadoBusquedaItem(BaseModel):
    """Representa un ítem individual en los resultados de búsqueda."""
    id_fragmento: str = Field(description="ID del fragmento de documento relevante.")
    similitud: float = Field(description="Puntuación de similitud entre la consulta y el fragmento (mayor es mejor).")
    texto_fragmento: str = Field(description="Contenido textual del fragmento.")
    metadatos: Dict[str, Any] = Field(description="Metadatos asociados al fragmento (ej. nombre de archivo, título).")

class RespuestaBusqueda(BaseModel):
    """Respuesta devuelta por el endpoint de búsqueda contextual."""
    consulta_original: str = Field(description="La consulta original realizada por el usuario.")
    resultados: List[ResultadoBusquedaItem] = Field(description="Lista de fragmentos relevantes encontrados.")
    total_resultados: int = Field(description="Número total de resultados devueltos.")
    # Se podría añadir información adicional como el tiempo de búsqueda, etc.

# --- Modelos Generales de API ---

class RespuestaConfiguracionCurso(BaseModel):
    id_curso: int = Field(description="ID del curso procesado.")
    estado: str = Field(description="Estado de la configuración.")
    mensaje: str = Field(description="Mensaje descriptivo del resultado.")
    nombre_tabla_vectorial: Optional[str] = Field(default=None, description="Nombre de la tabla vectorial para este curso.")
    id_seccion_moodle: Optional[int] = Field(default=None, description="ID de la sección de Moodle para EntrenAI.")
    id_carpeta_moodle: Optional[int] = Field(default=None, description="ID del módulo carpeta en Moodle.")
    id_chat_moodle: Optional[int] = Field(default=None, description="ID del módulo URL del chat N8N en Moodle.")
    id_enlace_refresco_moodle: Optional[int] = Field(default=None, description="ID del módulo URL de refresco en Moodle.")
    url_chat_n8n: Optional[HttpUrl] = Field(default=None, description="URL del webhook del chat N8N.")

class ArchivoProcesado(BaseModel):
    nombre_archivo: str = Field(alias="nombre", description="Identificador único del archivo en Moodle.")
    ultima_modificacion_moodle: int = Field(description="Timestamp Unix de la última modificación en Moodle.")

class RespuestaEliminacionArchivo(BaseModel):
    mensaje: str = Field(description="Mensaje del resultado de la operación.")
    detalle: Optional[str] = Field(default=None, description="Detalles adicionales.")

class SolicitudProcesamientoArchivos(BaseModel):
    id_curso: int = Field(description="ID del curso de Moodle a procesar.")
    id_usuario: int = Field(description="ID del usuario de Moodle que inicia el procesamiento.")

class RespuestaEstadoTarea(BaseModel):
    id_tarea: str = Field(description="ID de la tarea Celery.")
    estado: str = Field(description="Estado de la tarea (ej. PENDING, SUCCESS).")
    resultado: Optional[Any] = Field(default=None, description="Resultado de la tarea si finalizó con éxito.")
    traceback: Optional[str] = Field(default=None, description="Traceback si la tarea falló.")

class ConfiguracionChatN8N(BaseModel):
    mensajes_iniciales: Optional[str] = Field(default=None, description="Mensajes de bienvenida del chat.")
    placeholder_entrada: Optional[str] = Field(default=None, description="Texto placeholder para la entrada del chat.")
    titulo_chat: Optional[str] = Field(default=None, description="Título de la ventana de chat.")
    mensaje_sistema_oculto: Optional[str] = Field(default=None, alias="mensaje_sistema", description="Mensaje de sistema para el agente IA.")
    class Config:
        populate_by_name = True

[end of entrenai_refactor/api/modelos.py]
