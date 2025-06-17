"""Configuración simplificada del sistema."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Configuración principal del sistema."""
    
    # Base de datos
    database_url: str = "postgresql://user:password@localhost:5432/entrenai"
    
    # Moodle
    moodle_url: str = "http://localhost:8080"
    moodle_token: str = ""
    
    # N8N
    n8n_url: str = "http://localhost:5678"
    n8n_api_key: str = ""
    
    # Ollama
    ollama_url: str = "http://localhost:11434"
    
    # Configuración de modelo
    embedding_model: str = "nomic-embed-text"
    chat_model: str = "llama3.2"
    
    class Config:
        env_file = ".env"


settings = Settings()
