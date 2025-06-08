import os
from functools import lru_cache
from typing import Optional, Callable

from dotenv import load_dotenv
from pydantic import BaseModel, Field

# Carga las variables de entorno desde un archivo .env si existe.
load_dotenv()

# --- Funciones Auxiliares para Conversión de Tipos ---

def _get_env_int(key: str, default: int) -> int:
    """Obtiene una variable de entorno como entero."""
    return int(os.getenv(key, default))

def _get_env_optional_int(key: str) -> Optional[int]:
    """Obtiene una variable de entorno opcional como entero."""
    value = os.getenv(key)
    return int(value) if value and value.isdigit() else None

def _get_env_bool(key: str, default: bool) -> bool:
    """Obtiene una variable de entorno como booleano."""
    return os.getenv(key, str(default)).lower() == "true"

# --- Modelos de Configuración Anidados ---

class _ConfiguracionMoodle(BaseModel):
    """Configuraciones para la integración con Moodle."""
    url: Optional[str] = Field(default_factory=lambda: os.getenv("MOODLE_URL"), description="URL de la instancia de Moodle.")
    token: Optional[str] = Field(default_factory=lambda: os.getenv("MOODLE_TOKEN"), description="Token de API para Moodle.")
    nombre_carpeta_curso: str = Field(
        default_factory=lambda: os.getenv("MOODLE_COURSE_FOLDER_NAME", "Documentos Entrenai"),
        description="Nombre de la carpeta donde se almacenan los documentos en el curso."
    )
    nombre_enlace_refrescar: str = Field(
        default_factory=lambda: os.getenv("MOODLE_REFRESH_LINK_NAME", "Refrescar IA Entrenai"),
        description="Texto del enlace para disparar la actualización de la IA."
    )
    nombre_enlace_chat: str = Field(
        default_factory=lambda: os.getenv("MOODLE_CHAT_LINK_NAME", "Chat con IA Entrenai"),
        description="Texto del enlace para acceder al chatbot."
    )
    id_profesor_defecto: Optional[int] = Field(
        default_factory=lambda: _get_env_optional_int("MOODLE_DEFAULT_TEACHER_ID"),
        description="ID del profesor por defecto para ciertas operaciones."
    )

class _ConfiguracionPostgres(BaseModel):
    """Configuraciones para la base de datos vectorial (PostgreSQL con pgvector)."""
    usuario: Optional[str] = Field(default_factory=lambda: os.getenv("PGVECTOR_USER"), description="Usuario de la base de datos.")
    contrasena: Optional[str] = Field(default_factory=lambda: os.getenv("PGVECTOR_PASSWORD"), description="Contraseña de la base de datos.")
    host: str = Field(
        default_factory=lambda: os.getenv("PGVECTOR_HOST", "pgvector_db" if os.getenv("APP_ENV") == "docker" else "localhost"),
        description="Host de la base de datos."
    )
    puerto: int = Field(
        default_factory=lambda: _get_env_int("PGVECTOR_PORT", 5432 if os.getenv("APP_ENV") == "docker" else 5433),
        description="Puerto de la base de datos."
    )
    nombre_bd: Optional[str] = Field(default_factory=lambda: os.getenv("PGVECTOR_DB_NAME"), description="Nombre de la base de datos.")
    prefijo_coleccion: str = Field(
        default_factory=lambda: os.getenv("PGVECTOR_COLLECTION_PREFIX", "entrenai_curso_"),
        description="Prefijo para los nombres de las colecciones (tablas) de cada curso."
    )
    tamano_vector_defecto: int = Field(
        default_factory=lambda: _get_env_int("DEFAULT_VECTOR_SIZE", 384),
        description="Tamaño de los vectores de embedding por defecto."
    )

class _ConfiguracionOllama(BaseModel):
    """Configuraciones para el proveedor de IA Ollama."""
    host: Optional[str] = Field(default_factory=lambda: os.getenv("OLLAMA_HOST"), description="Host del servidor Ollama.")
    modelo_embedding: str = Field(default_factory=lambda: os.getenv("OLLAMA_EMBEDDING_MODEL", "nomic-embed-text"), description="Modelo para generar embeddings.")
    modelo_markdown: str = Field(default_factory=lambda: os.getenv("OLLAMA_MARKDOWN_MODEL", "llama3"), description="Modelo para procesar Markdown.")
    modelo_qa: str = Field(default_factory=lambda: os.getenv("OLLAMA_QA_MODEL", "llama3"), description="Modelo para preguntas y respuestas.")
    modelo_contexto: str = Field(default_factory=lambda: os.getenv("OLLAMA_CONTEXT_MODEL", "llama3"), description="Modelo para análisis de contexto.")

