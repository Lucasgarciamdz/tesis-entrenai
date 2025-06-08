import os
from functools import lru_cache
from typing import Optional, Union # Union para campos que pueden ser None por default_factory

from dotenv import load_dotenv
from pydantic import BaseModel, Field, HttpUrl

# Importar el registrador para los mensajes de creación de directorios
from .registrador import obtener_registrador # Usar import relativo dentro del mismo paquete

registrador_config = obtener_registrador(__name__) # Logger específico para este módulo

# Carga las variables de entorno desde un archivo .env.
# Esta ruta está configurada para buscar '.env' en el directorio raíz de 'entrenai_refactor',
# asumiendo que este archivo (configuracion.py) se encuentra en 'entrenai_refactor/config/'.
# Path: entrenai_refactor/config/../.env  => entrenai_refactor/.env
ruta_archivo_dotenv = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env")
if os.path.exists(ruta_archivo_dotenv):
    load_dotenv(dotenv_path=ruta_archivo_dotenv)
    registrador_config.debug(f"Archivo .env cargado desde: {ruta_archivo_dotenv}")
else:
    registrador_config.warning(f"Archivo .env no encontrado en la ruta esperada: {ruta_archivo_dotenv}. Se usarán valores por defecto o variables de entorno del sistema.")

# --- Funciones Auxiliares para Conversión de Tipos desde Variables de Entorno ---

def _aux_obtener_entorno_como_entero(clave_env: str, valor_por_defecto: int) -> int:
    """
    Obtiene una variable de entorno como un entero.
    Si la variable no está definida o no es un entero válido, devuelve el valor por defecto.
    """
    valor_str = os.getenv(clave_env)
    if valor_str and valor_str.isdigit():
        return int(valor_str)
    registrador_config.debug(f"Variable de entorno '{clave_env}' no encontrada o no es un entero válido. Usando valor por defecto: {valor_por_defecto}.")
    return valor_por_defecto

def _aux_obtener_entorno_opcional_como_entero(clave_env: str) -> Optional[int]:
    """
    Obtiene una variable de entorno opcional como un entero.
    Devuelve None si la variable no está definida o no es un entero válido.
    """
    valor_str = os.getenv(clave_env)
    if valor_str and valor_str.isdigit():
        return int(valor_str)
    registrador_config.debug(f"Variable de entorno opcional '{clave_env}' no encontrada o no es un entero válido. Devolviendo None.")
    return None

def _aux_obtener_entorno_como_booleano(clave_env: str, valor_por_defecto: bool) -> bool:
    """
    Obtiene una variable de entorno como un booleano.
    Interpreta 'true', '1', 'yes', 'on' (insensible a mayúsculas) como True.
    Cualquier otro valor (o si no está definida) resulta en el valor por defecto o False si el valor por defecto es False.
    """
    valor_str = os.getenv(clave_env, str(valor_por_defecto)).lower()
    return valor_str in ("true", "1", "yes", "on")

# --- Modelos Pydantic para Secciones de Configuración Anidadas ---

class _ConfiguracionAnidadaMoodle(BaseModel):
    """Configuraciones específicas para la integración con la plataforma Moodle."""
    url_moodle: Optional[str] = Field(default_factory=lambda: os.getenv("MOODLE_URL"), description="URL base de la instancia de Moodle.")
    token_api_moodle: Optional[str] = Field(default_factory=lambda: os.getenv("MOODLE_TOKEN"), description="Token de API para los servicios web de Moodle.")
    nombre_carpeta_recursos_ia: str = Field(
        default_factory=lambda: os.getenv("MOODLE_COURSE_FOLDER_NAME", "EntrenAI - Recursos IA"), # Nombre más descriptivo
        description="Nombre de la carpeta que se creará/utilizará en los cursos de Moodle para almacenar los archivos de la IA."
    )
    nombre_enlace_refrescar_ia: str = Field(
        default_factory=lambda: os.getenv("MOODLE_REFRESH_LINK_NAME", "Actualizar Contenido IA"),
        description="Texto del enlace en Moodle para que los profesores disparen la actualización/refresco de la IA del curso."
    )
    nombre_enlace_chat_ia: str = Field(
        default_factory=lambda: os.getenv("MOODLE_CHAT_LINK_NAME", "Chatear con IA del Curso"),
        description="Texto del enlace en Moodle para que los usuarios accedan al chat con la IA del curso."
    )
    id_profesor_por_defecto: Optional[int] = Field(
        default_factory=lambda: _aux_obtener_entorno_opcional_como_entero("MOODLE_DEFAULT_TEACHER_ID"),
        description="ID del usuario de Moodle (generalmente un profesor o administrador) que se usará por defecto para ciertas operaciones que requieren un contexto de usuario (ej. listar cursos, tareas asíncronas)."
    )

