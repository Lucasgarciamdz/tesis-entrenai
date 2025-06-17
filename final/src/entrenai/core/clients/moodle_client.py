from typing import List, Optional, Dict, Any
from urllib.parse import urljoin
import requests
from loguru import logger


class MoodleAPIError(Exception):
    """Excepción para errores de la API de Moodle."""
    
    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code


class MoodleClient:
    """Cliente simplificado para interactuar con Moodle."""
    
    def __init__(self, url: str, token: str):
        self.base_url = urljoin(url.rstrip('/') + '/', "webservice/rest/server.php")
        self.token = token
        self.session = requests.Session()
        self.session.params = {
            "wstoken": token,
            "moodlewsrestformat": "json",
        }
        logger.info(f"MoodleClient inicializado para: {url}")
    
    def _make_request(self, wsfunction: str, **params) -> Any:
        """Realiza una petición a la API de Moodle."""
        data = {"wsfunction": wsfunction, **params}
        
        try:
            response = self.session.post(self.base_url, data=data)
            response.raise_for_status()
            result = response.json()
            
            if isinstance(result, dict) and "exception" in result:
                raise MoodleAPIError(f"Error de Moodle: {result.get('message', 'Error desconocido')}")
            
            return result
        except requests.RequestException as e:
            raise MoodleAPIError(f"Error de conexión: {str(e)}")
    
    def get_courses_by_user(self, user_id: int) -> List[Dict[str, Any]]:
        """Obtiene los cursos de un usuario."""
        return self._make_request("core_enrol_get_users_courses", userid=user_id)
    
    def get_course_info(self, course_id: int) -> Dict[str, Any]:
        """Obtiene información básica de un curso."""
        courses = self._make_request("core_course_get_courses", options={"ids": [course_id]})
        if not courses:
            raise MoodleAPIError(f"Curso {course_id} no encontrado")
        return courses[0]
    
    def get_folder_files(self, course_id: int, folder_name: str = "Archivos del curso") -> List[Dict[str, Any]]:
        """Obtiene archivos de una carpeta del curso."""
        try:
            # Obtener el contenido del curso
            contents = self._make_request("core_course_get_contents", courseid=course_id)
            
            files = []
            for section in contents:
                for module in section.get("modules", []):
                    if module.get("modname") == "folder" and folder_name in module.get("name", ""):
                        for content in module.get("contents", []):
                            if content.get("type") == "file":
                                files.append({
                                    "filename": content.get("filename"),
                                    "fileurl": content.get("fileurl"),
                                    "filesize": content.get("filesize", 0),
                                    "mimetype": content.get("mimetype"),
                                    "timecreated": content.get("timecreated", 0),
                                })
            return files
        except Exception as e:
            logger.error(f"Error obteniendo archivos del curso {course_id}: {e}")
            return []
    
    def download_file(self, file_url: str) -> bytes:
        """Descarga un archivo desde Moodle."""
        try:
            response = self.session.get(file_url)
            response.raise_for_status()
            return response.content
        except requests.RequestException as e:
            raise MoodleAPIError(f"Error descargando archivo: {str(e)}")
    
    def create_course_section(self, course_id: int, section_name: str) -> int:
        """Crea una nueva sección en el curso."""
        sections = [{"type": "num", "section": 0, "summary": "", "summaryformat": 1}]
        result = self._make_request(
            "core_course_create_sections",
            courseid=course_id,
            sections=sections
        )
        return result[0]["id"] if result else 0
    
    def create_url_in_section(self, course_id: int, section_id: int, name: str, url: str, description: str = "") -> int:
        """Crea un enlace URL en una sección."""
        modules = [{
            "modulename": "url",
            "instance": {
                "course": course_id,
                "name": name,
                "intro": description,
                "introformat": 1,
                "externalurl": url,
                "display": 0,
                "displayoptions": "",
            }
        }]
        
        result = self._make_request(
            "core_course_create_modules",
            modules=modules
        )
        
        if result and result[0].get("instance"):
            # Mover el módulo a la sección correcta
            self._make_request(
                "core_course_edit_section",
                id=section_id,
                sequence=f"{result[0]['instance']['cmid']}"
            )
            return result[0]["instance"]["cmid"]
        return 0


def get_moodle_client() -> MoodleClient:
    """Función dependency para FastAPI."""
    from entrenai.config.settings import settings
    return MoodleClient(url=settings.moodle_url, token=settings.moodle_token)
