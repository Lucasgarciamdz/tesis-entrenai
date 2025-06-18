import logging  # Import standard logging to get a logger instance
import os
from typing import Optional

from dotenv import load_dotenv
from pydantic import BaseModel, Field

# Load environment variables from .env file
# This should be called once when the application starts.
# For modules, it's often placed at the top level or in an init function.
load_dotenv()

# Leer APP_ENV una vez para usarlo en default_factory
# Esto se ejecuta cuando el módulo config.py se carga por primera vez.
APP_ENV_VALUE = os.getenv("APP_ENV", "local").lower()
logging.info(
    f"Config module loaded. APP_ENV_VALUE = '{APP_ENV_VALUE}'"
)  # Log para confirmar

# Valores constantes para Pgvector
_PGVECTOR_HOST_LOCAL: str = "localhost"
_PGVECTOR_PORT_LOCAL: int = 5433
_PGVECTOR_HOST_DOCKER: str = "pgvector_db"
_PGVECTOR_PORT_DOCKER: int = 5432


def _get_default_pg_host():
    app_env = os.getenv("APP_ENV", "local").lower()
    if app_env == "docker":
        return _PGVECTOR_HOST_DOCKER
    return _PGVECTOR_HOST_LOCAL


def _get_default_pg_port():
    app_env = os.getenv("APP_ENV", "local").lower()
    if app_env == "docker":
        return _PGVECTOR_PORT_DOCKER
    return _PGVECTOR_PORT_LOCAL


class BaseConfig(BaseModel):
    """
    Base configuration class.
    Loads variables from environment.
    """

    log_level: str = Field(
        default_factory=lambda: os.getenv("LOG_LEVEL", "INFO").upper()
    )
    fastapi_host: str = Field(
        default_factory=lambda: os.getenv("FASTAPI_HOST", "0.0.0.0")
    )
    fastapi_port: int = Field(
        default_factory=lambda: int(os.getenv("FASTAPI_PORT", "8000"))
    )

    # Path configurations
    data_dir: str = Field(
        default_factory=lambda: os.getenv("DATA_DIR", "data")
    )  # Base directory for app data
    download_dir: str = Field(default="")  # Will be set in __post_init__

    # AI provider settings
    ai_provider: str = Field(
        default_factory=lambda: os.getenv("AI_PROVIDER", "ollama").lower()
    )  # "ollama" o "gemini"

    def __post_init__(self):
        # Ensure data directories exist
        self.download_dir = os.path.join(
            self.data_dir, os.getenv("DOWNLOAD_SUBDIR", "downloads")
        )
        os.makedirs(self.data_dir, exist_ok=True)
        os.makedirs(self.download_dir, exist_ok=True)
        # Directory for SQLite DB will be created by sqlite3 if it doesn't exist,
        # but its parent (data_dir) must exist.


class MoodleConfig(BaseConfig):
    """Moodle specific configurations."""

    url: Optional[str] = Field(default_factory=lambda: os.getenv("MOODLE_URL"))
    token: Optional[str] = Field(default_factory=lambda: os.getenv("MOODLE_TOKEN"))
    course_folder_name: str = Field(
        default_factory=lambda: os.getenv(
            "MOODLE_COURSE_FOLDER_NAME", "Entrenai Documents"
        )
    )
    refresh_link_name: str = Field(
        default_factory=lambda: os.getenv(
            "MOODLE_REFRESH_LINK_NAME", "Refresh Entrenai IA"
        )
    )
    chat_link_name: str = Field(
        default_factory=lambda: os.getenv(
            "MOODLE_CHAT_LINK_NAME", "Chat con Entrenai IA"
        )
    )
    default_teacher_id: Optional[int] = Field(
        default_factory=lambda: (
            int(val)
            if (val := os.getenv("MOODLE_DEFAULT_TEACHER_ID")) is not None
            and val.isdigit()
            else None
        )
    )

    def __post_init__(self):
        super().__post_init__()
        if not self.url or not self.token:
            logging.warning(
                "Advertencia: MOODLE_URL o MOODLE_TOKEN no están configurados en el entorno."
            )

        if self.default_teacher_id is None:
            logging.warning(
                "Advertencia: MOODLE_DEFAULT_TEACHER_ID no está configurado o no es un entero válido en el entorno."
            )


class PgvectorConfig(BaseConfig):
    """Pgvector specific configurations."""

    host: Optional[str] = Field(default_factory=_get_default_pg_host)
    port: Optional[int] = Field(default_factory=_get_default_pg_port)

    user: Optional[str] = Field(default_factory=lambda: os.getenv("PGVECTOR_USER"))
    password: Optional[str] = Field(
        default_factory=lambda: os.getenv("PGVECTOR_PASSWORD")
    )
    db_name: Optional[str] = Field(
        default_factory=lambda: os.getenv("PGVECTOR_DB_NAME")
    )
    collection_prefix: str = Field(
        default_factory=lambda: os.getenv(
            "PGVECTOR_COLLECTION_PREFIX", "entrenai_course_"
        )
    )
    default_vector_size: int = Field(
        default_factory=lambda: int(os.getenv("DEFAULT_VECTOR_SIZE", "384"))
    )

    def __post_init__(self):
        super().__post_init__()

        # host y port ya están establecidos por default_factory
        # El logging ahora puede confirmar los valores establecidos
        current_app_env = os.getenv(
            "APP_ENV", "local"
        ).lower()  # Re-evaluar aquí para el log
        log_message_details = (
            f"PgvectorConfig init: APP_ENV (current getenv)='{current_app_env}', "
            f"APP_ENV_VALUE (module level)='{APP_ENV_VALUE}', "  # Usar la variable global del módulo
            f"Host='{self.host}', Port='{self.port}', "
            f"User='{self.user}', DB_Name='{self.db_name}', "
            f"Password_is_set={'True' if self.password else 'False'}"
        )
        logging.info(log_message_details)

        # Validaciones
        if not self.host:
            logging.warning(
                "Advertencia: PGVECTOR_HOST no está configurado (valor final)."
            )
        if not self.port:  # Añadir validación para puerto también
            logging.warning(
                "Advertencia: PGVECTOR_PORT no está configurado (valor final)."
            )
        if not self.user:
            logging.warning(
                "Advertencia: PGVECTOR_USER no está configurado en el entorno."
            )
        if not self.password:
            logging.warning(
                "Advertencia: PGVECTOR_PASSWORD no está configurado en el entorno."
            )
        if not self.db_name:
            logging.warning(
                "Advertencia: PGVECTOR_DB_NAME no está configurado en el entorno."
            )


