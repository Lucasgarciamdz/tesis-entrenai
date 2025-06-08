import os
from functools import lru_cache
from typing import Optional

from dotenv import load_dotenv
from pydantic import BaseModel, Field

# Carga las variables de entorno desde un archivo .env si existe.
# Es importante que este archivo .env esté en la raíz del proyecto,
# un nivel arriba del directorio 'entrenai_refactor'.
# load_dotenv(dotenv_path=os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".env"))
# Corregido para buscar .env en el directorio padre de entrenai_refactor, asumiendo que configuracion.py está en entrenai_refactor/config/
dotenv_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".env")
load_dotenv(dotenv_path=dotenv_path)

# --- Funciones Auxiliares para Conversión de Tipos ---

def _obtener_entorno_como_entero(clave: str, valor_defecto: int) -> int:
    """Obtiene una variable de entorno como entero."""
    return int(os.getenv(clave, str(valor_defecto)))

def _obtener_entorno_opcional_como_entero(clave: str) -> Optional[int]:
    """Obtiene una variable de entorno opcional como entero."""
    valor = os.getenv(clave)
    return int(valor) if valor and valor.isdigit() else None

def _obtener_entorno_como_booleano(clave: str, valor_defecto: bool) -> bool:
    """Obtiene una variable de entorno como booleano."""
    return os.getenv(clave, str(valor_defecto)).lower() == "true"

# --- Modelos de Configuración Anidados ---

class _ConfiguracionMoodleAnidada(BaseModel):
    """Configuraciones para la integración con Moodle."""
    url: Optional[str] = Field(default_factory=lambda: os.getenv("MOODLE_URL"), description="URL de la instancia de Moodle.")
    token: Optional[str] = Field(default_factory=lambda: os.getenv("MOODLE_TOKEN"), description="Token de API para Moodle.")
    nombre_carpeta_curso: str = Field(
        default_factory=lambda: os.getenv("MOODLE_COURSE_FOLDER_NAME", "Documentos EntrenAI"),
        description="Nombre de la carpeta donde se almacenan los documentos en el curso."
    )
    nombre_enlace_refrescar: str = Field(
        default_factory=lambda: os.getenv("MOODLE_REFRESH_LINK_NAME", "Refrescar IA EntrenAI"),
        description="Texto del enlace para disparar la actualización de la IA."
    )
    nombre_enlace_chat: str = Field(
        default_factory=lambda: os.getenv("MOODLE_CHAT_LINK_NAME", "Chat con IA EntrenAI"),
        description="Texto del enlace para acceder al chatbot."
    )
    id_profesor_defecto: Optional[int] = Field(
        default_factory=lambda: _obtener_entorno_opcional_como_entero("MOODLE_DEFAULT_TEACHER_ID"),
        description="ID del profesor por defecto para ciertas operaciones."
    )

class _ConfiguracionPostgresAnidada(BaseModel):
    """Configuraciones para la base de datos vectorial (PostgreSQL con pgvector)."""
    usuario: Optional[str] = Field(default_factory=lambda: os.getenv("PGVECTOR_USER"), description="Usuario de la base de datos.")
    contrasena: Optional[str] = Field(default_factory=lambda: os.getenv("PGVECTOR_PASSWORD"), description="Contraseña de la base de datos.")
    host: str = Field(
        default_factory=lambda: os.getenv("PGVECTOR_HOST", "pgvector_db" if os.getenv("ENTORNO_APP") == "docker" else "localhost"),
        description="Host de la base de datos."
    )
    puerto: int = Field(
        default_factory=lambda: _obtener_entorno_como_entero("PGVECTOR_PORT", 5432 if os.getenv("ENTORNO_APP") == "docker" else 5433),
        description="Puerto de la base de datos."
    )
    nombre_bd: Optional[str] = Field(default_factory=lambda: os.getenv("PGVECTOR_DB_NAME"), description="Nombre de la base de datos.")
    prefijo_coleccion: str = Field(
        default_factory=lambda: os.getenv("PGVECTOR_COLLECTION_PREFIX", "entrenai_curso_"),
        description="Prefijo para los nombres de las colecciones (tablas) de cada curso."
    )
    tamano_vector_defecto: int = Field(
        default_factory=lambda: _obtener_entorno_como_entero("DEFAULT_VECTOR_SIZE", 384),
        description="Tamaño de los vectores de embedding por defecto."
    )

