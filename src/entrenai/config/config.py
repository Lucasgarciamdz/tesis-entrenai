import os
from dotenv import load_dotenv
from typing import Optional
import logging  # Import standard logging to get a logger instance

# Load environment variables from .env file
# This should be called once when the application starts.
# For modules, it's often placed at the top level or in an init function.
load_dotenv()


class BaseConfig:
    """
    Base configuration class.
    Loads variables from environment.
    """

    def __init__(self):
        # General application settings
        self.log_level: str = os.getenv("LOG_LEVEL", "INFO").upper()
        self.fastapi_host: str = os.getenv("FASTAPI_HOST", "0.0.0.0")
        self.fastapi_port: int = int(os.getenv("FASTAPI_PORT", "8000"))

        # Path configurations
        self.data_dir: str = os.getenv(
            "DATA_DIR", "data"
        )  # Base directory for app data
        self.download_dir: str = os.path.join(
            self.data_dir, os.getenv("DOWNLOAD_SUBDIR", "downloads")
        )

        # AI provider settings
        self.ai_provider: str = os.getenv(
            "AI_PROVIDER", "ollama"
        ).lower()  # "ollama" o "gemini"

        # Ensure data directories exist
        os.makedirs(self.data_dir, exist_ok=True)
        os.makedirs(self.download_dir, exist_ok=True)
        # Directory for SQLite DB will be created by sqlite3 if it doesn't exist,
        # but its parent (data_dir) must exist.


class MoodleConfig(BaseConfig):
    """Moodle specific configurations."""

    def __init__(self):
        super().__init__()
        self.url: Optional[str] = os.getenv("MOODLE_URL")
        self.token: Optional[str] = os.getenv("MOODLE_TOKEN")
        self.course_folder_name: str = os.getenv(
            "MOODLE_COURSE_FOLDER_NAME", "Entrenai Documents"
        )
        self.refresh_link_name: str = os.getenv(
            "MOODLE_REFRESH_LINK_NAME", "Refresh Entrenai IA"
        )
        self.chat_link_name: str = os.getenv(
            "MOODLE_CHAT_LINK_NAME", "Chat con Entrenai IA"
        )
        self.default_teacher_id: Optional[int] = (
            int(val)
            if (val := os.getenv("MOODLE_DEFAULT_TEACHER_ID")) is not None
            and val.isdigit()
            else None
        )

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

    def __init__(self):
        super().__init__()
        self.host: Optional[str] = os.getenv("PGVECTOR_HOST")
        self.port: Optional[int] = int(os.getenv("PGVECTOR_PORT", "5432"))
        self.user: Optional[str] = os.getenv("PGVECTOR_USER")
        self.password: Optional[str] = os.getenv("PGVECTOR_PASSWORD")
        self.db_name: Optional[str] = os.getenv("PGVECTOR_DB_NAME")
        self.collection_prefix: str = os.getenv(
            "PGVECTOR_COLLECTION_PREFIX", "entrenai_course_"
        )
        self.default_vector_size: int = int(os.getenv("DEFAULT_VECTOR_SIZE", "384"))

        if not self.host:
            logging.warning(
                "Advertencia: PGVECTOR_HOST no está configurado en el entorno."
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

    def __init__(self):
        super().__init__()
        self.host: Optional[str] = os.getenv("OLLAMA_HOST")
        self.embedding_model: str = os.getenv(
            "OLLAMA_EMBEDDING_MODEL", "nomic-embed-text"
        )
        self.markdown_model: str = os.getenv("OLLAMA_MARKDOWN_MODEL", "llama3")
        self.qa_model: str = os.getenv("OLLAMA_QA_MODEL", "llama3")
        self.context_model: str = os.getenv("OLLAMA_CONTEXT_MODEL", "llama3")

        if not self.host:
            logging.warning(
                "Advertencia: OLLAMA_HOST no está configurado en el entorno."
            )


class GeminiConfig(BaseConfig):
    """Google Gemini API specific configurations."""

    def __init__(self):
        super().__init__()
        self.api_key: Optional[str] = os.getenv("GEMINI_API_KEY")
        self.embedding_model: str = os.getenv("GEMINI_EMBEDDING_MODEL", "embedding-001")
        self.text_model: str = os.getenv("GEMINI_TEXT_MODEL", "gemini-1.5-flash")
        self.vision_model: str = os.getenv(
            "GEMINI_VISION_MODEL", "gemini-1.5-pro-vision"
        )
        self.embedding_dimension: int = int(
            os.getenv("GEMINI_EMBEDDING_DIMENSION", "1024")
        )

        # Configuración de safety settings (opcional, usando valores por defecto)
        self.safety_settings_enabled: bool = (
            os.getenv("GEMINI_SAFETY_SETTINGS_ENABLED", "True").lower() == "true"
        )

        if not self.api_key:
            logging.warning(
                "Advertencia: GEMINI_API_KEY no está configurado en el entorno. El proveedor Gemini no estará disponible."
            )


class N8NConfig(BaseConfig):
    """N8N specific configurations."""

    def __init__(self):
        super().__init__()
        self.url: Optional[str] = os.getenv("N8N_URL")
        self.webhook_url: Optional[str] = os.getenv(
            "N8N_WEBHOOK_URL"
        )  # URL N8N uses for its own webhooks
        self.api_key: Optional[str] = os.getenv(
            "N8N_API_KEY"
        )  # For N8N's REST API, if secured
        self.chat_workflow_id: Optional[str] = os.getenv(
            "N8N_CHAT_WORKFLOW_ID"
        )  # Might be deprecated if we import by JSON path
        self.workflow_json_path: Optional[str] = os.getenv(
            "N8N_WORKFLOW_JSON_PATH", "src/entrenai/n8n_workflow.json"
        )
        # N8N_ENCRYPTION_KEY is used by N8N itself, not directly by our app typically

        if not self.url:
            logging.warning("Advertencia: N8N_URL no está configurado en el entorno.")


class CeleryConfig(BaseConfig):
    """Celery specific configurations."""

    def __init__(self):
        super().__init__()
        self.broker_url: str = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
        self.result_backend: str = os.getenv(
            "CELERY_RESULT_BACKEND", "redis://localhost:6379/0"
        )
        # Consider adding other Celery settings if needed, e.g., task visibility timeout


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
