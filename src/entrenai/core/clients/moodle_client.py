from pathlib import Path
from typing import List, Optional, Dict, Any
from urllib.parse import urljoin

import requests

from src.entrenai.api.models import (
    MoodleCourse,
    MoodleSection,
    MoodleModule,
    MoodleFile,
)
from src.entrenai.config import MoodleConfig
from src.entrenai.config.logger import get_logger

logger = get_logger(__name__)


class MoodleAPIError(Exception):
    """Excepción personalizada para errores de la API de Moodle."""

    def __init__(
        self,
        message: str,
        status_code: Optional[int] = None,
        response_data: Optional[Any] = None,
    ):
        super().__init__(message)
        self.status_code = status_code
        self.response_data = response_data

    def __str__(self):
        return f"{super().__str__()} (Código de Estado: {self.status_code}, Respuesta: {self.response_data})"


class MoodleClient:
    """Cliente para interactuar con la API de Web Services de Moodle."""

    base_url: Optional[str]

    def __init__(
        self, config: MoodleConfig, session: Optional[requests.Session] = None
    ):
        self.config = config
        if not config.url:
            logger.error(
                "URL de Moodle no configurada. MoodleClient no será funcional."
            )
            self.base_url = None
        else:
            clean_url = config.url + "/" if not config.url.endswith("/") else config.url
            self.base_url = urljoin(clean_url, "webservice/rest/server.php")

        self.session = session or requests.Session()
        if self.config.token:
            self.session.params = {
                "wstoken": self.config.token,
                "moodlewsrestformat": "json",
            }  # type: ignore

        if self.base_url:
            logger.info(
                f"MoodleClient inicializado para URL: {self.base_url.rsplit('/', 1)[0]}"
            )
        else:
            logger.warning("MoodleClient inicializado sin una URL base válida.")

    @staticmethod
    def _process_courses_data(courses_data: Any) -> List[MoodleCourse]:
        """
        Helper para procesar y validar datos de cursos de la API de Moodle.

        Args:
            courses_data: Datos de cursos de la API

        Returns:
            Lista de objetos MoodleCourse

        Raises:
            MoodleAPIError: Si los datos no están en el formato esperado
        """
        if not isinstance(courses_data, list):
            if (
                isinstance(courses_data, dict)
                and "courses" in courses_data
                and isinstance(courses_data["courses"], list)
            ):
                courses_data = courses_data["courses"]
            else:
                raise MoodleAPIError(
                    "Los datos de cursos no están en el formato de lista esperado.",
                    response_data=courses_data,
                )
        return [MoodleCourse(**cd) for cd in courses_data]

    def _format_moodle_params(
        self, in_args: Any, prefix: str = "", out_dict: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Transforma una estructura de diccionario/lista a un diccionario plano para la API de Moodle."""
        if out_dict is None:
            out_dict = {}
        if not isinstance(in_args, (list, dict)):
            out_dict[prefix] = in_args
            return out_dict
        if isinstance(in_args, list):
            for idx, item in enumerate(in_args):
                self._format_moodle_params(item, f"{prefix}[{idx}]", out_dict)
        elif isinstance(in_args, dict):
            for key, item in in_args.items():
                self._format_moodle_params(
                    item, f"{prefix}[{key}]" if prefix else key, out_dict
                )
        return out_dict

    def _make_request(
        self,
        wsfunction: str,
        payload_params: Optional[Dict[str, Any]] = None,
        http_method: str = "POST",
    ) -> Any:
        """Realiza una petición a la API de Moodle."""
        if not self.base_url:
            raise MoodleAPIError("URL base de Moodle no configurada.")

        query_params_for_url = {
            "wstoken": self.config.token,
            "moodlewsrestformat": "json",
            "wsfunction": wsfunction,
        }
        formatted_api_payload = (
            self._format_moodle_params(payload_params) if payload_params else {}
        )
        response: Optional[requests.Response] = None

        try:
            logger.debug(
                f"Llamando a la función API de Moodle '{wsfunction}' con método {http_method.upper()}. URL: {self.base_url}"
            )
            if http_method.upper() == "POST":
                response = self.session.post(
                    self.base_url,
                    params=query_params_for_url,
                    data=formatted_api_payload,
                )
            elif http_method.upper() == "GET":
                all_get_params = {**query_params_for_url, **formatted_api_payload}
                response = self.session.get(self.base_url, params=all_get_params)
            else:
                raise MoodleAPIError(f"Método HTTP no soportado: {http_method}")
            response.raise_for_status()
            json_data = response.json()
            if isinstance(json_data, dict) and "exception" in json_data:
                err_msg = json_data.get("message", "Error desconocido de Moodle")
                logger.error(
                    f"Error de la API de Moodle para '{wsfunction}': {json_data.get('errorcode')} - {err_msg}"
                )
                raise MoodleAPIError(message=err_msg, response_data=json_data)
            return json_data
        except requests.exceptions.HTTPError as http_err:
            resp_text = (
                http_err.response.text
                if http_err.response is not None
                else "Sin respuesta"
            )
            status = (
                http_err.response.status_code if http_err.response is not None else None
            )
            logger.error(
                f"Error HTTP para '{wsfunction}': {http_err} - Respuesta: {resp_text}"
            )
            raise MoodleAPIError(
                f"Error HTTP: {status}", status_code=status, response_data=resp_text
            ) from http_err
        except requests.exceptions.RequestException as req_err:
            logger.error(f"Excepción de petición para '{wsfunction}': {req_err}")
            raise MoodleAPIError(str(req_err)) from req_err
        except ValueError as json_err:
            resp_text = response.text if response is not None else "Sin respuesta"
            logger.error(
                f"Error de decodificación JSON para '{wsfunction}': {json_err} - Respuesta: {resp_text}"
            )
            raise MoodleAPIError(
                f"Falló la decodificación de la respuesta JSON: {json_err}",
                response_data=resp_text,
            ) from json_err

    def get_courses_by_user(self, user_id: int) -> List[MoodleCourse]:
        """Obtiene los cursos de un usuario específico."""
        if user_id <= 0:
            raise ValueError("ID de usuario inválido.")
        logger.info(f"Obteniendo cursos para user_id: {user_id}")
        try:
            courses_data = self._make_request(
                "core_enrol_get_users_courses", {"userid": user_id}
            )
            return self._process_courses_data(courses_data)
        except MoodleAPIError as e:
            logger.error(f"Falló la obtención de cursos para el usuario {user_id}: {e}")
            raise
        except Exception as e:
            logger.exception(
                f"Error inesperado en get_courses_by_user para el usuario {user_id}: {e}"
            )
            raise MoodleAPIError(f"Error inesperado obteniendo cursos: {e}")

    def get_section_by_name(
        self, course_id: int, section_name: str
    ) -> Optional[MoodleSection]:
        """Recupera una sección específica por su nombre dentro de un curso."""
        logger.info(f"Buscando sección '{section_name}' en curso {course_id}")
        try:
            course_contents = self._make_request(
                "core_course_get_contents", {"courseid": course_id}
            )
            if not isinstance(course_contents, list):
                logger.error(
                    f"Se esperaba una lista de secciones, se obtuvo {type(course_contents)}"
                )
                return None
            for section_data in course_contents:
                if section_data.get("name") == section_name:
                    logger.info(
                        f"Sección '{section_name}' encontrada con ID: {section_data.get('id')}"
                    )
                    return MoodleSection(**section_data)
            logger.info(f"Sección '{section_name}' no encontrada en curso {course_id}.")
            return None
        except MoodleAPIError as e:
            logger.error(f"Error de API buscando sección '{section_name}': {e}")
            return None
        except Exception as e:
            logger.exception(f"Error inesperado buscando sección '{section_name}': {e}")
            return None

    def create_course_section(
        self, course_id: int, section_name: str, position: int = 1
    ) -> Optional[MoodleSection]:
        """Asegura la existencia de una sección en un curso, creándola si es necesario."""
        logger.info(
            f"Asegurando sección '{section_name}' en curso {course_id} en posición {position}"
        )
        existing_section = self.get_section_by_name(course_id, section_name)
        if existing_section:
            logger.info(
                f"Sección '{section_name}' ya existe con ID {existing_section.id}. Usando existente."
            )
            return existing_section

        logger.info(f"Sección '{section_name}' no encontrada. Intentando crear.")
        try:
            create_payload = {"courseid": course_id, "position": position, "number": 1}
            created_data = self._make_request(
                "local_wsmanagesections_create_sections", create_payload
            )
            if not isinstance(created_data, list) or not created_data:
                raise MoodleAPIError(
                    "Falló la creación de la estructura de la sección.",
                    response_data=created_data,
                )

            new_section_info = created_data[0]
            new_section_id = new_section_info.get("id") or new_section_info.get(
                "sectionid"
            )
            if new_section_id is None:
                raise MoodleAPIError(
                    "Datos de sección creada no contienen 'id' o 'sectionid'.",
                    response_data=new_section_info,
                )

            logger.info(
                f"Estructura de sección creada con ID: {new_section_id}. Obteniendo detalles..."
            )
            # Obtener los detalles de la sección recién creada (tendrá un nombre por defecto)
            get_payload = {"courseid": course_id, "sectionids": [new_section_id]}
            sections_data = self._make_request(
                "local_wsmanagesections_get_sections", payload_params=get_payload
            )
            if isinstance(sections_data, list) and sections_data:
                # El nombre de la sección aquí será el nombre por defecto asignado por Moodle
                # El renombrado se hará en una llamada posterior desde el router si es necesario.
                section_info_retrieved = sections_data[0]
                logger.info(
                    f"Sección creada y recuperada: ID {section_info_retrieved.get('id')}, Nombre por defecto '{section_info_retrieved.get('name')}'"
                )
                return MoodleSection(**section_info_retrieved)
            else:
                logger.error(
                    f"No se pudieron obtener los detalles de la sección recién creada ID {new_section_id}."
                )
                # Devolver un objeto MoodleSection con los datos conocidos si la obtención falla
                return MoodleSection(
                    id=new_section_id,
                    name=f"Sección {new_section_id} (Nombre Pendiente)",
                    section=new_section_info.get("section", position),
                )

        except MoodleAPIError as e:
            logger.error(
                f"Error creando sección '{section_name}' (nombre deseado, no necesariamente el actual): {e}"
            )
            return None
        except Exception as e:
            logger.exception(f"Error inesperado creando sección '{section_name}': {e}")
            return None

    def create_module_in_section(
        self,
        course_id: int,
        section_id: int,
        module_name: str,
        mod_type: str,
        instance_params: Optional[Dict[str, Any]] = None,
        common_module_options: Optional[List[Dict[str, Any]]] = None,
    ) -> Optional[MoodleModule]:
        """Crea o devuelve un módulo existente en la sección especificada del curso."""
        existing_module = self.get_course_module_by_name(
            course_id, section_id, module_name, mod_type
        )
        if existing_module:
            logger.info(
                f"Módulo '{module_name}' (tipo: {mod_type}) ya existe en sección {section_id}. Usando ID existente: {existing_module.id}"
            )
            return existing_module

        logger.info(
            f"Creando módulo '{module_name}' (tipo: {mod_type}) en curso {course_id}, sección {section_id}"
        )
        try:
            module_data_for_api: Dict[str, Any] = {
                "modname": mod_type,
                "name": module_name,
                "section": section_id,
                # Moodle necesita el ID de la sección donde se creará el módulo
            }

            # Incorporar instance_params y common_module_options en module_data_for_api
            # La API local_wsmanagesections_update_sections espera los parámetros del módulo directamente
            if instance_params:
                module_data_for_api.update(instance_params)
            if common_module_options:  # Estos son usualmente para core_course_add_module, adaptar si es necesario
                for opt in common_module_options:
                    module_data_for_api[opt["name"]] = opt["value"]

            payload = {"courseid": course_id, "modules": [module_data_for_api]}

            self._make_request("local_wsmanagesections_update_sections", payload)

            # Después de crear/actualizar, obtener el módulo para devolverlo con su ID
            return self.get_course_module_by_name(
                course_id, section_id, module_name, mod_type
            )

        except MoodleAPIError as e:
            logger.error(f"Error de API añadiendo módulo '{module_name}': {e}")
            return None
        except Exception as e:
            logger.exception(f"Error inesperado añadiendo módulo '{module_name}': {e}")
            return None

    def create_folder_in_section(
        self, course_id: int, section_id: int, folder_name: str, intro: str = ""
    ) -> Optional[MoodleModule]:
        """Asegura la existencia de una carpeta en una sección, creándola si es necesario."""
        logger.info(
            f"Asegurando carpeta '{folder_name}' en curso {course_id}, sección {section_id}"
        )
        instance_params = {
            "intro": intro or f"Carpeta para {folder_name}",
            "introformat": 1,  # Formato HTML para la intro
            "display": 0,  # 0 para mostrar en página de curso, 1 para página separada
            "showexpanded": 1,  # 1 para mostrar expandido por defecto
        }
        # common_module_options para visibilidad, etc.
        common_opts = [{"name": "visible", "value": "1"}]
        return self.create_module_in_section(
            course_id, section_id, folder_name, "folder", instance_params, common_opts
        )

    def create_url_in_section(
        self,
        course_id: int,
        section_id: int,
        url_name: str,
        external_url: str,
        description: str = "",
        display_mode: int = 0,
        # 0: Automático, 1: Embebido, 2: Abrir, 3: En pop-up
    ) -> Optional[MoodleModule]:
        """Asegura la existencia de un recurso URL en una sección, creándolo si es necesario."""
        logger.info(
            f"Asegurando URL '{url_name}' -> '{external_url}' en curso {course_id}, sección {section_id}"
        )
        instance_params = {
            "externalurl": external_url,
            "intro": description or f"Enlace a {url_name}",
            "introformat": 1,
            "display": display_mode,
        }
        common_opts = [{"name": "visible", "value": "1"}]
        return self.create_module_in_section(
            course_id, section_id, url_name, "url", instance_params, common_opts
        )

    def get_course_module_by_name(
        self,
        course_id: int,
        target_section_id: int,
        target_module_name: str,
        target_mod_type: Optional[str] = None,
    ) -> Optional[MoodleModule]:
        """Encuentra un módulo específico por nombre dentro de una sección de un curso."""
        logger.info(
            f"Buscando módulo '{target_module_name}' (tipo: {target_mod_type or 'cualquiera'}) en curso {course_id}, sección {target_section_id}"
        )
        try:
            course_contents = self._make_request(
                "core_course_get_contents", {"courseid": course_id}
            )
            if not isinstance(course_contents, list):
                logger.error(
                    f"Se esperaba lista de contenidos del curso, se obtuvo {type(course_contents)}"
                )
                return None
            for section_data in course_contents:
                if section_data.get("id") == target_section_id:
                    for module_data in section_data.get("modules", []):
                        name_match = module_data.get("name") == target_module_name
                        type_match = (
                            target_mod_type is None
                            or module_data.get("modname") == target_mod_type
                        )
                        if name_match and type_match:
                            logger.info(
                                f"Módulo '{target_module_name}' encontrado (ID: {module_data.get('id')})"
                            )
                            return MoodleModule(**module_data)
                    logger.info(
                        f"Módulo '{target_module_name}' no encontrado en sección {target_section_id}."
                    )
                    return None  # Módulo no encontrado en la sección objetivo
            logger.info(
                f"Sección {target_section_id} no encontrada en curso {course_id}."
            )
            return None  # Sección objetivo no encontrada
        except MoodleAPIError as e:
            logger.error(f"Error de API buscando módulo '{target_module_name}': {e}")
            return None
        except Exception as e:
            logger.exception(
                f"Error inesperado buscando módulo '{target_module_name}': {e}"
            )
            return None

    def get_folder_files(self, folder_cmid: int) -> List[MoodleFile]:
        """Recupera todos los archivos de un módulo de carpeta de Moodle.

        Args:
            folder_cmid: The course module ID of the folder.

        Returns:
            A list of MoodleFile objects representing files in the folder.
        """
        logger.info(
            f"Obteniendo archivos para el módulo de carpeta ID (cmid): {folder_cmid}"
        )
        try:
            # First get module details to verify it's a folder and get the course ID
            module_details = self._make_request(
                "core_course_get_course_module", {"cmid": folder_cmid}
            )
            print(module_details)
            if not module_details or "cm" not in module_details:
                logger.error(
                    f"No se pudieron obtener detalles para el módulo con cmid {folder_cmid}"
                )
                return []

            cm_info = module_details["cm"]
            logger.debug(f"Detalles del módulo: {module_details}")

            if cm_info.get("modname") != "folder":
                logger.error(
                    f"Módulo con ID {folder_cmid} no es una carpeta, es un '{cm_info.get('modname')}'"
                )
                return []

            # Get the course ID from module details
            course_id = cm_info.get("course")
            if not course_id:
                logger.error(
                    f"No se pudo determinar el ID del curso para el módulo {folder_cmid}"
                )
                return []

            return self._extract_folder_files(course_id, folder_cmid)

        except MoodleAPIError as e:
            logger.error(
                f"Error de API obteniendo archivos para carpeta {folder_cmid}: {e}"
            )
            return []
        except Exception as e:
            logger.exception(
                f"Error inesperado obteniendo archivos para carpeta {folder_cmid}: {e}"
            )
            return []

    def _extract_folder_files(
        self, course_id: int, folder_cmid: int
    ) -> List[MoodleFile]:
        """Helper method to extract files from a folder module in course contents.

        Args:
            course_id: The ID of the course containing the folder.
            folder_cmid: The course module ID of the folder.

        Returns:
            List of MoodleFile objects.
        """
        try:
            # Get all contents for this course
            course_contents = self._make_request(
                "core_course_get_contents", {"courseid": course_id}
            )

            for section in course_contents:
                for module in section.get("modules", []):
                    if module.get("id") == folder_cmid:
                        return self._parse_folder_contents(module, folder_cmid)

            logger.warning(
                f"Módulo de carpeta {folder_cmid} no encontrado en curso {course_id}"
            )
            return []
        except Exception as e:
            logger.exception(f"Error extrayendo archivos de carpeta: {e}")
            return []

    @staticmethod
    def _parse_folder_contents(module: dict, folder_cmid: int) -> List[MoodleFile]:
        """Parse the contents of a folder module to extract file information.

        Args:
            module: The module data containing contents.
            folder_cmid: The folder module ID for logging.

        Returns:
            List of MoodleFile objects.
        """
        files_data = []
        for content in module.get("contents", []):
            required_fields = (
                "filename",
                "filepath",
                "filesize",
                "fileurl",
                "timemodified",
            )

            if content.get("type") == "file" and all(
                k in content for k in required_fields
            ):
                files_data.append(MoodleFile(**content))
                logger.debug(f"Archivo encontrado: {content.get('filename')}")
            else:
                logger.warning(
                    f"Omitiendo contenido en carpeta {folder_cmid}: {content}"
                )

        logger.info(
            f"Se encontraron {len(files_data)} archivos en la carpeta {folder_cmid}"
        )
        return files_data

    def download_file(self, file_url: str, download_dir: Path, filename: str) -> Path:
        """Descarga un archivo desde una URL de Moodle a un directorio local."""
        if not self.config.token:
            raise MoodleAPIError(
                "Token de Moodle no configurado, no se pueden descargar archivos de forma segura."
            )

        download_dir.mkdir(parents=True, exist_ok=True)
        local_filepath = download_dir / filename
        logger.info(
            f"Descargando archivo de Moodle desde {file_url} a {local_filepath}"
        )
        try:
            # Asegurar que el token esté en la URL si es necesario
            # Las URLs de Moodle a veces ya lo incluyen, otras no.
            effective_file_url = file_url
            if (
                "token=" not in file_url
                and "wstoken=" not in file_url
                and self.config.token
            ):
                effective_file_url = file_url + (
                    f"&token={self.config.token}"
                    if "?" in file_url
                    else f"?token={self.config.token}"
                )

            # Configurar headers específicos para evitar compresión automática
            headers = {
                "Accept-Encoding": "identity",  # Evitar compresión automática
            }

            # Descargar el archivo con stream=True para evitar cargar todo en memoria
            with requests.get(effective_file_url, stream=True, headers=headers) as r:
                r.raise_for_status()
                # Verificar el tipo de contenido para determinar si es binario o texto
                content_type = r.headers.get("Content-Type", "")

                # Modo de escritura basado en el tipo de contenido
                if "text/" in content_type or content_type.endswith(
                    ("/markdown", "/md")
                ):
                    # Para archivos de texto, guardar con codificación adecuada
                    content = r.content.decode("utf-8", errors="replace")
                    with open(local_filepath, "w", encoding="utf-8") as f:
                        f.write(content)
                else:
                    # Para archivos binarios, guardar en modo binario
                    with open(local_filepath, "wb") as f:
                        for chunk in r.iter_content(chunk_size=8192):
                            if chunk:  # Filtrar keepalive chunks vacíos
                                f.write(chunk)

            logger.info(f"Archivo '{filename}' descargado exitosamente.")
            return local_filepath
        except requests.exceptions.HTTPError as http_err:
            logger.error(
                f"Error HTTP descargando '{filename}': {http_err} (URL: {file_url})"
            )
            raise MoodleAPIError(
                f"Falló la descarga del archivo '{filename}': {http_err}"
            ) from http_err
        except Exception as e:
            logger.exception(
                f"Error descargando archivo '{filename}' desde {file_url}: {e}"
            )
            raise MoodleAPIError(
                f"Error inesperado descargando archivo '{filename}': {e}"
            ) from e

    def get_all_courses(self) -> List[MoodleCourse]:
        """Recupera todos los cursos disponibles en el sitio Moodle."""
        logger.info("Obteniendo todos los cursos disponibles de Moodle")
        try:
            courses_data = self._make_request("core_course_get_courses")
            return self._process_courses_data(courses_data)
        except MoodleAPIError as e:
            logger.error(f"Falló la obtención de todos los cursos: {e}")
            raise
        except Exception as e:
            logger.exception(f"Error inesperado en get_all_courses: {e}")
            raise MoodleAPIError(f"Error inesperado obteniendo todos los cursos: {e}")

    def get_course_n8n_settings(self, course_id: int) -> Optional[Dict[str, Any]]:
        """
        Obtiene las configuraciones de N8N específicas de un curso desde Moodle.

        Args:
            course_id: ID del curso

        Returns:
            Diccionario con las configuraciones o None si no se encuentran
        """
        try:
            payload_params = {"courseid": course_id}
            
            response_data = self._make_request(
                "local_entrenai_get_course_n8n_settings",
                payload_params
            )

            if response_data and not isinstance(response_data, dict) or "exception" in response_data:
                logger.warning(f"Configuraciones N8N no disponibles para curso {course_id}")
                return None

            # Procesar las configuraciones recibidas
            settings = {}
            if response_data.get("initial_message"):
                settings["initial_message"] = response_data["initial_message"]
            if response_data.get("system_message_append"):
                settings["system_message_append"] = response_data["system_message_append"]
            if response_data.get("chat_title"):
                settings["chat_title"] = response_data["chat_title"]
            if response_data.get("input_placeholder"):
                settings["input_placeholder"] = response_data["input_placeholder"]

            return settings if settings else None

        except MoodleAPIError as e:
            logger.warning(f"Error obteniendo configuraciones N8N para curso {course_id}: {e}")
            return None
        except Exception as e:
            logger.exception(f"Error inesperado obteniendo configuraciones N8N para curso {course_id}: {e}")
            return None
