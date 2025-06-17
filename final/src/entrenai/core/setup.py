"""Lógica simplificada de setup de IA para cursos."""

from typing import Optional
from ..config import Config
from ..clients.moodle import MoodleClient
from ..clients.n8n import N8NClient
from ..db.vector_store import VectorStore
from ..models import SetupResponse


class CourseSetupService:
    """Servicio simplificado para configurar IA en cursos."""
    
    def __init__(self, config: Config):
        self.config = config
        self.moodle = MoodleClient(config.moodle)
        self.n8n = N8NClient(config.n8n)
        self.vector_store = VectorStore(config)
    
    async def setup_course_ai(
        self,
        course_id: int,
        course_name: Optional[str] = None
    ) -> SetupResponse:
        """
        Configura IA para un curso específico.
        
        Pasos:
        1. Obtener nombre del curso (si no se proporciona)
        2. Crear tabla de vectores
        3. Configurar workflow en N8N
        4. Crear sección en Moodle
        """
        
        # 1. Obtener nombre del curso si no se proporciona
        if not course_name:
            course = await self.moodle.get_course(course_id)
            if not course:
                return SetupResponse(
                    course_id=course_id,
                    status="error",
                    message="Curso no encontrado",
                    vector_table=""
                )
            course_name = course.fullname
        
        # 2. Crear tabla de vectores
        vector_table = f"curso_{course_id}_vectores"
        vector_created = await self.vector_store.create_collection(vector_table)
        
        if not vector_created:
            return SetupResponse(
                course_id=course_id,
                status="error",
                message="Error creando tabla de vectores",
                vector_table=vector_table
            )
        
        # 3. Configurar workflow en N8N
        try:
            await self.n8n.create_workflow(f"Chat_Curso_{course_id}", course_id)
            workflow_url = await self.n8n.get_webhook_url(course_id)
        except Exception as e:
            workflow_url = None
            print(f"Warning: No se pudo crear workflow N8N: {e}")
        
        # 4. Crear sección en Moodle
        try:
            section = await self.moodle.create_section(course_id, "Asistente IA")
            
            # Añadir enlace al chat si hay workflow
            if workflow_url and section:
                await self.moodle.add_url_to_section(
                    course_id,
                    section.id,
                    "Chat con IA",
                    workflow_url,
                    "Asistente inteligente para el curso"
                )
        except Exception as e:
            print(f"Warning: No se pudo crear sección en Moodle: {e}")
        
        return SetupResponse(
            course_id=course_id,
            status="success",
            message=f"Setup completado para {course_name}",
            vector_table=vector_table,
            workflow_url=workflow_url
        )
    
    async def cleanup_course_ai(self, course_id: int) -> bool:
        """Limpia la configuración de IA de un curso."""
        vector_table = f"curso_{course_id}_vectores"
        
        try:
            # Eliminar tabla de vectores
            await self.vector_store.delete_collection(vector_table)
            
            # TODO: Eliminar workflow de N8N
            # TODO: Eliminar sección de Moodle
            
            return True
        except Exception as e:
            print(f"Error en cleanup del curso {course_id}: {e}")
            return False
    
    async def get_course_status(self, course_id: int) -> dict:
        """Obtiene el estado de configuración de IA de un curso."""
        vector_table = f"curso_{course_id}_vectores"
        
        # Verificar si existe la tabla de vectores
        table_exists = await self.vector_store.collection_exists(vector_table)
        
        status = {
            "course_id": course_id,
            "vector_table_exists": table_exists,
            "vector_table_name": vector_table,
        }
        
        if table_exists:
            stats = await self.vector_store.get_collection_stats(vector_table)
            status.update(stats)
        
        return status
