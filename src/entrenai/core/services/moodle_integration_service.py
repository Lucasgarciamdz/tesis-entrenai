import re
from typing import Dict, Optional

from src.entrenai.config.logger import get_logger
from src.entrenai.core.clients.moodle_client import MoodleClient
from src.entrenai.config import moodle_config

logger = get_logger(__name__)

DEFAULT_UNSPECIFIED_TEXT = "No especificado"


class MoodleIntegrationService:
    """Servicio para integración con Moodle."""
    
    def __init__(self, moodle_client: MoodleClient):
        self.moodle = moodle_client
    
    def create_or_get_section(self, course_id: int, section_name: str, position: int = 1):
        """Crea o obtiene la sección de Moodle para el curso."""
        logger.info(f"Creando/obteniendo sección '{section_name}' para curso {course_id}")
        
        section = self.moodle.create_course_section(course_id, section_name, position)
        if not section or not section.id:
            raise Exception(f"Falló la creación de la sección de Moodle para el curso {course_id}")
        
        logger.info(f"Sección obtenida/creada: ID {section.id}, Nombre: '{section.name}'")
        return section
    
    def build_html_summary(
        self,
        n8n_chat_url: str,
        course_id: int,
        base_url: str,
        initial_messages: Optional[str] = None,
        system_message: Optional[str] = None,
        input_placeholder: Optional[str] = None,
        chat_title: Optional[str] = None,
    ) -> str:
        """Construye el HTML summary para la sección de Moodle."""
        
        # URLs para enlaces
        refresh_files_url = f"{base_url.rstrip('/')}/ui/manage_files.html?course_id={course_id}"
        refresh_chat_config_url = f"{base_url.rstrip('/')}/api/v1/courses/{course_id}/refresh-chat-config"
        
        # Mensaje de instrucciones
        edit_instruction_message = """
<p><strong>Nota para el profesor:</strong> Puede modificar las configuraciones del chat directamente en la sección "Configuración del Chat de IA" a continuación. Después de realizar cambios, use el enlace "Actualizar Configuraciones del Chat" para aplicar los cambios al sistema de IA.</p>
"""
        
        # Construir HTML summary
        html_summary = f"""
<h4>Recursos de Entrenai IA</h4>
<p>Utilice esta sección para interactuar con la Inteligencia Artificial de asistencia para este curso.</p>
<ul>
    <li><a href="{n8n_chat_url.rstrip('/')}" target="_blank">{moodle_config.chat_link_name}</a>: Acceda aquí para chatear con la IA.</li>
    <li>Carpeta "<strong>Documentos Entrenai</strong>": Suba aquí los documentos PDF, DOCX, PPTX que la IA utilizará como base de conocimiento.</li>
    <li><a href="{refresh_files_url}" target="_blank">{moodle_config.refresh_link_name}</a>: Haga clic aquí después de subir nuevos archivos o modificar existentes en la carpeta "Documentos Entrenai" para que la IA los procese.</li>
    <li><a href="{refresh_chat_config_url}" target="_blank">Actualizar Configuraciones del Chat</a>: Haga clic aquí después de modificar las configuraciones del chat (abajo) para aplicar los cambios.</li>
</ul>
{edit_instruction_message}
<h5>Configuración del Chat de IA:</h5>
<ul>
    <li><strong>Mensajes Iniciales:</strong> {initial_messages if initial_messages else DEFAULT_UNSPECIFIED_TEXT}</li>
    <li><strong>Mensaje del Sistema:</strong> {system_message if system_message else DEFAULT_UNSPECIFIED_TEXT}</li>
    <li><strong>Marcador de Posición de Entrada:</strong> {input_placeholder if input_placeholder else DEFAULT_UNSPECIFIED_TEXT}</li>
    <li><strong>Título del Chat:</strong> {chat_title if chat_title else DEFAULT_UNSPECIFIED_TEXT}</li>
</ul>
"""
        return html_summary
    
    def update_section_summary(
        self,
        course_id: int,
        section_id: int,
        section_name: str,
        html_summary: str
    ):
        """Actualiza el summary de la sección en Moodle."""
        payload = {
            "courseid": course_id,
            "sections": [
                {
                    "type": "id",
                    "section": section_id,
                    "name": section_name,
                    "summary": html_summary,
                    "summaryformat": 1,  # HTML format
                    "visible": 1,
                }
            ],
        }
        
        logger.info(f"Actualizando sección ID {section_id} con summary")
        update_result = self.moodle._make_request("local_wsmanagesections_update_sections", payload)
        logger.info(f"Resultado de actualización: {update_result}")
        return update_result
    
    def get_section_summary(self, course_id: int, section_name: str) -> Optional[str]:
        """Obtiene el summary de una sección específica."""
        section = self.moodle.get_section_by_name(course_id, section_name)
        if not section:
            return None
        
        section_details = self.moodle.get_section_details(section.id, course_id)
        return section_details.summary if section_details else None
    
    def extract_chat_config_from_html(self, html_content: str) -> Dict[str, str]:
        """Extrae configuraciones del chat desde el HTML Summary."""
        config = {}
        
        def clean_extracted_value(value):
            if not value:
                return None
            cleaned = value.strip()
            if cleaned.startswith('"') and cleaned.endswith('"'):
                cleaned = cleaned[1:-1]
            while cleaned.startswith('"""') and cleaned.endswith('"""'):
                cleaned = cleaned[3:-3]
            while '""' in cleaned:
                cleaned = cleaned.replace('""', '"')
            return cleaned if cleaned else None
        
        patterns = {
            'initial_messages': r'<strong>Mensajes Iniciales:</strong>\s*([^<\n\r]+)',
            'system_message': r'<strong>Mensaje del Sistema:</strong>\s*([^<\n\r]+)',
            'input_placeholder': r'<strong>Marcador de Posición de Entrada:</strong>\s*([^<\n\r]+)',
            'chat_title': r'<strong>Título del Chat:</strong>\s*([^<\n\r]+)'
        }
        
        for key, pattern in patterns.items():
            match = re.search(pattern, html_content, re.IGNORECASE | re.MULTILINE)
            if match:
                extracted_value = clean_extracted_value(match.group(1))
                if extracted_value:
                    config[key] = extracted_value
        
        return config