class _ConfiguracionAnidadaPostgres(BaseModel):
    """Configuraciones para la conexión a la base de datos PostgreSQL con la extensión pgvector."""
    usuario_db: Optional[str] = Field(default_factory=lambda: os.getenv("PGVECTOR_USER"), description="Nombre de usuario para la conexión a la base de datos PostgreSQL.")
    contrasena_db: Optional[str] = Field(default_factory=lambda: os.getenv("PGVECTOR_PASSWORD"), description="Contraseña para el usuario de la base de datos PostgreSQL.")
    host_db: str = Field(
        default_factory=lambda: os.getenv("PGVECTOR_HOST", "pgvector_db" if os.getenv("ENTORNO_APP") == "docker" else "localhost"),
        description="Host o dirección IP del servidor de la base de datos PostgreSQL."
    )
    puerto_db: int = Field(
        default_factory=lambda: _aux_obtener_entorno_como_entero("PGVECTOR_PORT", 5432 if os.getenv("ENTORNO_APP") == "docker" else 5433),
        description="Puerto en el que escucha el servidor de la base de datos PostgreSQL."
    )
    nombre_base_datos: Optional[str] = Field(default_factory=lambda: os.getenv("PGVECTOR_DB_NAME"), description="Nombre de la base de datos específica a la que conectarse.")
    prefijo_tabla_cursos_vectorial: str = Field( # Renombrado para claridad
        default_factory=lambda: os.getenv("PGVECTOR_COLLECTION_PREFIX", "entrenai_vectores_curso_"), # Prefijo más descriptivo
        description="Prefijo utilizado para nombrar las tablas (colecciones) de vectores de cada curso en la base de datos."
    )
    dimension_embedding_defecto: int = Field( # Renombrado para claridad
        default_factory=lambda: _aux_obtener_entorno_como_entero("DEFAULT_VECTOR_SIZE", 768), # Ejemplo de tamaño común, ajustar
        description="Dimensión (tamaño) por defecto de los vectores de embedding que se almacenarán. Debe coincidir con el modelo de embedding usado."
    )

class _ConfiguracionAnidadaOllama(BaseModel):
    """Configuraciones para interactuar con un servidor Ollama como proveedor de IA."""
    host_ollama: Optional[str] = Field(default_factory=lambda: os.getenv("OLLAMA_HOST"), description="URL completa del host donde se ejecuta el servidor Ollama (ej. http://localhost:11434).")
    modelo_embedding_ollama: str = Field(default_factory=lambda: os.getenv("OLLAMA_EMBEDDING_MODEL", "nomic-embed-text"), description="Nombre del modelo de Ollama a utilizar para generar embeddings.")
    modelo_markdown_ollama: str = Field(default_factory=lambda: os.getenv("OLLAMA_MARKDOWN_MODEL", "llama3:8b"), description="Nombre del modelo de Ollama para tareas de formateo a Markdown.")
    modelo_qa_ollama: str = Field(default_factory=lambda: os.getenv("OLLAMA_QA_MODEL", "llama3:8b"), description="Nombre del modelo de Ollama para tareas de preguntas y respuestas (chat).")
    modelo_contexto_ollama: str = Field(default_factory=lambda: os.getenv("OLLAMA_CONTEXT_MODEL", "llama3:8b"), description="Nombre del modelo de Ollama para tareas de análisis o enriquecimiento de contexto (si se usa explícitamente).")

