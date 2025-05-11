from fastapi import FastAPI
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


@app.on_event("startup")
async def startup_event():
    logger.info("Entrenai API starting up...")
    logger.info(f"Log level set to: {base_config.log_level}")
    logger.info(f"FastAPI Host: {base_config.fastapi_host}")
    logger.info(f"FastAPI Port: {base_config.fastapi_port}")
    # Here you could add initial checks, like trying to connect to Qdrant, Ollama, etc.
    # For now, just logging.


@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Entrenai API shutting down...")


@app.get("/")
async def read_root():
    logger.info("Root endpoint '/' was called.")
    return {"message": "Welcome to Entrenai API!"}


@app.get("/health")
async def health_check():
    logger.debug("Health check endpoint '/health' was called.")
    return {"status": "healthy"}


# Placeholder for future routers
# from .routers import some_router
# app.include_router(some_router.router, prefix="/items", tags=["items"])

if __name__ == "__main__":
    # This part is for direct execution (e.g., python src/entrenai/api/main.py)
    # Uvicorn is typically used for production or via the Makefile.
    import uvicorn

    logger.info(
        "Running FastAPI app directly using Uvicorn (for development/debugging)."
    )
    uvicorn.run(
        app,
        host=base_config.fastapi_host,
        port=base_config.fastapi_port,
        log_level=base_config.log_level.lower(),
    )