class _ConfiguracionOllamaAnidada(BaseModel):
    """Configuraciones para el proveedor de IA Ollama."""
    host: Optional[str] = Field(default_factory=lambda: os.getenv("OLLAMA_HOST"), description="Host del servidor Ollama.")
    modelo_embedding: str = Field(default_factory=lambda: os.getenv("OLLAMA_EMBEDDING_MODEL", "nomic-embed-text"), description="Modelo para generar embeddings.")
    modelo_markdown: str = Field(default_factory=lambda: os.getenv("OLLAMA_MARKDOWN_MODEL", "llama3"), description="Modelo para procesar Markdown.")
    modelo_qa: str = Field(default_factory=lambda: os.getenv("OLLAMA_QA_MODEL", "llama3"), description="Modelo para preguntas y respuestas.")
    modelo_contexto: str = Field(default_factory=lambda: os.getenv("OLLAMA_CONTEXT_MODEL", "llama3"), description="Modelo para análisis de contexto.")

class _ConfiguracionGeminiAnidada(BaseModel):
    """Configuraciones para el proveedor de IA Google Gemini."""
    clave_api: Optional[str] = Field(default_factory=lambda: os.getenv("GEMINI_API_KEY"), description="Clave de API para Google Gemini.")
    modelo_embedding: str = Field(default_factory=lambda: os.getenv("GEMINI_EMBEDDING_MODEL", "embedding-001"), description="Modelo para generar embeddings.")
    modelo_texto: str = Field(default_factory=lambda: os.getenv("GEMINI_TEXT_MODEL", "gemini-1.5-flash"), description="Modelo para tareas de texto.")
    modelo_vision: str = Field(default_factory=lambda: os.getenv("GEMINI_VISION_MODEL", "gemini-1.5-pro-vision"), description="Modelo para tareas de visión.")
    # dimension_embedding: int = Field(default_factory=lambda: _obtener_entorno_como_entero("GEMINI_EMBEDDING_DIMENSION", 1024), description="Dimensión de los embeddings de Gemini.") # Esta variable no está en .env.example, considerar si es necesaria.
    seguridad_habilitada: bool = Field(
        default_factory=lambda: _obtener_entorno_como_booleano("GEMINI_SAFETY_SETTINGS_ENABLED", True),
        description="Indica si se aplican los filtros de seguridad de Gemini."
    )

class _ConfiguracionN8NAnidada(BaseModel):
    """Configuraciones para la integración con n8n."""
    url: Optional[str] = Field(default_factory=lambda: os.getenv("N8N_URL"), description="URL base de la instancia de n8n.")
    url_webhook: Optional[str] = Field(default_factory=lambda: os.getenv("N8N_WEBHOOK_URL"), description="URL del webhook de n8n para el chat.")
    clave_api: Optional[str] = Field(default_factory=lambda: os.getenv("N8N_API_KEY"), description="Clave de API para n8n.")
    id_flujo_chat: Optional[str] = Field(default_factory=lambda: os.getenv("N8N_CHAT_WORKFLOW_ID"), description="ID del flujo de trabajo de chat en n8n.")
    ruta_json_flujo: str = Field(
        default_factory=lambda: os.getenv("N8N_WORKFLOW_JSON_PATH", "nucleo/clientes/plantillas_n8n/flujo_n8n.json"), # Actualizada la ruta por defecto
        description="Ruta al archivo JSON que contiene la plantilla del flujo de n8n, relativa a la raíz de `entrenai_refactor`."
    )

