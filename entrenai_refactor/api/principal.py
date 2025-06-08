from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from entrenai_refactor.api.rutas import principal

app = FastAPI(title="EntrenAI Refactorizado", description="API en español para gestión de IA en Moodle")

app.include_router(principal.router)

# Servir archivos estáticos (frontend)
app.mount("/ui", StaticFiles(directory="entrenai_refactor/api/estaticos"), name="ui") 