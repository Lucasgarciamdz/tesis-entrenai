"""Aplicación FastAPI principal."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routes import courses, setup, files

app = FastAPI(
    title="Entrenai API",
    description="Sistema RAG simplificado para Moodle",
    version="1.0.0"
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Rutas
app.include_router(courses.router, prefix="/api/v1")
app.include_router(setup.router, prefix="/api/v1")
app.include_router(files.router, prefix="/api/v1")


@app.get("/")
async def root():
    """Endpoint raíz."""
    return {"message": "Entrenai API v1.0.0"}


@app.get("/health")
async def health():
    """Health check."""
    return {"status": "ok"}
