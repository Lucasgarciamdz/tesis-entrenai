from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from entrenai.api.routes.entrenai_setup import router as setup_router
from entrenai.config.settings import settings

# Configurar logging
logger.add("logs/entrenai.log", rotation="10 MB", level=settings.log_level)

app = FastAPI(
    title="Entrenai API",
    description="API simplificada para configuración de IA en cursos de Moodle",
    version="2.0.0",
    debug=settings.debug
)

# Configurar CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # En producción, especificar dominios exactos
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Incluir routers
app.include_router(setup_router, prefix="/api/v1", tags=["Setup"])

@app.get("/")
async def root():
    """Endpoint de salud de la aplicación."""
    return {
        "message": "Entrenai API v2.0 - Simplificada", 
        "status": "active",
        "version": "2.0.0"
    }

@app.get("/health")
async def health_check():
    """Endpoint de verificación de salud."""
    return {"status": "healthy", "message": "API funcionando correctamente"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "entrenai.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.debug
    )
