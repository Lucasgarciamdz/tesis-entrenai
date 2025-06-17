from fastapi import FastAPI
from loguru import logger
import sys

# Configuración del logger
logger.remove()
logger.add(sys.stderr, format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>")

app = FastAPI(
    title="Entrenai",
    description="API para sistemas de inteligencia artificial personalizados en moodle",
    version="1.0.0",
    docs_url="/docs",
)

@app.get("/readyz", tags=["Health"])
async def readyz():
    """
    Endpoint para verificar el estado de la API.
    
    Returns:
        dict: Estado de la API
    """
    logger.info("Verificando estado de la API")
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    logger.info("Iniciando servidor FastAPI")
    uvicorn.run(app, host="0.0.0.0", port=8000)