class OllamaConfig(BaseConfig):
    """Ollama specific configurations."""

    host: Optional[str] = Field(default_factory=lambda: os.getenv("OLLAMA_HOST"))
    embedding_model: str = Field(
        default_factory=lambda: os.getenv("OLLAMA_EMBEDDING_MODEL", "nomic-embed-text")
    )
    markdown_model: str = Field(
        default_factory=lambda: os.getenv("OLLAMA_MARKDOWN_MODEL", "llama3")
    )
    qa_model: str = Field(
        default_factory=lambda: os.getenv("OLLAMA_QA_MODEL", "llama3")
    )
    context_model: str = Field(
        default_factory=lambda: os.getenv("OLLAMA_CONTEXT_MODEL", "llama3")
    )

    def __post_init__(self):
        super().__post_init__()
        if not self.host:
            logging.warning(
                "Advertencia: OLLAMA_HOST no está configurado en el entorno."
            )


class GeminiConfig(BaseConfig):
    """Google Gemini API specific configurations."""

    api_key: Optional[str] = Field(default_factory=lambda: os.getenv("GEMINI_API_KEY"))
    embedding_model: str = Field(
        default_factory=lambda: os.getenv("GEMINI_EMBEDDING_MODEL", "embedding-001")
    )
    text_model: str = Field(
        default_factory=lambda: os.getenv("GEMINI_TEXT_MODEL", "gemini-1.5-flash")
    )
    vision_model: str = Field(
        default_factory=lambda: os.getenv(
            "GEMINI_VISION_MODEL", "gemini-1.5-pro-vision"
        )
    )
    embedding_dimension: int = Field(
        default_factory=lambda: int(os.getenv("GEMINI_EMBEDDING_DIMENSION", "1024"))
    )

    # Configuración de safety settings (opcional, usando valores por defecto)
    safety_settings_enabled: bool = Field(
        default_factory=lambda: (
            os.getenv("GEMINI_SAFETY_SETTINGS_ENABLED", "True").lower() == "true"
        )
    )

    def __post_init__(self):
        super().__post_init__()
        if not self.api_key:
            logging.warning(
                "Advertencia: GEMINI_API_KEY no está configurado en el entorno. El proveedor Gemini no estará disponible."
            )


class N8NConfig(BaseConfig):
    """N8N specific configurations."""

    url: Optional[str] = Field(default_factory=lambda: os.getenv("N8N_URL"))
    webhook_url: Optional[str] = Field(
        default_factory=lambda: os.getenv("N8N_WEBHOOK_URL")
    )  # URL N8N uses for its own webhooks
    api_key: Optional[str] = Field(
        default_factory=lambda: os.getenv("N8N_API_KEY")
    )  # For N8N's REST API, if secured
    chat_workflow_id: Optional[str] = Field(
        default_factory=lambda: os.getenv("N8N_CHAT_WORKFLOW_ID")
    )  # Might be deprecated if we import by JSON path
    workflow_json_path: Optional[str] = Field(
        default_factory=lambda: os.getenv(
            "N8N_WORKFLOW_JSON_PATH", "src/entrenai/n8n_workflow.json"
        )
    )
    # N8N_ENCRYPTION_KEY is used by N8N itself, not directly by our app typically

    def __post_init__(self):
        super().__post_init__()
        if not self.url:
            logging.warning("Advertencia: N8N_URL no está configurado en el entorno.")


# Valores constantes para Redis
_REDIS_HOST_LOCAL: str = "localhost"
_REDIS_PORT: int = 6379
_REDIS_HOST_DOCKER: str = "redis"


def _get_default_redis_host():
    app_env = os.getenv("APP_ENV", "local").lower()
    if app_env == "docker":
        return _REDIS_HOST_DOCKER
    return _REDIS_HOST_LOCAL


def _get_default_redis_url():
    host = _get_default_redis_host()
    return f"redis://{host}:{_REDIS_PORT}/0"


class CeleryConfig(BaseConfig):
    """Celery specific configurations."""

    broker_url: str = Field(
        default_factory=lambda: os.getenv(
            "CELERY_BROKER_URL", _get_default_redis_url()
        )
    )
    result_backend: str = Field(
        default_factory=lambda: os.getenv(
            "CELERY_RESULT_BACKEND", _get_default_redis_url()
        )
    )
    # Consider adding other Celery settings if needed, e.g., task visibility timeout

    def __post_init__(self):
        super().__post_init__()


# Instantiate configurations for easy import elsewhere
# This makes them singletons for the application's lifecycle
base_config = BaseConfig()
moodle_config = MoodleConfig()
pgvector_config = PgvectorConfig()
ollama_config = OllamaConfig()
gemini_config = GeminiConfig()
n8n_config = N8NConfig()
celery_config = CeleryConfig()

# Example of how to use:
# from entrenai.config import moodle_config
# print(moodle_config.url)
