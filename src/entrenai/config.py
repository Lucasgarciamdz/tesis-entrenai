import os
from dotenv import load_dotenv
from typing import Optional, List

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

class MoodleConfig(BaseConfig):
    """Moodle specific configurations."""
    def __init__(self):
        super().__init__()
        self.url: Optional[str] = os.getenv("MOODLE_URL")
        self.token: Optional[str] = os.getenv("MOODLE_TOKEN")
        self.course_folder_name: str = os.getenv("MOODLE_COURSE_FOLDER_NAME", "Entrenai Documents")
        self.refresh_link_name: str = os.getenv("MOODLE_REFRESH_LINK_NAME", "Refresh Entrenai IA")
        self.chat_link_name: str = os.getenv("MOODLE_CHAT_LINK_NAME", "Chat con Entrenai IA")

        if not self.url or not self.token:
            # Or raise an error, or log a warning, depending on how critical these are at startup
            print("Warning: MOODLE_URL or MOODLE_TOKEN is not set in the environment.")


class QdrantConfig(BaseConfig):
    """Qdrant specific configurations."""
    def __init__(self):
        super().__init__()
        self.host: Optional[str] = os.getenv("QDRANT_HOST")
        self.port: Optional[int] = int(os.getenv("QDRANT_PORT", "6333"))
        self.grpc_port: Optional[int] = int(os.getenv("QDRANT_GRPC_PORT", "6334"))
        self.api_key: Optional[str] = os.getenv("QDRANT_API_KEY") # Can be None
        self.collection_prefix: str = os.getenv("QDRANT_COLLECTION_PREFIX", "entrenai_course_")

        if not self.host:
            print("Warning: QDRANT_HOST is not set in the environment.")


class OllamaConfig(BaseConfig):
    """Ollama specific configurations."""
    def __init__(self):
        super().__init__()
        self.host: Optional[str] = os.getenv("OLLAMA_HOST")
        self.embedding_model: str = os.getenv("OLLAMA_EMBEDDING_MODEL", "nomic-embed-text")
        self.markdown_model: str = os.getenv("OLLAMA_MARKDOWN_MODEL", "llama3")
        self.qa_model: str = os.getenv("OLLAMA_QA_MODEL", "llama3")
        self.context_model: str = os.getenv("OLLAMA_CONTEXT_MODEL", "llama3")

        if not self.host:
            print("Warning: OLLAMA_HOST is not set in the environment.")


class N8NConfig(BaseConfig):
    """N8N specific configurations."""
    def __init__(self):
        super().__init__()
        self.url: Optional[str] = os.getenv("N8N_URL")
        self.webhook_url: Optional[str] = os.getenv("N8N_WEBHOOK_URL") # URL N8N uses for its own webhooks
        self.api_key: Optional[str] = os.getenv("N8N_API_KEY") # For N8N's REST API, if secured
        self.chat_workflow_id: Optional[str] = os.getenv("N8N_CHAT_WORKFLOW_ID")
        # N8N_ENCRYPTION_KEY is used by N8N itself, not directly by our app typically

        if not self.url:
            print("Warning: N8N_URL is not set in the environment.")


# Instantiate configurations for easy import elsewhere
# This makes them singletons for the application's lifecycle
base_config = BaseConfig()
moodle_config = MoodleConfig()
qdrant_config = QdrantConfig()
ollama_config = OllamaConfig()
n8n_config = N8NConfig()

# Example of how to use:
# from entrenai.config import moodle_config
# print(moodle_config.url)

if __name__ == "__main__":
    print("Base Config:", vars(base_config))
    print("Moodle Config:", vars(moodle_config))
    print("Qdrant Config:", vars(qdrant_config))
    print("Ollama Config:", vars(ollama_config))
    print("N8N Config:", vars(n8n_config))
