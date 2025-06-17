"""Cliente simplificado para Moodle Web Services."""

from typing import List, Optional, Dict, Any
import httpx
from loguru import logger

from ..config.settings import Settings, get_settings
from ..models.moodle import MoodleCourse, MoodleSection, MoodleModule, MoodleFile


class MoodleAPIError(Exception):
    """Error de la API de Moodle."""
    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code


class MoodleClient:
    """Cliente simplificado para Moodle."""
    
    def __init__(self, settings: Settings):
        self.base_url = f"{settings.moodle.url.rstrip('/')}/webservice/rest/server.php"
        self.token = settings.moodle.token
        self.client = httpx.Client(timeout=30.0)
        logger.info(f"MoodleClient inicializado para {settings.moodle.url}")
    
    def _make_request(self, function: str, params: Dict[str, Any]) -> Any:
        """Realiza una petición a la API de Moodle."""
        request_params = {
            "wstoken": self.token,
            "moodlewsrestformat": "json",
            "wsfunction": function,
            **params
        }
        
        try:
            response = self.client.post(self.base_url, data=request_params)
            response.raise_for_status()
            
            data = response.json()
            
            # Verificar errores de Moodle
            if isinstance(data, dict) and "exception" in data:
                raise MoodleAPIError(
                    f"Error de Moodle: {data.get('message', 'Error desconocido')}",
                    status_code=response.status_code
                )
            
            return data
            
        except httpx.HTTPStatusError as e:
            raise MoodleAPIError(f"Error HTTP: {e.response.status_code}", e.response.status_code)
        except httpx.RequestError as e:
            raise MoodleAPIError(f"Error de conexión: {str(e)}")
    
    def get_course(self, course_id: int) -> Optional[MoodleCourse]:
        """Obtiene información de un curso."""
        try:
            courses = self._make_request("core_course_get_courses", {"options": {"ids": [course_id]}})
            if courses and len(courses) > 0:
                return MoodleCourse(**courses[0])
            return None
        except Exception as e:
            logger.error(f"Error obteniendo curso {course_id}: {e}")
            return None
    
    def get_course_sections(self, course_id: int) -> List[MoodleSection]:
        """Obtiene las secciones de un curso."""
        try:
            sections_data = self._make_request("core_course_get_contents", {"courseid": course_id})
            sections = []
            for section_data in sections_data:
                sections.append(MoodleSection(
                    id=section_data["id"],
                    name=section_data.get("name", f"Sección {section_data.get('section', 0)}"),
                    section=section_data.get("section", 0),
                    visible=section_data.get("visible", True),
                    summary=section_data.get("summary", "")
                ))
            return sections
        except Exception as e:
            logger.error(f"Error obteniendo secciones del curso {course_id}: {e}")
            return []
    
    def create_section(self, course_id: int, name: str, summary: str = "") -> Optional[MoodleSection]:
        """Crea una nueva sección en un curso."""
        try:
            sections = self._make_request("core_course_create_sections", {
                "sections": [{
                    "courseid": course_id,
                    "name": name,
                    "summary": summary
                }]
            })
            
            if sections and len(sections) > 0:
                section_data = sections[0]
                return MoodleSection(
                    id=section_data["id"],
                    name=name,
                    section=section_data["section"],
                    visible=True,
                    summary=summary
                )
            return None
        except Exception as e:
            logger.error(f"Error creando sección en curso {course_id}: {e}")
            return None
    
    def add_url_to_section(self, course_id: int, section_id: int, name: str, url: str, description: str = "") -> Optional[MoodleModule]:
        """Añade un enlace URL a una sección."""
        try:
            # Crear el módulo URL
            modules = self._make_request("core_course_create_modules", {
                "modules": [{
                    "courseid": course_id,
                    "name": name,
                    "modname": "url",
                    "section": section_id,
                    "visible": 1,
                    "instance": {
                        "externalurl": url,
                        "intro": description,
                        "display": 5  # Display in pop-up
                    }
                }]
            })
            
            if modules and len(modules) > 0:
                module_data = modules[0]
                return MoodleModule(
                    id=module_data["id"],
                    name=name,
                    modname="url",
                    visible=True,
                    url=url
                )
            return None
        except Exception as e:
            logger.error(f"Error añadiendo URL a sección {section_id}: {e}")
            return None
    
    def get_folder_files(self, folder_id: int) -> List[MoodleFile]:
        """Obtiene archivos de una carpeta."""
        try:
            # TODO: Implementar lógica simplificada para obtener archivos
            # Esta implementación requiere más investigación de la API de Moodle
            logger.warning("get_folder_files no implementado completamente")
            return []
        except Exception as e:
            logger.error(f"Error obteniendo archivos de carpeta {folder_id}: {e}")
            return []
    
    def get_course_files(self, course_id: int) -> List[MoodleFile]:
        """Obtiene todos los archivos de un curso."""
        try:
            # TODO: Implementar lógica para obtener archivos del curso
            logger.warning("get_course_files no implementado completamente") 
            return []
        except Exception as e:
            logger.error(f"Error obteniendo archivos del curso {course_id}: {e}")
            return []
    
    def close(self):
        """Cierra el cliente HTTP."""
        self.client.close()


def get_moodle_client(settings: Settings = None) -> MoodleClient:
    """Dependency para obtener el cliente de Moodle."""
    if settings is None:
        settings = get_settings()
    return MoodleClient(settings)
