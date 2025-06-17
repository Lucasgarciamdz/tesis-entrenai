"""Endpoints para gestión de archivos."""

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from typing import List
from loguru import logger
from pydantic import BaseModel
from pathlib import Path
import time

from entrenai.core.clients.moodle_client import MoodleClient
from entrenai.core.db.pgvector_wrapper import PgVectorWrapper
from entrenai.core.files.file_processor import FileProcessor
from entrenai.core.ai.ollama_wrapper import OllamaWrapper
from entrenai.api.models import MoodleFile, DocumentChunk
from entrenai.config import get_config

router = APIRouter()


class FileProcessResponse(BaseModel):
    """Respuesta del procesamiento de archivos."""
    curso_id: int
    archivos_procesados: int
    estado: str
    mensaje: str


class FileInfo(BaseModel):
    """Información de archivo indexado."""
    nombre: str
    tipo: str
    tamaño: int
    url: str
    procesado: bool


def get_moodle_client() -> MoodleClient:
    """Dependency para obtener cliente de Moodle."""
    config = get_config()
    return MoodleClient(config.moodle)


def get_pgvector_wrapper() -> PgVectorWrapper:
    """Dependency para obtener wrapper de PgVector."""
    config = get_config()
    return PgVectorWrapper(config.pgvector)


def get_file_processor() -> FileProcessor:
    """Dependency para obtener procesador de archivos."""
    return FileProcessor()


def get_ollama_wrapper() -> OllamaWrapper:
    """Dependency para obtener wrapper de Ollama."""
    config = get_config()
    return OllamaWrapper(config.ai)


@router.post("/courses/{course_id}/files/refresh", response_model=FileProcessResponse)
def refresh_course_files(
    course_id: int,
    background_tasks: BackgroundTasks,
    moodle: MoodleClient = Depends(get_moodle_client),
    db: PgVectorWrapper = Depends(get_pgvector_wrapper),
    processor: FileProcessor = Depends(get_file_processor),
):
    """
    Procesa archivos nuevos de un curso.
    
    Busca archivos en carpetas del curso y los indexa en la base vectorial.
    """
    logger.info(f"Iniciando refresh de archivos para curso {course_id}")
    
    try:
        # Verificar que el curso existe
        courses = moodle.get_all_courses()
        course = next((c for c in courses if c.id == course_id), None)
        if not course:
            raise HTTPException(status_code=404, detail="Curso no encontrado")
        
        # Buscar sección de IA
        seccion_ia = moodle.get_section_by_name(course_id, "Asistente IA")
        if not seccion_ia:
            raise HTTPException(
                status_code=400, 
                detail="Curso no tiene IA configurada. Ejecute setup primero."
            )
        
        # Procesar archivos en background
        ai_client = get_ollama_wrapper()
        background_tasks.add_task(
            process_course_files_background,
            course_id,
            moodle,
            db,
            processor,
            ai_client
        )
        
        return FileProcessResponse(
            curso_id=course_id,
            archivos_procesados=0,  # Se actualizará en background
            estado="en_proceso",
            mensaje="Procesamiento de archivos iniciado en segundo plano"
        )
        
    except Exception as e:
        logger.error(f"Error iniciando refresh de archivos: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/courses/{course_id}/files", response_model=List[FileInfo])
def get_course_files(
    course_id: int,
    moodle: MoodleClient = Depends(get_moodle_client),
    db: PgVectorWrapper = Depends(get_pgvector_wrapper),
):
    """
    Lista archivos indexados de un curso.
    """
    logger.info(f"Obteniendo archivos del curso {course_id}")
    
    try:
        # Verificar que el curso existe
        courses = moodle.get_all_courses()
        course = next((c for c in courses if c.id == course_id), None)
        if not course:
            raise HTTPException(status_code=404, detail="Curso no encontrado")
        
        # Obtener contenido del curso y buscar carpetas
        course_contents = moodle._make_request(
            "core_course_get_contents", {"courseid": course_id}
        )
        
        files_info = []
        
        for section in course_contents:
            for module in section.get("modules", []):
                if module.get("modname") == "folder":
                    # Obtener archivos de la carpeta
                    folder_files = moodle.get_folder_files(module.get("id"))
                    
                    for file in folder_files:
                        # Verificar si está procesado usando el file tracker
                        processed_files = db.get_processed_files_timestamps(course_id)
                        is_processed = file.filename in processed_files
                        
                        files_info.append(FileInfo(
                            nombre=file.filename,
                            tipo=file.filename.split('.')[-1] if '.' in file.filename else 'unknown',
                            tamaño=file.filesize,
                            url=file.fileurl,
                            procesado=is_processed
                        ))
        
        return files_info
        
    except Exception as e:
        logger.error(f"Error obteniendo archivos del curso {course_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def process_course_files_background(
    course_id: int,
    moodle: MoodleClient,
    db: PgVectorWrapper,
    processor: FileProcessor,
    ai_client: OllamaWrapper
):
    """Procesa archivos en segundo plano."""
    try:
        logger.info(f"Procesando archivos en background para curso {course_id}")
        
        # Obtener contenido del curso
        course_contents = moodle._make_request(
            "core_course_get_contents", {"courseid": course_id}
        )
        
        course_name = f"curso_{course_id}"
        archivos_procesados = 0
        
        for section in course_contents:
            for module in section.get("modules", []):
                if module.get("modname") == "folder":
                    folder_files = moodle.get_folder_files(module.get("id"))
                    
                    for file in folder_files:
                        # Verificar si ya está procesado
                        if db.is_file_new_or_modified(course_id, file.filename, file.timemodified):
                            try:
                                # Descargar y procesar archivo
                                temp_dir = Path("temp_downloads")
                                
                                local_file_path = moodle.download_file(
                                    file.fileurl, temp_dir, file.filename
                                )
                                
                                # Extraer texto
                                text_content = processor.process_file(local_file_path)
                                
                                if text_content:
                                    # Crear chunks simples
                                    chunks = create_text_chunks(text_content, file.filename, course_id)
                                    
                                    # Generar embeddings para cada chunk
                                    for chunk in chunks:
                                        embedding = ai_client.generate_embedding(chunk.text)
                                        chunk.embedding = embedding
                                    
                                    # Guardar chunks en BD
                                    if db.upsert_chunks(course_name, chunks):
                                        db.mark_file_as_processed(course_id, file.filename, file.timemodified)
                                        archivos_procesados += 1
                                        logger.info(f"Archivo procesado: {file.filename}")
                                
                                # Limpiar archivo temporal
                                local_file_path.unlink()
                                
                            except Exception as e:
                                logger.error(f"Error procesando {file.filename}: {e}")
                                continue
        
        logger.info(f"Background processing completado. Archivos procesados: {archivos_procesados}")
        
    except Exception as e:
        logger.error(f"Error en procesamiento background: {e}")


def create_text_chunks(text: str, filename: str, course_id: int, chunk_size: int = 1000) -> List[DocumentChunk]:
    """Crea chunks simples de texto."""
    chunks = []
    words = text.split()
    
    for i in range(0, len(words), chunk_size):
        chunk_words = words[i:i + chunk_size]
        chunk_text = " ".join(chunk_words)
        
        chunk_id = f"{filename}_chunk_{i // chunk_size}"
        
        chunk = DocumentChunk(
            id=chunk_id,
            course_id=course_id,
            document_id=filename,
            text=chunk_text,
            metadata={
                "source": filename,
                "chunk_index": i // chunk_size,
                "created_at": int(time.time())
            }
        )
        chunks.append(chunk)
    
    return chunks
