"""Aplicación FastAPI principal."""

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


# === ENDPOINTS DE CURSOS ===

@app.get("/api/v1/courses")
async def get_courses():
    """Lista todos los cursos disponibles."""
    # Simulación de datos - en producción vendría del MoodleClient
    return [
        {
            "id": 1,
            "shortname": "math101",
            "fullname": "Matemáticas Básicas",
            "displayname": "Matemáticas Básicas",
            "summary": "Curso introductorio de matemáticas"
        },
        {
            "id": 2,
            "shortname": "phys201",
            "fullname": "Física Avanzada",
            "displayname": "Física Avanzada", 
            "summary": "Conceptos avanzados de física"
        }
    ]


@app.get("/api/v1/courses/{course_id}")
async def get_course(course_id: int):
    """Obtiene un curso específico."""
    # Simulación - en producción buscaría en la lista de cursos
    if course_id == 1:
        return {
            "id": 1,
            "shortname": "math101",
            "fullname": "Matemáticas Básicas",
            "displayname": "Matemáticas Básicas",
            "summary": "Curso introductorio de matemáticas"
        }
    elif course_id == 2:
        return {
            "id": 2,
            "shortname": "phys201",
            "fullname": "Física Avanzada",
            "displayname": "Física Avanzada",
            "summary": "Conceptos avanzados de física"
        }
    else:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Curso no encontrado")


# === ENDPOINTS DE SETUP ===

@app.post("/api/v1/courses/{course_id}/setup-ia")
async def setup_ia_curso(course_id: int):
    """
    Configura la IA para un curso específico.
    
    Pasos simulados:
    1. Crea tabla de vectores
    2. Configura workflow en N8N
    3. Crea sección en Moodle
    """
    # Simulación del proceso de setup
    return {
        "curso_id": course_id,
        "estado": "exitoso",
        "mensaje": f"Setup completado para curso {course_id}",
        "tabla_vectores": f"curso_{course_id}_vectores",
        "workflow_url": f"http://localhost:5678/webhook/curso-{course_id}"
    }


# === ENDPOINTS DE ARCHIVOS ===

@app.post("/api/v1/courses/{course_id}/files/refresh")
async def refresh_course_files(course_id: int):
    """
    Procesa archivos nuevos de un curso.
    
    Busca archivos en carpetas del curso y los indexa en la base vectorial.
    """
    # Simulación del procesamiento en background
    return {
        "curso_id": course_id,
        "archivos_procesados": 0,  # Se actualizará en background
        "estado": "en_proceso",
        "mensaje": "Procesamiento de archivos iniciado en segundo plano"
    }


@app.get("/api/v1/courses/{course_id}/files")
async def get_course_files(course_id: int):
    """Lista archivos indexados de un curso."""
    # Simulación de archivos indexados
    return [
        {
            "nombre": "capitulo1.pdf",
            "tipo": "pdf",
            "tamaño": 524288,  # 512KB
            "url": f"http://moodle.example.com/file.php/course{course_id}/capitulo1.pdf",
            "procesado": True
        },
        {
            "nombre": "ejercicios.docx",
            "tipo": "docx",
            "tamaño": 102400,  # 100KB
            "url": f"http://moodle.example.com/file.php/course{course_id}/ejercicios.docx",
            "procesado": True
        },
        {
            "nombre": "presentacion.pptx",
            "tipo": "pptx",
            "tamaño": 2097152,  # 2MB
            "url": f"http://moodle.example.com/file.php/course{course_id}/presentacion.pptx",
            "procesado": False
        }
    ]


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
