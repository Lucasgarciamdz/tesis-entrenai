"""Aplicación FastAPI principal simplificada."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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


@app.get("/")
async def root():
    """Endpoint raíz."""
    return {"message": "Entrenai API v1.0.0"}


@app.get("/health")
async def health():
    """Health check."""
    return {"status": "ok"}


@app.get("/api/v1/courses")
async def get_courses():
    """Lista todos los cursos."""
    return [
        {"id": 1, "name": "Curso de prueba 1", "shortname": "curso1"},
        {"id": 2, "name": "Curso de prueba 2", "shortname": "curso2"}
    ]


@app.post("/api/v1/courses/{course_id}/setup-ia")
async def setup_ia(course_id: int):
    """Configura IA para un curso."""
    return {
        "curso_id": course_id,
        "estado": "exitoso",
        "mensaje": f"IA configurada para curso {course_id}",
        "tabla_vectores": f"curso_{course_id}_vectores"
    }


@app.post("/api/v1/courses/{course_id}/files/refresh")
async def refresh_files(course_id: int):
    """Procesa archivos de un curso."""
    return {
        "curso_id": course_id,
        "archivos_procesados": 0,
        "estado": "en_proceso",
        "mensaje": "Procesamiento iniciado"
    }


@app.get("/api/v1/courses/{course_id}/files")
async def get_course_files(course_id: int):
    """Lista archivos de un curso."""
    return [
        {
            "nombre": "documento1.pdf",
            "tipo": "pdf",
            "tamaño": 1024,
            "procesado": True
        },
        {
            "nombre": "documento2.docx",
            "tipo": "docx", 
            "tamaño": 2048,
            "procesado": False
        }
    ]
