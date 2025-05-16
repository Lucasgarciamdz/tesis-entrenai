from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from src.entrenai.utils.logger import get_logger
from src.entrenai.config import base_config

# Initialize logger for this module
logger = get_logger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="Entrenai API",
    description="API para el sistema Entrenai, integrando Moodle, Qdrant, Ollama y N8N.",
    version="0.1.0",
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


@app.on_event("startup")
async def startup_event():
    logger.info("Iniciando API de Entrenai...")
    logger.info(f"Nivel de log configurado en: {base_config.log_level}")
    logger.info(f"Host de FastAPI: {base_config.fastapi_host}")
    logger.info(f"Puerto de FastAPI: {base_config.fastapi_port}")
    # Aquí se podrían añadir verificaciones iniciales, como intentar conectar a Qdrant, Ollama, etc.
    # Por ahora, solo se registra.


@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Cerrando API de Entrenai...")


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

# Import and include routers
from src.entrenai.api.routers import course_setup, search

app.include_router(course_setup.router)
app.include_router(search.router)

# Montar directorio estático
# Asume que 'static' está en la raíz del proyecto, y main.py está en src/entrenai/api/
# Por lo tanto, necesitamos subir dos niveles desde __file__ para llegar a la raíz del proyecto.
# project_root = Path(__file__).resolve().parent.parent.parent
# static_files_dir = project_root / "static"
# app.mount("/ui", StaticFiles(directory=str(static_files_dir), html=True), name="ui")

# Simplificación: Asumir que la aplicación se ejecuta desde la raíz del proyecto
# donde el directorio 'static' es directamente accesible.
# Esto es común si usas `uvicorn src.entrenai.api.main:app` desde la raíz.
# Si `make run` ejecuta uvicorn desde la raíz, "static" es correcto.
# El Makefile actual ejecuta `uvicorn src.entrenai.api.main:app --reload $(RUN_ARGS)`
# que se ejecuta desde la raíz del proyecto, por lo que "static" debería ser correcto.
app.mount("/ui", StaticFiles(directory="static", html=True), name="ui")
