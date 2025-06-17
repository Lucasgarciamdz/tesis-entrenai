"""Configuración centralizada y simplificada para Entrenai."""

from typing import Literal, Optional
from pydantic import Field
from pydantic_settings import BaseSettings


class MoodleConfig(BaseSettings):
    """Configuración de Moodle."""
    url: str = Field(description="URL base de Moodle")
    token: str = Field(description="Token de webservice de Moodle")
    
    class Config:
        env_prefix = "MOODLE_"


class N8NConfig(BaseSettings):
    """Configuración de N8N."""
    url: str = Field(description="URL base de N8N")
    token: str = Field(description="Token de API de N8N")
    
    class Config:
        env_prefix = "N8N_"


class DatabaseConfig(BaseSettings):
    """Configuración de base de datos PostgreSQL con PgVector."""
    host: str = Field(default="localhost", description="Host de PostgreSQL")
    port: int = Field(default=5432, description="Puerto de PostgreSQL")
    database: str = Field(description="Nombre de la base de datos")
    username: str = Field(description="Usuario de PostgreSQL")
    password: str = Field(description="Contraseña de PostgreSQL")
    
    @property
    def connection_string(self) -> str:
        """Genera la cadena de conexión."""
        return f"postgresql://{self.username}:{self.password}@{self.host}:{self.port}/{self.database}"
    
    class Config:
        env_prefix = "DB_"


class AIConfig(BaseSettings):
    """Configuración de proveedores de IA."""
    provider: Literal["ollama", "gemini"] = Field(default="ollama", description="Proveedor de IA")
    
    # Ollama
    ollama_url: str = Field(default="http://localhost:11434", description="URL de Ollama")
    ollama_model: str = Field(default="llama3.1", description="Modelo de Ollama")
    
    # Gemini
    gemini_api_key: Optional[str] = Field(default=None, description="API Key de Gemini")
    gemini_model: str = Field(default="gemini-1.5-flash", description="Modelo de Gemini")
    
    # Configuración de embeddings
    embedding_model: str = Field(default="nomic-embed-text", description="Modelo para embeddings")
    embedding_dimensions: int = Field(default=768, description="Dimensiones de los embeddings")
    
    class Config:
        env_prefix = "AI_"


class CeleryConfig(BaseSettings):
    """Configuración de Celery."""
    broker_url: str = Field(default="redis://localhost:6379/0", description="URL del broker Redis")
    result_backend: str = Field(default="redis://localhost:6379/0", description="Backend de resultados")
    
    class Config:
        env_prefix = "CELERY_"


class Settings(BaseSettings):
    """Configuración principal de la aplicación."""
    
    # Configuración general
    app_name: str = Field(default="Entrenai", description="Nombre de la aplicación")
    debug: bool = Field(default=False, description="Modo debug")
    log_level: str = Field(default="INFO", description="Nivel de logging")
    
    # Configuraciones de servicios
    moodle: MoodleConfig = Field(default_factory=MoodleConfig)
    n8n: N8NConfig = Field(default_factory=N8NConfig)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    ai: AIConfig = Field(default_factory=AIConfig)
    celery: CeleryConfig = Field(default_factory=CeleryConfig)
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


# Instancia global de configuración
settings = Settings()


def get_settings() -> Settings:
    """Dependency para obtener la configuración."""
    return settings
