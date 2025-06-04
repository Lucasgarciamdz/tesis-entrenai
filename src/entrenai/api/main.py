from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

# Direct imports to avoid potential circular imports
import src.entrenai.api.routers.course_setup as course_setup
import src.entrenai.api.routers.search as search
import src.entrenai.api.routers.internal_processing as internal_processing
from src.entrenai.config import base_config
from src.entrenai.config.logger import get_logger

# Initialize logger for this module
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Iniciando API de Entrenai...")
    logger.info(f"Nivel de log configurado en: {base_config.log_level}")
    logger.info(f"Host de FastAPI: {base_config.fastapi_host}")
    logger.info(f"Puerto de FastAPI: {base_config.fastapi_port}")
    # Aquí se podrían añadir verificaciones iniciales, como intentar conectar a PgVector, Ollama, etc.
    # Por ahora, solo se registra.

    yield

    # Shutdown
    logger.info("Cerrando API de Entrenai...")


# Initialize FastAPI app
app = FastAPI(
    title="Entrenai API",
    description="API para el sistema Entrenai, integrando Moodle, PgVector, Ollama y N8N.",
    version="0.1.0",
    lifespan=lifespan,
)

# Configuración de CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Permite todos los orígenes (para desarrollo)
    # En producción, deberías restringirlo a dominios específicos.
    allow_credentials=True,
    allow_methods=["GET", "POST"],  # Especifica los métodos que permites
    allow_headers=["*"],  # Permite todos los headers
)


@app.get("/")
async def read_root():
    logger.info("Endpoint raíz '/' fue llamado.")
    return {"message": "¡Bienvenido a la API de Entrenai!"}


@app.get("/health")
async def health_check():
    logger.debug("Endpoint de estado '/health' fue llamado.")
    return {"status": "healthy"}  # "healthy" es un término técnico común, se mantiene.


# Placeholder for future routers
# from .routers import some_router
# app.include_router(some_router.router, prefix="/items", tags=["items"])

# Include routers
app.include_router(course_setup.router)
app.include_router(search.router)
app.include_router(internal_processing.router)

app.mount("/ui", StaticFiles(directory="src/entrenai/api/static", html=True), name="ui")

if __name__ == "__main__":
    import uvicorn

    # Cargar configuración desde el archivo .env
    # load_dotenv()

    # Iniciar el servidor Uvicorn
    uvicorn.run(
        app,
        host=base_config.fastapi_host,
        port=base_config.fastapi_port,
        log_level=base_config.log_level.lower(),
        reload=True,  # Solo para desarrollo
    )