class _ConfiguracionCeleryAnidada(BaseModel):
    """Configuraciones para Celery."""
    url_broker: str = Field(default_factory=lambda: os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0"), description="URL del broker de mensajes (Redis).")
    backend_resultado: str = Field(default_factory=lambda: os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/0"), description="URL del backend de resultados (Redis).")


# --- Clase de Configuración Principal ---

class ConfiguracionPrincipal(BaseModel):
    """
    Agrupa todas las configuraciones de la aplicación en un único objeto.
    """
    entorno_app: str = Field(default_factory=lambda: os.getenv("ENTORNO_APP", "local").lower(), description="Entorno de ejecución (local o docker). Equivalente a APP_ENV.")
    nivel_log: str = Field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO").upper(), description="Nivel de los logs (INFO, DEBUG, etc.).")
    host_api: str = Field(default_factory=lambda: os.getenv("FASTAPI_HOST", "0.0.0.0"), description="Host para la API de FastAPI.")
    puerto_api: int = Field(default_factory=lambda: _obtener_entorno_como_entero("FASTAPI_PORT", 8000), description="Puerto para la API de FastAPI.")

    # Directorio de datos: usa DATA_DIR de .env, o por defecto 'datos/' relativo a la raíz de entrenai_refactor
    directorio_datos_base: str = Field(default_factory=lambda: os.getenv("DATA_DIR", "datos"), description="Directorio base para datos de la aplicación, relativo a la raíz de entrenai_refactor.")

    @property
    def ruta_directorio_datos(self) -> str:
        """Ruta absoluta al directorio de datos base."""
        # Asume que este archivo está en entrenai_refactor/config/
        # Sube dos niveles para llegar a entrenai_refactor/ y luego añade el directorio_datos_base
        return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", self.directorio_datos_base))

    @property
    def ruta_directorio_descargas(self) -> str:
        """Ruta absoluta al subdirectorio de descargas."""
        # Usa DOWNLOAD_SUBDIR de .env o 'descargas' por defecto
        subdirectorio_descargas = os.getenv("DOWNLOAD_SUBDIR", "descargas")
        return os.path.join(self.ruta_directorio_datos, subdirectorio_descargas)

    proveedor_ia: str = Field(default_factory=lambda: os.getenv("AI_PROVIDER", "ollama").lower(), description="Proveedor de IA a utilizar (ollama o gemini).")

    moodle: _ConfiguracionMoodleAnidada = Field(default_factory=_ConfiguracionMoodleAnidada)
    db: _ConfiguracionPostgresAnidada = Field(default_factory=_ConfiguracionPostgresAnidada)
    ollama: _ConfiguracionOllamaAnidada = Field(default_factory=_ConfiguracionOllamaAnidada)
    gemini: _ConfiguracionGeminiAnidada = Field(default_factory=_ConfiguracionGeminiAnidada)
    n8n: _ConfiguracionN8NAnidada = Field(default_factory=_ConfiguracionN8NAnidada)
    celery: _ConfiguracionCeleryAnidada = Field(default_factory=_ConfiguracionCeleryAnidada)


# --- Función para obtener la configuración ---

@lru_cache()
def obtener_configuracion_global() -> ConfiguracionPrincipal:
    """
    Crea y devuelve una instancia única de la configuración de la aplicación.
    Utiliza lru_cache para asegurar que la configuración se cargue una sola vez.

    Returns:
        ConfiguracionPrincipal: El objeto de configuración de la aplicación.
    """
    return ConfiguracionPrincipal()

# Instancia global para facilitar la importación en otros módulos
configuracion_global = obtener_configuracion_global()

# Crear directorios de datos si no existen al cargar la configuración
# Esto se ejecutará una vez cuando el módulo se importe por primera vez.
if not os.path.exists(configuracion_global.ruta_directorio_datos):
    os.makedirs(configuracion_global.ruta_directorio_datos)
    print(f"Directorio de datos creado: {configuracion_global.ruta_directorio_datos}")

if not os.path.exists(configuracion_global.ruta_directorio_descargas):
    os.makedirs(configuracion_global.ruta_directorio_descargas)
    print(f"Directorio de descargas creado: {configuracion_global.ruta_directorio_descargas}")

[end of entrenai_refactor/config/configuracion.py]