class _ConfiguracionAnidadaGemini(BaseModel):
    """Configuraciones para interactuar con la API de Google Gemini como proveedor de IA."""
    clave_api_gemini: Optional[str] = Field(default_factory=lambda: os.getenv("GEMINI_API_KEY"), description="Clave API para acceder a los servicios de Google Gemini.")
    modelo_embedding_gemini: str = Field(default_factory=lambda: os.getenv("GEMINI_EMBEDDING_MODEL", "models/embedding-001"), description="Nombre/ID del modelo de Gemini a utilizar para generar embeddings.")
    modelo_texto_gemini: str = Field(default_factory=lambda: os.getenv("GEMINI_TEXT_MODEL", "gemini-1.5-flash-latest"), description="Nombre/ID del modelo de Gemini para tareas generales de texto y chat.")
    # modelo_vision_gemini: str = Field(default_factory=lambda: os.getenv("GEMINI_VISION_MODEL", "gemini-pro-vision"), description="Nombre/ID del modelo de Gemini para tareas que involucran visión (procesamiento de imágenes).") # Descomentar si se usa
    seguridad_gemini_habilitada: bool = Field(
        default_factory=lambda: _aux_obtener_entorno_como_booleano("GEMINI_SAFETY_SETTINGS_ENABLED", True),
        description="Indica si se deben aplicar los filtros de seguridad predeterminados de Google Gemini en las respuestas."
    )

class _ConfiguracionAnidadaN8N(BaseModel):
    """Configuraciones para la integración con la plataforma de automatización N8N."""
    url_n8n: Optional[str] = Field(default_factory=lambda: os.getenv("N8N_URL"), description="URL base de la instancia de N8N (ej. http://localhost:5678).")
    url_webhook_chat_n8n: Optional[str] = Field(default_factory=lambda: os.getenv("N8N_WEBHOOK_URL"), description="URL base para los webhooks de N8N (puede ser la misma que N8N_URL o una específica si N8N está detrás de un proxy).")
    clave_api_n8n: Optional[str] = Field(default_factory=lambda: os.getenv("N8N_API_KEY"), description="Clave API para interactuar con la API REST de N8N.")
    # id_flujo_chat_n8n: Optional[str] = Field(default_factory=lambda: os.getenv("N8N_CHAT_WORKFLOW_ID"), description="ID de un flujo de trabajo de chat preexistente en N8N (opcional, la aplicación puede crear flujos).") # Comentado, ya que la app crea el flujo
    ruta_plantilla_flujo_n8n: str = Field(
        default_factory=lambda: os.getenv("N8N_WORKFLOW_JSON_PATH", "nucleo/clientes/plantillas_n8n/flujo_n8n.json"),
        description="Ruta relativa al archivo JSON que contiene la plantilla del flujo de chat de N8N. La ruta es relativa a la raíz del proyecto 'entrenai_refactor'."
    )

