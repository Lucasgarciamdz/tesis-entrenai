"""API principal simplificada de EntrenAI."""

from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Optional
from pathlib import Path
import tempfile
import os

from ..config import Config
from ..core.setup import CourseSetupService
from ..core.chat import ChatService
from ..core.document_processor import DocumentProcessor
from ..models import SetupResponse, ChatMessage, ChatResponse

# Configuración
config = Config.from_env()

# Servicios
setup_service = CourseSetupService(config)
chat_service = ChatService(config)
doc_processor = DocumentProcessor(config)

# FastAPI app
app = FastAPI(
    title="EntrenAI API",
    description="API simplificada para EntrenAI",
    version="2.0.0"
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
    """Endpoint de salud."""
    return {"message": "EntrenAI API funcionando"}


@app.post("/courses/{course_id}/setup", response_model=SetupResponse)
async def setup_course_ai(
    course_id: int,
    course_name: Optional[str] = None
):
    """Configura IA para un curso."""
    try:
        result = await setup_service.setup_course_ai(course_id, course_name)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/courses/{course_id}/status")
async def get_course_status(course_id: int):
    """Obtiene el estado de configuración de IA de un curso."""
    try:
        status = await setup_service.get_course_status(course_id)
        return status
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/courses/{course_id}/cleanup")
async def cleanup_course_ai(course_id: int):
    """Limpia la configuración de IA de un curso."""
    try:
        success = await setup_service.cleanup_course_ai(course_id)
        return {"success": success}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/courses/{course_id}/chat", response_model=ChatResponse)
async def chat_with_course(
    course_id: int,
    message: str,
    history: Optional[List[ChatMessage]] = None
):
    """Chat con contexto del curso."""
    try:
        response = await chat_service.chat_with_context(
            course_id, message, history
        )
        return response
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/chat", response_model=ChatResponse)
async def simple_chat(message: str):
    """Chat simple sin contexto específico."""
    try:
        response = await chat_service.simple_chat(message)
        return response
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/courses/{course_id}/documents/upload")
async def upload_documents(
    course_id: int,
    files: List[UploadFile] = File(...),
    source: Optional[str] = "upload"
):
    """Sube y procesa documentos para un curso."""
    try:
        # Crear directorio temporal
        with tempfile.TemporaryDirectory() as temp_dir:
            file_paths = []
            
            # Guardar archivos temporalmente
            for file in files:
                file_path = Path(temp_dir) / file.filename
                with open(file_path, "wb") as f:
                    content = await file.read()
                    f.write(content)
                file_paths.append(file_path)
            
            # Procesar archivos
            success = await doc_processor.process_and_store_documents(
                course_id,
                file_paths,
                {"source": source}
            )
            
            return {
                "success": success,
                "files_processed": len(file_paths),
                "message": "Documentos procesados exitosamente" if success else "Error procesando documentos"
            }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/courses/{course_id}/documents/text")
async def add_text_content(
    course_id: int,
    content: str,
    source_name: str = "texto_manual"
):
    """Añade contenido de texto directamente a un curso."""
    try:
        success = await doc_processor.process_text_content(
            course_id,
            content,
            source_name
        )
        
        return {
            "success": success,
            "message": "Contenido añadido exitosamente" if success else "Error añadiendo contenido"
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Punto de entrada para desarrollo
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
