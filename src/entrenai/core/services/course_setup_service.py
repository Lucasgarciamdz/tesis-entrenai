from typing import Optional

from src.entrenai.api.models import CourseSetupResponse, HttpUrl
from src.entrenai.config.logger import get_logger
from src.entrenai.config import pgvector_config, moodle_config, base_config, gemini_config, ollama_config
from src.entrenai.core.services.pgvector_service import PgvectorService
from src.entrenai.core.services.n8n_workflow_service import N8NWorkflowService
from src.entrenai.core.services.moodle_integration_service import MoodleIntegrationService
from src.entrenai.core.utils.course_utils import get_course_name_from_query_or_moodle
from src.entrenai.core.clients.moodle_client import MoodleClient

logger = get_logger(__name__)


class CourseSetupService:
    """Servicio orquestador para la configuración de cursos."""
    
    def __init__(
        self,
        pgvector_service: PgvectorService,
        n8n_service: N8NWorkflowService,
        moodle_service: MoodleIntegrationService,
        moodle_client: MoodleClient,
    ):
        self.pgvector_service = pgvector_service
        self.n8n_service = n8n_service
        self.moodle_service = moodle_service
        self.moodle_client = moodle_client
    
    async def setup_course(
        self,
        course_id: int,
        base_url: str,
        course_name_query: Optional[str] = None,
        initial_messages: Optional[str] = None,
        system_message: Optional[str] = None,
        input_placeholder: Optional[str] = None,
        chat_title: Optional[str] = None,
    ) -> CourseSetupResponse:
        """
        Orquesta el setup completo de un curso.
        """
        logger.info(f"Iniciando configuración de IA para curso ID: {course_id}")
        
        # Paso 1: Obtener nombre del curso
        course_name = get_course_name_from_query_or_moodle(
            course_id, course_name_query, self.moodle_client
        )
        
        # Inicializar respuesta
        response = CourseSetupResponse(
            course_id=course_id,
            status="pendiente",
            message=f"Configuración iniciada para el curso {course_id} ('{course_name}').",
            qdrant_collection_name="",
        )
        
        try:
            # Paso 2: Configurar base de datos Pgvector
            pgvector_table_name = self._setup_pgvector(course_name)
            response.qdrant_collection_name = pgvector_table_name
            
            # Paso 3: Configurar y desplegar workflow N8N
            n8n_chat_url = self._setup_n8n_workflow(
                course_id, course_name, pgvector_table_name,
                initial_messages, system_message, input_placeholder, chat_title
            )
            response.n8n_chat_url = HttpUrl(n8n_chat_url) if n8n_chat_url else None
            
            # Paso 4: Configurar sección de Moodle
            section_id = self._setup_moodle_section(
                course_id, course_name, n8n_chat_url, base_url,
                initial_messages, system_message, input_placeholder, chat_title
            )
            response.moodle_section_id = section_id
            
            # Completar respuesta exitosa
            response.status = "exitoso"
            response.message = f"Configuración de Entrenai IA completada exitosamente para el curso {course_id} ('{course_name}')."
            logger.info(response.message)
            
            return response
            
        except Exception as e:
            response.status = "fallido"
            response.message = f"Error durante la configuración: {str(e)}"
            logger.error(response.message)
            raise
    
    def _setup_pgvector(self, course_name: str) -> str:
        """Configura la base de datos Pgvector."""
        logger.info("Configurando base de datos Pgvector...")
        vector_size = pgvector_config.default_vector_size
        return self.pgvector_service.ensure_course_table(course_name, vector_size)
    
    def _setup_n8n_workflow(
        self,
        course_id: int,
        course_name: str,
        pgvector_table_name: str,
        initial_messages: Optional[str],
        system_message: Optional[str],
        input_placeholder: Optional[str],
        chat_title: Optional[str],
    ) -> Optional[str]:
        """Configura el workflow de N8N."""
        logger.info("Configurando workflow N8N...")
        
        # Preparar parámetros de IA
        ai_params = self._prepare_ai_params()
        
        return self.n8n_service.configure_and_deploy_workflow(
            course_id=course_id,
            course_name=course_name,
            pgvector_table_name=pgvector_table_name,
            ai_config_params=ai_params,
            initial_messages=initial_messages,
            system_message=system_message,
            input_placeholder=input_placeholder,
            chat_title=chat_title,
        )
    
    def _setup_moodle_section(
        self,
        course_id: int,
        course_name: str,
        n8n_chat_url: Optional[str],
        base_url: str,
        initial_messages: Optional[str],
        system_message: Optional[str],
        input_placeholder: Optional[str],
        chat_title: Optional[str],
    ) -> int:
        """Configura la sección de Moodle."""
        logger.info("Configurando sección de Moodle...")
        
        if not n8n_chat_url:
            raise Exception("No se pudo obtener URL del chat de N8N")
        
        # Crear/obtener sección
        section = self.moodle_service.create_or_get_section(
            course_id, moodle_config.course_folder_name, position=1
        )
        
        # Construir HTML summary
        html_summary = self.moodle_service.build_html_summary(
            n8n_chat_url=n8n_chat_url,
            course_id=course_id,
            base_url=base_url,
            initial_messages=initial_messages,
            system_message=system_message,
            input_placeholder=input_placeholder,
            chat_title=chat_title,
        )
        
        # Actualizar sección
        self.moodle_service.update_section_summary(
            course_id=course_id,
            section_id=section.id,
            section_name=moodle_config.course_folder_name,
            html_summary=html_summary,
        )
        
        return section.id
    
    def _prepare_ai_params(self) -> dict:
        """Prepara los parámetros de configuración de IA."""
        if base_config.ai_provider == "gemini":
            return {
                "api_key": gemini_config.api_key,
                "embedding_model": gemini_config.embedding_model,
                "qa_model": gemini_config.text_model,
            }
        else:  # Ollama por defecto
            return {
                "host": ollama_config.host,
                "embedding_model": ollama_config.embedding_model,
                "qa_model": ollama_config.qa_model,
            }