class _ConfiguracionGemini(BaseModel):
    """Configuraciones para el proveedor de IA Google Gemini."""
    clave_api: Optional[str] = Field(default_factory=lambda: os.getenv("GEMINI_API_KEY"), description="Clave de API para Google Gemini.")
    modelo_embedding: str = Field(default_factory=lambda: os.getenv("GEMINI_EMBEDDING_MODEL", "embedding-001"), description="Modelo para generar embeddings.")
    modelo_texto: str = Field(default_factory=lambda: os.getenv("GEMINI_TEXT_MODEL", "gemini-1.5-flash"), description="Modelo para tareas de texto.")
    modelo_vision: str = Field(default_factory=lambda: os.getenv("GEMINI_VISION_MODEL", "gemini-1.5-pro-vision"), description="Modelo para tareas de visión.")
    dimension_embedding: int = Field(default_factory=lambda: _get_env_int("GEMINI_EMBEDDING_DIMENSION", 1024), description="Dimensión de los embeddings de Gemini.")
    seguridad_habilitada: bool = Field(
        default_factory=lambda: _get_env_bool("GEMINI_SAFETY_SETTINGS_ENABLED", True),
        description="Indica si se aplican los filtros de seguridad de Gemini."
    )

class _ConfiguracionN8N(BaseModel):
    """Configuraciones para la integración con n8n."""
    url: Optional[str] = Field(default_factory=lambda: os.getenv("N8N_URL"), description="URL base de la instancia de n8n.")
    url_webhook: Optional[str] = Field(default_factory=lambda: os.getenv("N8N_WEBHOOK_URL"), description="URL del webhook de n8n para el chat.")
    clave_api: Optional[str] = Field(default_factory=lambda: os.getenv("N8N_API_KEY"), description="Clave de API para n8n.")
    id_flujo_chat: Optional[str] = Field(default_factory=lambda: os.getenv("N8N_CHAT_WORKFLOW_ID"), description="ID del flujo de trabajo de chat en n8n.")
    ruta_json_flujo: str = Field(
        default_factory=lambda: os.getenv("N8N_WORKFLOW_JSON_PATH", "entrenai2/flujo_n8n.json"),
        description="Ruta al archivo JSON que contiene la plantilla del flujo de n8n."
    )

class _ConfiguracionCelery(BaseModel):
    """Configuraciones para Celery."""
    url_broker: str = Field(default_factory=lambda: os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0"), description="URL del broker de mensajes (Redis).")
    backend_resultado: str = Field(default_factory=lambda: os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/0"), description="URL del backend de resultados (Redis).")


# --- Clase de Configuración Principal ---

class Configuracion(BaseModel):
    """
    Agrupa todas las configuraciones de la aplicación en un único objeto.
    """
    entorno: str = Field(default_factory=lambda: os.getenv("APP_ENV", "local").lower(), description="Entorno de ejecución (local o docker).")
    nivel_log: str = Field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO").upper(), description="Nivel de los logs (INFO, DEBUG, etc.).")
    host_api: str = Field(default_factory=lambda: os.getenv("FASTAPI_HOST", "0.0.0.0"), description="Host para la API de FastAPI.")
    puerto_api: int = Field(default_factory=lambda: _get_env_int("FASTAPI_PORT", 8000), description="Puerto para la API de FastAPI.")
    directorio_datos: str = Field(default_factory=lambda: os.getenv("DATA_DIR", "entrenai2/api/datos"), description="Directorio base para datos.")
    
    @property
    def directorio_descargas(self) -> str:
        """Ruta completa al directorio de descargas."""
        return os.path.join(self.directorio_datos, "descargas")

    proveedor_ia: str = Field(default_factory=lambda: os.getenv("AI_PROVIDER", "ollama").lower(), description="Proveedor de IA a utilizar (ollama o gemini).")

    moodle: _ConfiguracionMoodle = Field(default_factory=_ConfiguracionMoodle)
    db: _ConfiguracionPostgres = Field(default_factory=_ConfiguracionPostgres)
    ollama: _ConfiguracionOllama = Field(default_factory=_ConfiguracionOllama)
    gemini: _ConfiguracionGemini = Field(default_factory=_ConfiguracionGemini)
    n8n: _ConfiguracionN8N = Field(default_factory=_ConfiguracionN8N)
    celery: _ConfiguracionCelery = Field(default_factory=_ConfiguracionCelery)


# --- Función para obtener la configuración ---

@lru_cache()
def obtener_configuracion() -> Configuracion:
    """
    Crea y devuelve una instancia única de la configuración de la aplicación.
    Utiliza lru_cache para asegurar que la configuración se cargue una sola vez.
    
    Returns:
        Configuracion: El objeto de configuración de la aplicación.
    """
    return Configuracion()

# Instancia global para facilitar la importación en otros módulos
config = obtener_configuracion()
