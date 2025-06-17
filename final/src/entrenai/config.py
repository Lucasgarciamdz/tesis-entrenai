"""Configuración simplificada para EntrenAI."""

import os
from typing import Optional
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings


class DatabaseConfig(BaseModel):
    """Configuración de base de datos."""
    host: str = Field("localhost", description="Host de la base de datos")
    port: int = Field(5432, description="Puerto de la base de datos")
    database: str = Field("entrenai", description="Nombre de la base de datos")
    username: str = Field("entrenai", description="Usuario de la base de datos")
    password: str = Field("", description="Contraseña de la base de datos")
    
    @property
    def url(self) -> str:
        """URL de conexión a la base de datos."""
        return f"postgresql://{self.username}:{self.password}@{self.host}:{self.port}/{self.database}"


class MoodleConfig(BaseModel):
    """Configuración de Moodle."""
    url: str = Field("", description="URL base de Moodle")
    token: str = Field("", description="Token de API de Moodle")


class AIConfig(BaseModel):
    """Configuración de proveedores de IA."""
    provider: str = Field("ollama", description="Proveedor de IA (ollama, gemini)")
    
    # Configuración para Ollama
    ollama_host: str = Field("http://localhost:11434", description="Host de Ollama")
    ollama_model: str = Field("llama3.2", description="Modelo de Ollama")
    
    # Configuración para Gemini
    gemini_api_key: str = Field("", description="API Key de Gemini")
    gemini_model: str = Field("gemini-pro", description="Modelo de Gemini")


class N8NConfig(BaseModel):
    """Configuración de N8N."""
    url: str = Field("http://localhost:5678", description="URL base de N8N")
    api_key: str = Field("", description="API Key de N8N")


class Config(BaseSettings):
    """Configuración principal de EntrenAI."""
    
    # Base de datos
    database: DatabaseConfig = DatabaseConfig()
    
    # Moodle
    moodle: MoodleConfig = MoodleConfig()
    
    # IA
    ai: AIConfig = AIConfig()
    
    # N8N
    n8n: N8NConfig = N8NConfig()
    
    # Redis
    redis_url: str = Field("redis://localhost:6379", description="URL de Redis")
    
    model_config = {"env_nested_delimiter": "__"}
    
    @classmethod
    def from_env(cls) -> "Config":
        """Crea configuración desde variables de entorno."""
        return cls(
            database=DatabaseConfig(
                host=os.getenv("DB_HOST", "localhost"),
                port=int(os.getenv("DB_PORT", "5432")),
                database=os.getenv("DB_NAME", "entrenai"),
                username=os.getenv("DB_USER", "entrenai"),
                password=os.getenv("DB_PASSWORD", ""),
            ),
            moodle=MoodleConfig(
                url=os.getenv("MOODLE_URL", ""),
                token=os.getenv("MOODLE_TOKEN", ""),
            ),
            ai=AIConfig(
                provider=os.getenv("AI_PROVIDER", "ollama"),
                ollama_host=os.getenv("OLLAMA_HOST", "http://localhost:11434"),
                ollama_model=os.getenv("OLLAMA_MODEL", "llama3.2"),
                gemini_api_key=os.getenv("GEMINI_API_KEY", ""),
                gemini_model=os.getenv("GEMINI_MODEL", "gemini-pro"),
            ),
            n8n=N8NConfig(
                url=os.getenv("N8N_URL", "http://localhost:5678"),
                api_key=os.getenv("N8N_API_KEY", ""),
            ),
            redis_url=os.getenv("REDIS_URL", "redis://localhost:6379"),
        )


# Instancia global de configuración
config = Config.from_env()