class _ConfiguracionAnidadaCelery(BaseModel):
    """Configuraciones para Celery, el sistema de colas de tareas asíncronas."""
    url_broker_celery: str = Field(default_factory=lambda: os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0"), description="URL del broker de mensajes para Celery (ej. Redis o RabbitMQ).")
    backend_resultados_celery: str = Field(default_factory=lambda: os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/0"), description="URL del backend donde Celery almacena los resultados de las tareas.")

# --- Clase Principal de Configuración de la Aplicación ---

class ConfiguracionPrincipal(BaseModel):
    """
    Agrupa todas las configuraciones de la aplicación EntrenAI en un único objeto accesible globalmente.
    Carga valores desde variables de entorno y/o un archivo .env.
    """
    # Configuración general de la aplicación
    entorno_aplicacion: str = Field(default_factory=lambda: os.getenv("APP_ENV", "local").lower(), description="Entorno de ejecución de la aplicación (ej. 'local', 'desarrollo', 'produccion', 'docker'). Impacta la carga de ciertas configuraciones.")
    nivel_registro_log: str = Field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO").upper(), description="Nivel de detalle para los logs de la aplicación (ej. DEBUG, INFO, WARNING, ERROR).")
    host_api_fastapi: str = Field(default_factory=lambda: os.getenv("FASTAPI_HOST", "0.0.0.0"), description="Host en el que la API de FastAPI escuchará peticiones.")
    puerto_api_fastapi: int = Field(default_factory=lambda: _aux_obtener_entorno_como_entero("FASTAPI_PORT", 8000), description="Puerto en el que la API de FastAPI escuchará peticiones.")
    timezone_app: Optional[str] = Field(default_factory=lambda: os.getenv("TIMEZONE", "Europe/Madrid"), description="Zona horaria para la aplicación (ej. 'Europe/Madrid', 'America/Bogota').")


    # Directorios de datos
    # Ruta base para almacenar datos generados por la aplicación (relativa a la raíz de 'entrenai_refactor').
    directorio_base_datos_app: str = Field(default_factory=lambda: os.getenv("DATA_DIR", "datos_app"), description="Directorio base para datos de la aplicación (ej. archivos Markdown generados, descargas temporales), relativo a la raíz de 'entrenai_refactor'.")

    @property
    def ruta_absoluta_directorio_datos(self) -> Path:
        """Devuelve la ruta absoluta al directorio de datos base de la aplicación."""
        # Este archivo (configuracion.py) está en entrenai_refactor/config/
        # Para llegar a la raíz de 'entrenai_refactor', subimos un nivel desde 'config'.
        raiz_proyecto_entrenai_refactor = Path(__file__).resolve().parent.parent
        return raiz_proyecto_entrenai_refactor / self.directorio_base_datos_app

    @property
    def ruta_absoluta_directorio_descargas(self) -> Path:
        """Devuelve la ruta absoluta al subdirectorio específico para descargas (ej. archivos de Moodle)."""
        subdirectorio_descargas_config = os.getenv("DOWNLOAD_SUBDIR", "descargas_temporales")
        return self.ruta_absoluta_directorio_datos / subdirectorio_descargas_config

    # Proveedor de IA configurado
    proveedor_ia_seleccionado: str = Field(default_factory=lambda: os.getenv("AI_PROVIDER", "ollama").lower(), description="Proveedor de Inteligencia Artificial a utilizar: 'ollama' o 'gemini'.")

    # Secciones de configuración anidadas
    moodle: _ConfiguracionAnidadaMoodle = Field(default_factory=_ConfiguracionAnidadaMoodle)
    db: _ConfiguracionAnidadaPostgres = Field(default_factory=_ConfiguracionAnidadaPostgres) # 'db' es un nombre común para config de BD
    ollama: _ConfiguracionAnidadaOllama = Field(default_factory=_ConfiguracionAnidadaOllama)
    gemini: _ConfiguracionAnidadaGemini = Field(default_factory=_ConfiguracionAnidadaGemini)
    n8n: _ConfiguracionAnidadaN8N = Field(default_factory=_ConfiguracionAnidadaN8N)
    celery: _ConfiguracionAnidadaCelery = Field(default_factory=_ConfiguracionAnidadaCelery)


# --- Función Singleton para Obtener la Configuración Global ---

@lru_cache() # Asegura que la configuración se cargue una sola vez
def obtener_configuracion_global() -> ConfiguracionPrincipal:
    """
    Crea y devuelve una instancia única de la configuración principal de la aplicación.
    Utiliza `lru_cache` para implementar el patrón Singleton, asegurando que la configuración
    se parsea y valida una sola vez durante el ciclo de vida de la aplicación.

    Returns:
        ConfiguracionPrincipal: El objeto de configuración global de la aplicación.
    """
    registrador_config.info("Creando instancia de ConfiguracionPrincipal (debería ocurrir una vez).")
    return ConfiguracionPrincipal()

# Instancia global única de la configuración, accesible desde otros módulos.
configuracion_global: ConfiguracionPrincipal = obtener_configuracion_global()

# --- Creación de Directorios Necesarios al Iniciar ---
# Esta sección se ejecuta una vez cuando este módulo (configuracion.py) es importado por primera vez.
# Asegura que los directorios base para datos y descargas existan.
try:
    ruta_datos = configuracion_global.ruta_absoluta_directorio_datos
    ruta_descargas = configuracion_global.ruta_absoluta_directorio_descargas

    if not ruta_datos.exists():
        ruta_datos.mkdir(parents=True, exist_ok=True)
        registrador_config.info(f"Directorio de datos base creado en: {ruta_datos}")
    else:
        registrador_config.debug(f"Directorio de datos base ya existe en: {ruta_datos}")

    if not ruta_descargas.exists():
        ruta_descargas.mkdir(parents=True, exist_ok=True)
        registrador_config.info(f"Directorio de descargas creado en: {ruta_descargas}")
    else:
        registrador_config.debug(f"Directorio de descargas ya existe en: {ruta_descargas}")
except Exception as e_dir:
    registrador_config.error(f"Error al crear directorios base durante la inicialización de la configuración: {e_dir}")
    # Considerar si este error debe ser fatal para la aplicación.
    # Por ahora, solo se loguea.

[end of entrenai_refactor/config/configuracion.py]
