from pathlib import Path
from typing import List, Optional, Dict, Any
from urllib.parse import urljoin

import requests

from entrenai_refactor.api import modelos as modelos_api
from entrenai_refactor.config.configuracion import configuracion_global
from entrenai_refactor.config.registrador import obtener_registrador

registrador = obtener_registrador(__name__)


class ErrorAPIMoodle(Exception):
    """Excepción personalizada para errores de la API de Moodle."""

    def __init__(
        self,
        mensaje: str,
        codigo_estado: Optional[int] = None,
        datos_respuesta: Optional[Any] = None,
    ):
        super().__init__(mensaje)
        self.codigo_estado = codigo_estado
        self.datos_respuesta = datos_respuesta
        registrador.debug(f"Excepción ErrorAPIMoodle creada: {mensaje}, Código: {codigo_estado}, Respuesta: {datos_respuesta}")

    def __str__(self):
        return f"{super().__str__()} (Código de Estado: {self.codigo_estado}, Respuesta: {self.datos_respuesta})"


class ClienteMoodle:
    """Cliente para interactuar con la API de Web Services de Moodle."""

    url_base_api: Optional[str]

    def __init__(self, sesion: Optional[requests.Session] = None):
        self.config_moodle = configuracion_global.moodle
        if not self.config_moodle.url_moodle: # CAMBIADO: url -> url_moodle
            registrador.error("URL de Moodle no configurada. ClienteMoodle no será funcional.")
            self.url_base_api = None
        else:
            # Asegurar que la URL base termine con una barra
            url_limpia = self.config_moodle.url_moodle.rstrip("/") + "/" # CAMBIADO: url -> url_moodle
            self.url_base_api = urljoin(url_limpia, "webservice/rest/server.php")

        self.sesion = sesion or requests.Session()
        if self.config_moodle.token_api_moodle: # CAMBIADO: token -> token_api_moodle
            # Configurar parámetros por defecto para la sesión
            self.sesion.params = {
                "wstoken": self.config_moodle.token_api_moodle, # CAMBIADO: token -> token_api_moodle
                "moodlewsrestformat": "json",
            }

        if self.url_base_api:
            registrador.info(f"ClienteMoodle inicializado para URL: {self.url_base_api.rsplit('/', 1)[0]}/...")
        else:
            registrador.warning("ClienteMoodle inicializado sin una URL base API válida.")

    @staticmethod
    def _procesar_datos_cursos(datos_cursos_api: Any) -> List[modelos_api.CursoMoodle]:
        """
        Procesa y valida los datos de cursos recibidos de la API de Moodle.
        Transforma los datos crudos en una lista de objetos CursoMoodle.
        """
        registrador.debug(f"Procesando datos de cursos recibidos: {type(datos_cursos_api)}")
        cursos_procesados = []

        if isinstance(datos_cursos_api, list):
            # Formato esperado: una lista de diccionarios de cursos
            for curso_data in datos_cursos_api:
                if not isinstance(curso_data, dict):
                    registrador.warning(f"Elemento de curso inesperado (no es dict): {curso_data}")
                    continue
                try:
                    cursos_procesados.append(modelos_api.CursoMoodle(**curso_data))
                except Exception as e: # Captura error de validación de Pydantic u otros
                    registrador.error(f"Error al procesar un curso individual ({curso_data.get('id', 'ID desconocido')}): {e}")
            return cursos_procesados
        elif isinstance(datos_cursos_api, dict) and "courses" in datos_cursos_api and isinstance(datos_cursos_api["courses"], list):
            # Formato alternativo: un diccionario con una clave "courses" que contiene la lista
            registrador.debug("Detectado formato de respuesta con clave 'courses'.")
            for curso_data in datos_cursos_api["courses"]:
                if not isinstance(curso_data, dict):
                    registrador.warning(f"Elemento de curso inesperado en 'courses' (no es dict): {curso_data}")
                    continue
                try:
                    cursos_procesados.append(modelos_api.CursoMoodle(**curso_data))
                except Exception as e:
                    registrador.error(f"Error al procesar un curso individual desde 'courses' ({curso_data.get('id', 'ID desconocido')}): {e}")
            return cursos_procesados
        else:
            mensaje_error = "Los datos de cursos no están en un formato esperado (lista o dict con 'courses')."
            registrador.error(f"{mensaje_error} Datos recibidos: {datos_cursos_api}")
            raise ErrorAPIMoodle(mensaje_error, datos_respuesta=datos_cursos_api)

    def _formatear_parametros_moodle(
        self, datos_entrada: Any, prefijo_actual: str = "", dict_salida_plano: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Transforma una estructura anidada de diccionarios/listas a un diccionario plano,
        formateando las claves como espera la API de Moodle (ej. 'courses[0][id]').
        """
        if dict_salida_plano is None:
            dict_salida_plano = {}

        if not isinstance(datos_entrada, (list, dict)):
            # Es un valor simple, lo asignamos directamente con el prefijo actual
            dict_salida_plano[prefijo_actual] = datos_entrada
            return dict_salida_plano

        if isinstance(datos_entrada, list):
            # Si es una lista, iteramos sobre sus elementos
            for indice, valor_item in enumerate(datos_entrada):
                # Creamos el nuevo prefijo para el elemento de la lista
                nuevo_prefijo = f"{prefijo_actual}[{indice}]"
                self._formatear_parametros_moodle(valor_item, nuevo_prefijo, dict_salida_plano)
        elif isinstance(datos_entrada, dict):
            # Si es un diccionario, iteramos sobre sus pares clave-valor
            for clave_item, valor_item in datos_entrada.items():
                # Creamos el nuevo prefijo para el elemento del diccionario
                nuevo_prefijo = f"{prefijo_actual}[{clave_item}]" if prefijo_actual else clave_item
                self._formatear_parametros_moodle(valor_item, nuevo_prefijo, dict_salida_plano)

        return dict_salida_plano

    def _realizar_peticion_api(
        self,
        nombre_funcion_ws: str,
        parametros_payload: Optional[Dict[str, Any]] = None,
        metodo_http: str = "POST",
    ) -> Any:
        """Realiza una petición genérica a la API de Web Services de Moodle."""
        if not self.url_base_api:
            registrador.error("URL base de Moodle no configurada. No se puede realizar la petición.")
            raise ErrorAPIMoodle("URL base de Moodle no configurada.")

        # Parámetros base para la URL que identifican la función del WS
        parametros_url = {"wsfunction": nombre_funcion_ws}

        # El token y el formato de respuesta ya están en self.sesion.params por defecto

        # Formatear el payload si existe
        payload_api_formateado = (
            self._formatear_parametros_moodle(parametros_payload) if parametros_payload else {}
        )

        respuesta_http: Optional[requests.Response] = None # Para asegurar que esté definida en caso de error previo

        try:
            registrador.debug(
                f"Llamando a función API Moodle '{nombre_funcion_ws}' con método {metodo_http.upper()}. URL: {self.url_base_api}"
            )
            if metodo_http.upper() == "POST":
                respuesta_http = self.sesion.post(
                    self.url_base_api,
                    params=parametros_url, # Solo wsfunction aquí, token y format ya en la sesión
                    data=payload_api_formateado,
                    timeout=30, # Timeout en segundos
                )
            elif metodo_http.upper() == "GET":
                # Para GET, todos los parámetros (incluyendo los formateados del payload) van en la URL
                todos_parametros_get = {**parametros_url, **payload_api_formateado}
                respuesta_http = self.sesion.get(self.url_base_api, params=todos_parametros_get, timeout=30)
            else:
                registrador.error(f"Método HTTP no soportado: {metodo_http}")
                raise ErrorAPIMoodle(f"Método HTTP no soportado: {metodo_http}")

            # Verificar si la respuesta fue exitosa (códigos 2xx)
            respuesta_http.raise_for_status()

            # Intentar decodificar la respuesta JSON
            datos_json = respuesta_http.json()

            # Moodle puede devolver errores 200 pero con una estructura de excepción en el JSON
            if isinstance(datos_json, dict) and "exception" in datos_json:
                mensaje_error_moodle = datos_json.get("message", f"Error desconocido de Moodle en '{nombre_funcion_ws}'")
                codigo_error_moodle = datos_json.get("errorcode", "SIN_CODIGO")
                registrador.error(
                    f"Error API Moodle para '{nombre_funcion_ws}': {codigo_error_moodle} - {mensaje_error_moodle}"
                )
                raise ErrorAPIMoodle(mensaje=mensaje_error_moodle, datos_respuesta=datos_json)

            registrador.debug(f"Respuesta exitosa de '{nombre_funcion_ws}'.")
            return datos_json

        except requests.exceptions.HTTPError as error_http:
            texto_respuesta_error = error_http.response.text if error_http.response is not None else "Sin texto de respuesta."
            codigo_estado_error = error_http.response.status_code if error_http.response is not None else None
            registrador.error(
                f"Error HTTP para '{nombre_funcion_ws}': {error_http}. Código: {codigo_estado_error}. Respuesta: {texto_respuesta_error}"
            )
            raise ErrorAPIMoodle(
                f"Error HTTP: {codigo_estado_error}", codigo_estado=codigo_estado_error, datos_respuesta=texto_respuesta_error
            ) from error_http
        except requests.exceptions.Timeout as error_timeout:
            registrador.error(f"Timeout durante la petición a '{nombre_funcion_ws}': {error_timeout}")
            raise ErrorAPIMoodle(f"Timeout al conectar con Moodle para '{nombre_funcion_ws}'") from error_timeout
        except requests.exceptions.RequestException as error_peticion:
            # Error más genérico de la librería requests (ej. problemas de red)
            registrador.error(f"Excepción de red/petición para '{nombre_funcion_ws}': {error_peticion}")
            raise ErrorAPIMoodle(f"Error de red o petición para '{nombre_funcion_ws}': {error_peticion}") from error_peticion
        except ValueError as error_json: # Error al decodificar JSON
            texto_respuesta_bruta = respuesta_http.text if respuesta_http is not None else "Sin respuesta HTTP."
            registrador.error(
                f"Error en decodificación JSON para '{nombre_funcion_ws}': {error_json}. Respuesta bruta: {texto_respuesta_bruta}"
            )
            raise ErrorAPIMoodle(
                f"Falló la decodificación de la respuesta JSON para '{nombre_funcion_ws}'",
                datos_respuesta=texto_respuesta_bruta,
            ) from error_json

    # --- Métodos de Obtención de Datos ---
    def obtener_cursos_de_usuario(self, id_usuario: int) -> List[modelos_api.CursoMoodle]:
        """Obtiene los cursos en los que un usuario específico está inscrito."""
        if not isinstance(id_usuario, int) or id_usuario <= 0:
            registrador.error(f"ID de usuario inválido proporcionado: {id_usuario}")
            raise ValueError("El ID de usuario debe ser un entero positivo.")

        registrador.info(f"Obteniendo cursos para el ID de usuario: {id_usuario}")
        try:
            datos_cursos_api = self._realizar_peticion_api(
                "core_enrol_get_users_courses", {"userid": id_usuario}
            )
            cursos = self._procesar_datos_cursos(datos_cursos_api)
            registrador.info(f"Se encontraron {len(cursos)} cursos para el usuario {id_usuario}.")
            return cursos
        except ErrorAPIMoodle as e:
            registrador.error(f"Falló la obtención de cursos para el usuario {id_usuario}: {e}")
            # Re-lanzar la excepción para que el llamador la maneje o para mantener la traza
            raise
        except Exception as e: # Captura errores inesperados no previstos
            registrador.exception(f"Error inesperado en obtener_cursos_de_usuario para {id_usuario}: {e}")
            raise ErrorAPIMoodle(f"Error inesperado obteniendo cursos del usuario {id_usuario}: {e}")

    def obtener_todos_los_cursos_disponibles(self) -> List[modelos_api.CursoMoodle]:
        """Recupera todos los cursos disponibles en la instancia de Moodle."""
        registrador.info("Obteniendo todos los cursos disponibles de Moodle.")
        try:
            datos_cursos_api = self._realizar_peticion_api("core_course_get_courses")
            cursos = self._procesar_datos_cursos(datos_cursos_api)
            registrador.info(f"Se encontraron {len(cursos)} cursos en total.")
            return cursos
        except ErrorAPIMoodle as e:
            registrador.error(f"Falló la obtención de todos los cursos: {e}")
            raise
        except Exception as e:
            registrador.exception(f"Error inesperado en obtener_todos_los_cursos_disponibles: {e}")
            raise ErrorAPIMoodle(f"Error inesperado obteniendo todos los cursos: {e}")

    def obtener_contenidos_de_curso(self, id_curso: int) -> List[Dict[str, Any]]:
        """
        Obtiene los contenidos de un curso (secciones y módulos).
        Devuelve la estructura cruda tal como la proporciona la API.
        """
        registrador.info(f"Obteniendo contenidos para el ID de curso: {id_curso}")
        try:
            contenidos = self._realizar_peticion_api("core_course_get_contents", {"courseid": id_curso})
            if not isinstance(contenidos, list):
                registrador.warning(f"Respuesta inesperada para contenidos del curso {id_curso}, se esperaba lista pero fue {type(contenidos)}.")
                # Dependiendo de la política de errores, podría devolverse [] o lanzar excepción.
                # Por ahora, se devuelve tal cual para que el llamador decida.
            return contenidos
        except ErrorAPIMoodle as e:
            registrador.error(f"Falló la obtención de contenidos para el curso {id_curso}: {e}")
            raise

    def obtener_seccion_por_nombre(self, id_curso: int, nombre_seccion_buscada: str) -> Optional[modelos_api.SeccionMoodle]:
        """Recupera una sección específica por su nombre dentro de un curso."""
        registrador.info(f"Buscando sección con nombre '{nombre_seccion_buscada}' en el curso ID: {id_curso}")
        try:
            contenidos_del_curso = self.obtener_contenidos_de_curso(id_curso)
            if not isinstance(contenidos_del_curso, list):
                registrador.error(f"Se esperaba una lista de secciones para el curso {id_curso}, pero se obtuvo: {type(contenidos_del_curso)}")
                return None

            for datos_seccion_api in contenidos_del_curso:
                if not isinstance(datos_seccion_api, dict):
                    registrador.warning(f"Elemento de sección inesperado (no es dict): {datos_seccion_api}")
                    continue
                if datos_seccion_api.get("name") == nombre_seccion_buscada:
                    registrador.info(f"Sección '{nombre_seccion_buscada}' encontrada con ID: {datos_seccion_api.get('id')}")
                    return modelos_api.SeccionMoodle(**datos_seccion_api)

            registrador.info(f"Sección '{nombre_seccion_buscada}' no fue encontrada en el curso {id_curso}.")
            return None
        except ErrorAPIMoodle as e:
            # Error ya logueado en _realizar_peticion_api o obtener_contenidos_de_curso
            registrador.warning(f"Error API Moodle al buscar sección '{nombre_seccion_buscada}' en curso {id_curso}: {e}")
            return None
        except Exception as e:
            registrador.exception(f"Error inesperado al buscar sección '{nombre_seccion_buscada}' en curso {id_curso}: {e}")
            return None # O podría relanzarse como ErrorAPIMoodle

    def obtener_modulo_de_curso_por_nombre(
        self, id_curso: int, id_seccion: int, nombre_modulo_buscado: str, tipo_modulo_deseado: Optional[str] = None
    ) -> Optional[modelos_api.ModuloMoodle]:
        """Encuentra un módulo específico por su nombre dentro de una sección de un curso."""
        mensaje_busqueda = (
            f"Buscando módulo '{nombre_modulo_buscado}' "
            f"(tipo: {tipo_modulo_deseado or 'cualquiera'}) "
            f"en curso ID: {id_curso}, sección ID: {id_seccion}"
        )
        registrador.info(mensaje_busqueda)
        try:
            contenidos_del_curso = self.obtener_contenidos_de_curso(id_curso)
            if not isinstance(contenidos_del_curso, list):
                registrador.error(f"Se esperaba una lista de contenidos para el curso {id_curso}, se obtuvo {type(contenidos_del_curso)}")
                return None

            for datos_seccion_api in contenidos_del_curso:
                if not isinstance(datos_seccion_api, dict):
                    registrador.warning(f"Elemento de sección inesperado (no es dict): {datos_seccion_api}")
                    continue
                if datos_seccion_api.get("id") == id_seccion:
                    modulos_en_seccion = datos_seccion_api.get("modules", [])
                    if not isinstance(modulos_en_seccion, list):
                        registrador.warning(f"Los módulos en la sección {id_seccion} no son una lista: {modulos_en_seccion}")
                        return None
                    for datos_modulo_api in modulos_en_seccion:
                        if not isinstance(datos_modulo_api, dict):
                            registrador.warning(f"Elemento de módulo inesperado (no es dict): {datos_modulo_api}")
                            continue

                        nombre_coincide = datos_modulo_api.get("name") == nombre_modulo_buscado
                        tipo_coincide = (
                            tipo_modulo_deseado is None
                            or datos_modulo_api.get("modname") == tipo_modulo_deseado
                        )
                        if nombre_coincide and tipo_coincide:
                            registrador.info(f"Módulo '{nombre_modulo_buscado}' encontrado con ID: {datos_modulo_api.get('id')}")
                            return modelos_api.ModuloMoodle(**datos_modulo_api)
                    registrador.info(f"Módulo '{nombre_modulo_buscado}' no encontrado en la sección {id_seccion}.")
                    return None # Módulo no encontrado en esta sección

            registrador.info(f"Sección con ID {id_seccion} no encontrada en el curso {id_curso}.")
            return None # Sección no encontrada
        except ErrorAPIMoodle as e:
            registrador.warning(f"Error API Moodle al buscar módulo '{nombre_modulo_buscado}': {e}")
            return None
        except Exception as e:
            registrador.exception(f"Error inesperado al buscar módulo '{nombre_modulo_buscado}': {e}")
            return None

    def _parsear_contenidos_de_carpeta(self, datos_modulo_carpeta: dict, id_cm_carpeta: int) -> List[modelos_api.ArchivoMoodle]:
        """Parsea los contenidos de un módulo de tipo 'carpeta' para extraer información de archivos."""
        archivos_extraidos = []
        contenidos_carpeta = datos_modulo_carpeta.get("contents", [])
        if not isinstance(contenidos_carpeta, list):
            registrador.warning(f"Contenidos de carpeta {id_cm_carpeta} no son una lista: {contenidos_carpeta}")
            return []

        for item_contenido in contenidos_carpeta:
            if not isinstance(item_contenido, dict):
                registrador.warning(f"Item de contenido en carpeta {id_cm_carpeta} no es un dict: {item_contenido}")
                continue

            campos_requeridos = ("type", "filename", "filepath", "filesize", "fileurl", "timemodified")
            if item_contenido.get("type") == "file" and all(k in item_contenido for k in campos_requeridos):
                try:
                    archivos_extraidos.append(modelos_api.ArchivoMoodle(**item_contenido))
                    registrador.debug(f"Archivo '{item_contenido.get('filename')}' encontrado en carpeta ID: {id_cm_carpeta}")
                except Exception as e: # Error de validación Pydantic u otro
                    registrador.error(f"Error al procesar archivo en carpeta ({item_contenido.get('filename', 'Nombre desconocido')}): {e}")
            else:
                registrador.debug(f"Omitiendo item no archivo o con campos faltantes en carpeta {id_cm_carpeta}: {item_contenido.get('filename', 'Sin nombre')}")

        registrador.info(f"Se encontraron {len(archivos_extraidos)} archivos en la carpeta con ID de módulo de curso (cmid): {id_cm_carpeta}")
        return archivos_extraidos

    def _extraer_archivos_de_modulo_carpeta(self, id_curso: int, id_cm_carpeta: int) -> List[modelos_api.ArchivoMoodle]:
        """
        Método ayudante para obtener los archivos de un módulo de carpeta específico,
        buscándolo dentro de la estructura de contenidos del curso.
        """
        try:
            contenidos_del_curso = self.obtener_contenidos_de_curso(id_curso)
            if not isinstance(contenidos_del_curso, list):
                registrador.error(f"Contenidos del curso {id_curso} no son una lista, no se pueden buscar archivos de carpeta.")
                return []

            for seccion_api in contenidos_del_curso:
                if not isinstance(seccion_api, dict) or "modules" not in seccion_api or not isinstance(seccion_api["modules"], list):
                    continue # Saltar sección malformada
                for modulo_api in seccion_api["modules"]:
                    if isinstance(modulo_api, dict) and modulo_api.get("id") == id_cm_carpeta:
                        # Encontramos el módulo de carpeta, ahora parseamos sus contenidos
                        if modulo_api.get("modname") != "folder":
                             registrador.warning(f"Módulo {id_cm_carpeta} encontrado pero no es tipo 'folder', es '{modulo_api.get('modname')}'")
                             return []
                        return self._parsear_contenidos_de_carpeta(modulo_api, id_cm_carpeta)

            registrador.warning(f"Módulo de carpeta con ID {id_cm_carpeta} no encontrado en el curso {id_curso}.")
            return []
        except Exception as e: # Captura errores de obtener_contenidos_de_curso o procesamiento
            registrador.exception(f"Error extrayendo archivos de la carpeta ID {id_cm_carpeta} en curso {id_curso}: {e}")
            return []

    def obtener_archivos_de_carpeta(self, id_modulo_curso_carpeta: int) -> List[modelos_api.ArchivoMoodle]:
        """
        Recupera la lista de archivos contenidos en un módulo de Moodle de tipo 'carpeta'.
        Utiliza el ID del módulo de curso (cmid) de la carpeta.
        """
        registrador.info(f"Obteniendo archivos para el módulo de carpeta con ID de módulo de curso (cmid): {id_modulo_curso_carpeta}")
        try:
            # Primero, obtenemos detalles del módulo para verificar que es una carpeta y obtener el ID del curso.
            # El WS `core_course_get_course_module` devuelve información sobre un módulo específico (cm).
            datos_modulo_ws = self._realizar_peticion_api("core_course_get_course_module", {"cmid": id_modulo_curso_carpeta})

            if not datos_modulo_ws or "cm" not in datos_modulo_ws or not isinstance(datos_modulo_ws["cm"], dict):
                registrador.error(f"No se pudieron obtener detalles válidos para el módulo con cmid {id_modulo_curso_carpeta}.")
                return []

            info_cm = datos_modulo_ws["cm"] # Información del Course Module
            registrador.debug(f"Detalles del módulo cmid {id_modulo_curso_carpeta}: {info_cm}")

            if info_cm.get("modname") != "folder":
                registrador.error(f"El módulo con cmid {id_modulo_curso_carpeta} no es de tipo 'folder', sino '{info_cm.get('modname')}'")
                return []

            id_curso_asociado = info_cm.get("course")
            if not id_curso_asociado: # Debería estar siempre presente
                registrador.error(f"No se pudo determinar el ID del curso para el módulo cmid {id_modulo_curso_carpeta}.")
                return []

            # Ahora que tenemos el id_curso y sabemos que es una carpeta, usamos el método ayudante
            return self._extraer_archivos_de_modulo_carpeta(id_curso_asociado, id_modulo_curso_carpeta)
        except ErrorAPIMoodle as e:
            registrador.error(f"Error API Moodle obteniendo archivos para carpeta cmid {id_modulo_curso_carpeta}: {e}")
            return [] # Devolver lista vacía en caso de error API específico
        except Exception as e: # Otros errores inesperados
            registrador.exception(f"Error inesperado obteniendo archivos para carpeta cmid {id_modulo_curso_carpeta}: {e}")
            return []

    def obtener_configuracion_n8n_del_curso(self, id_curso: int) -> Optional[Dict[str, Any]]:
        """
        Obtiene las configuraciones de N8N específicas de un curso desde Moodle,
        utilizando un plugin local de Moodle 'local_entrenai_get_course_n8n_settings'.
        """
        registrador.info(f"Obteniendo configuración N8N para el curso ID: {id_curso}")
        try:
            # Este WS es ficticio y necesitaría existir en la instalación de Moodle.
            datos_respuesta_api = self._realizar_peticion_api("local_entrenai_get_course_n8n_settings", {"courseid": id_curso})

            if not datos_respuesta_api or not isinstance(datos_respuesta_api, dict):
                registrador.warning(f"Configuraciones N8N no disponibles o respuesta inválida para curso {id_curso}. Respuesta: {datos_respuesta_api}")
                return None

            # Filtrar y devolver solo los campos esperados y no nulos
            configuraciones_n8n = {}
            campos_esperados = ["initial_message", "system_message_append", "chat_title", "input_placeholder"]
            for campo in campos_esperados:
                if campo in datos_respuesta_api and datos_respuesta_api[campo] is not None:
                    configuraciones_n8n[campo] = datos_respuesta_api[campo]

            if configuraciones_n8n:
                registrador.info(f"Configuraciones N8N obtenidas para curso {id_curso}: {list(configuraciones_n8n.keys())}")
                return configuraciones_n8n
            else:
                registrador.info(f"No se encontraron configuraciones N8N específicas para el curso {id_curso}.")
                return None
        except ErrorAPIMoodle as e:
            # Si el WS no existe, esto podría ser un error 'ಕೋಡ್ ದೋಷ' (invalidfunction)
            if "invalidfunction" in str(e.datos_respuesta).lower() or "ಕೋಡ್ ದೋಷ" in str(e.datos_respuesta): # Heurística
                 registrador.warning(f"El Web Service 'local_entrenai_get_course_n8n_settings' podría no estar disponible en Moodle. Curso {id_curso}.")
            else:
                registrador.warning(f"Error API Moodle obteniendo configuraciones N8N para curso {id_curso}: {e}")
            return None
        except Exception as e:
            registrador.exception(f"Error inesperado obteniendo configuraciones N8N para curso {id_curso}: {e}")
            return None

    # --- Métodos de Creación/Modificación ---
    def asegurar_seccion_curso(self, id_curso: int, nombre_seccion: str) -> Optional[modelos_api.SeccionMoodle]:
        """
        Asegura la existencia de una sección en un curso.
        Si no existe, la crea. Devuelve el objeto SeccionMoodle.
        Requiere Web Services locales en Moodle: 'local_wsmanagesections_create_sections' y 'local_wsmanagesections_update_sections'.
        """
        registrador.info(f"Asegurando existencia de sección '{nombre_seccion}' en curso ID: {id_curso}")

        seccion_existente = self.obtener_seccion_por_nombre(id_curso, nombre_seccion)
        if seccion_existente:
            registrador.info(f"Sección '{nombre_seccion}' ya existe con ID {seccion_existente.id}. No se creará una nueva.")
            return seccion_existente

        registrador.info(f"Sección '{nombre_seccion}' no encontrada. Intentando crear...")
        try:
            # Paso 1: Crear una nueva sección. Moodle podría asignarle un nombre por defecto.
            # El WS 'local_wsmanagesections_create_sections' espera una lista de secciones a crear.
            # Aquí creamos una sola sección, sin especificar nombre aún si el WS no lo permite al crear.
            payload_creacion = {"courseid": id_curso, "sections": [{}]}
            respuesta_creacion = self._realizar_peticion_api("local_wsmanagesections_create_sections", payload_creacion)

            if not respuesta_creacion or not isinstance(respuesta_creacion, list) or not respuesta_creacion[0].get("id"):
                 registrador.error(f"No se pudo crear la sección o obtener su ID. Respuesta: {respuesta_creacion}")
                 raise ErrorAPIMoodle("Falló la creación de la estructura de la sección.", datos_respuesta=respuesta_creacion)
            id_nueva_seccion = respuesta_creacion[0]["id"]
            registrador.info(f"Sección base creada con ID {id_nueva_seccion}.")

            # Paso 2: Actualizar la sección recién creada con el nombre y sumario deseados.
            payload_actualizacion = {
                "courseid": id_curso,
                "sections": [{
                    "id": id_nueva_seccion,
                    "name": nombre_seccion,
                    "summary": f"Contenidos para {nombre_seccion}", # Sumario por defecto
                    "summaryformat": 1 # Formato HTML
                }]
            }
            self._realizar_peticion_api("local_wsmanagesections_update_sections", payload_actualizacion)
            registrador.info(f"Sección ID {id_nueva_seccion} actualizada con nombre '{nombre_seccion}'.")

            # Paso 3: Obtener la sección completamente actualizada para devolverla.
            # Esto también verifica que la actualización fue exitosa.
            seccion_final = self.obtener_seccion_por_nombre(id_curso, nombre_seccion)
            if not seccion_final:
                 registrador.error(f"No se pudo obtener la sección '{nombre_seccion}' después de intentar crearla y actualizarla.")
                 # Esto indicaría un problema, ya que debería existir.
            return seccion_final

        except ErrorAPIMoodle as e:
            registrador.error(f"Error API Moodle creando/actualizando la sección '{nombre_seccion}': {e}")
            return None
        except Exception as e:
            registrador.exception(f"Error inesperado al crear/actualizar la sección '{nombre_seccion}': {e}")
            return None

    def crear_o_actualizar_modulo_en_seccion(
        self, id_curso: int, id_seccion: int, nombre_modulo: str, tipo_modulo: str,
        parametros_especificos_modulo: Optional[Dict[str, Any]] = None,
        opciones_comunes_modulo: Optional[List[Dict[str, Any]]] = None
    ) -> Optional[modelos_api.ModuloMoodle]:
        """
        Crea un nuevo módulo en una sección específica de un curso o actualiza uno existente si se encuentra
        con el mismo nombre y tipo.
        Requiere el Web Service local 'local_wsmanagesections_update_sections'.
        """
        # NOTA: La lógica original no actualizaba un módulo existente, solo lo devolvía si se encontraba.
        # Esta implementación mantiene ese comportamiento para 'crear_modulo_en_seccion'.
        # Para una verdadera "crear o actualizar", se necesitaría más lógica para comparar `parametros_especificos_modulo`
        # y decidir si se requiere una actualización, y un WS que permita actualizar módulos existentes.
        # El WS 'local_wsmanagesections_update_sections' parece añadir módulos si no existen por ID,
        # pero no está claro si actualiza uno existente basado en nombre y tipo.
        # Por ahora, se enfoca en la creación.

        modulo_existente = self.obtener_modulo_de_curso_por_nombre(id_curso, id_seccion, nombre_modulo, tipo_modulo)
        if modulo_existente:
            registrador.info(f"Módulo '{nombre_modulo}' (tipo: {tipo_modulo}) ya existe en sección {id_seccion} con ID {modulo_existente.id}. No se creará uno nuevo.")
            return modulo_existente

        registrador.info(f"Creando módulo '{nombre_modulo}' (tipo: {tipo_modulo}) en curso ID: {id_curso}, sección ID: {id_seccion}")
        try:
            # Preparar datos del módulo para la API
            datos_api_modulo = {
                "modname": tipo_modulo,
                "name": nombre_modulo,
            }
            if parametros_especificos_modulo:
                datos_api_modulo.update(parametros_especificos_modulo)

            if opciones_comunes_modulo:
                 for opcion in opciones_comunes_modulo: # Ej: {"name": "visible", "value": 1}
                    if "name" in opcion and "value" in opcion:
                        datos_api_modulo[opcion["name"]] = opcion["value"]
                    else:
                        registrador.warning(f"Opción común de módulo malformada: {opcion}")

            # El WS 'local_wsmanagesections_update_sections' se usa para añadir módulos.
            # Espera el 'id' de la sección y una lista de módulos a añadir/modificar.
            payload_api = {
                "courseid": id_curso,
                "sections": [{
                    "id": id_seccion,
                    "modules": [datos_api_modulo] # Lista con un solo módulo a crear
                }]
            }

            self._realizar_peticion_api("local_wsmanagesections_update_sections", payload_api)
            registrador.info(f"Petición para crear módulo '{nombre_modulo}' (tipo: {tipo_modulo}) en sección {id_seccion} enviada.")

            # Después de crear, volvemos a obtener el módulo para confirmar y obtener su ID y detalles completos.
            modulo_creado = self.obtener_modulo_de_curso_por_nombre(id_curso, id_seccion, nombre_modulo, tipo_modulo)
            if modulo_creado:
                registrador.info(f"Módulo '{nombre_modulo}' creado/confirmado con ID {modulo_creado.id}.")
            else:
                registrador.warning(f"Módulo '{nombre_modulo}' no encontrado después del intento de creación. Puede haber un retraso o error no capturado.")
            return modulo_creado

        except ErrorAPIMoodle as e:
            registrador.error(f"Error API Moodle al añadir módulo '{nombre_modulo}' (tipo: {tipo_modulo}): {e}")
            return None
        except Exception as e:
            registrador.exception(f"Error inesperado al añadir módulo '{nombre_modulo}' (tipo: {tipo_modulo}): {e}")
            return None

    def crear_carpeta_en_seccion(self, id_curso: int, id_seccion: int, nombre_carpeta: str, introduccion: str = "") -> Optional[modelos_api.ModuloMoodle]:
        """Crea un módulo de tipo 'carpeta' en una sección específica."""
        registrador.info(f"Asegurando carpeta '{nombre_carpeta}' en curso ID: {id_curso}, sección ID: {id_seccion}")
        parametros_carpeta = {
            "intro": introduccion or f"Carpeta para {nombre_carpeta}", # Descripción de la carpeta
            "introformat": 1, # Formato HTML para la introducción
            "display": 0, # 0 para mostrar en página de curso, 1 para mostrar en página separada
            "showexpanded": 1, # 1 para mostrar expandida por defecto
        }
        opciones_comunes = [{"name": "visible", "value": 1}] # Hacer visible por defecto
        return self.crear_o_actualizar_modulo_en_seccion(id_curso, id_seccion, nombre_carpeta, "folder", parametros_carpeta, opciones_comunes)

    def crear_url_en_seccion(
        self, id_curso: int, id_seccion: int, nombre_recurso_url: str, url_externa: str,
        descripcion: str = "", modo_visualizacion: int = 0 # 0 = Automático, 1 = Embebido, 2 = Abrir, 3 = En ventana emergente
    ) -> Optional[modelos_api.ModuloMoodle]:
        """Crea un módulo de tipo 'URL' (enlace web) en una sección específica."""
        registrador.info(f"Asegurando URL '{nombre_recurso_url}' -> '{url_externa}' en curso ID: {id_curso}, sección ID: {id_seccion}")
        parametros_url = {
            "externalurl": url_externa,
            "intro": descripcion or f"Enlace a {nombre_recurso_url}", # Descripción del recurso URL
            "introformat": 1, # Formato HTML
            "display": modo_visualizacion, # Cómo se muestra el URL
        }
        opciones_comunes = [{"name": "visible", "value": 1}] # Hacer visible por defecto
        return self.crear_o_actualizar_modulo_en_seccion(id_curso, id_seccion, nombre_recurso_url, "url", parametros_url, opciones_comunes)

    def actualizar_sumario_de_seccion(self, id_curso: int, id_seccion: int, nuevo_sumario: str, formato_sumario: int = 1) -> bool:
        """Actualiza el sumario (descripción) de una sección específica de un curso."""
        registrador.info(f"Actualizando sumario para la sección ID: {id_seccion} en el curso ID: {id_curso}")
        try:
            payload_api = {
                "courseid": id_curso,
                "sections": [{
                    "id": id_seccion,
                    "summary": nuevo_sumario,
                    "summaryformat": formato_sumario # 1 para HTML, 0 para Moodle Auto-Format, 2 para Plain text, 4 para Markdown
                }]
            }
            # Utiliza el mismo WS que para añadir módulos, pero aquí solo actualiza campos de la sección.
            self._realizar_peticion_api("local_wsmanagesections_update_sections", payload_api)
            registrador.info(f"Sumario de la sección {id_seccion} actualizado exitosamente.")
            return True
        except ErrorAPIMoodle as e:
            registrador.error(f"Error API Moodle al actualizar sumario de sección {id_seccion} en curso {id_curso}: {e}")
            return False
        except Exception as e:
            registrador.exception(f"Error inesperado al actualizar sumario de sección {id_seccion}: {e}")
            return False

    # --- Descarga de Archivos ---
    def descargar_archivo_moodle(self, url_archivo_moodle: str, directorio_destino_descarga: Path, nombre_final_archivo: str) -> Path:
        """
        Descarga un archivo desde una URL de Moodle a un directorio local especificado.
        Asegura que el token de Moodle se añade a la URL si es necesario.
        Maneja tanto archivos de texto como binarios.
        """
        if not self.config_moodle.token_api_moodle: # CAMBIADO: token -> token_api_moodle
            registrador.error("Token de Moodle no configurado. No se pueden descargar archivos.")
            raise ErrorAPIMoodle("Token de Moodle no configurado, necesario para la descarga de archivos.")

        # Asegurar que el directorio de descarga exista
        directorio_destino_descarga.mkdir(parents=True, exist_ok=True)
        ruta_archivo_local_completa = directorio_destino_descarga / nombre_final_archivo

        registrador.info(f"Iniciando descarga de archivo Moodle desde {url_archivo_moodle} a {ruta_archivo_local_completa}")

        try:
            url_descarga_efectiva = str(url_archivo_moodle) # Asegurar que es un string
            # Añadir token a la URL si no está ya presente
            if "token=" not in url_descarga_efectiva.lower() and "wstoken=" not in url_descarga_efectiva.lower():
                conector_url = "&" if "?" in url_descarga_efectiva else "?"
                url_descarga_efectiva += f"{conector_url}token={self.config_moodle.token_api_moodle}" # CAMBIADO: token -> token_api_moodle

            # Cabecera para evitar problemas con codificación de contenido por parte del servidor
            cabeceras_peticion = {"Accept-Encoding": "identity"}

            # Realizar la petición de descarga en streaming
            with self.sesion.get(url_descarga_efectiva, stream=True, headers=cabeceras_peticion, timeout=120) as respuesta_descarga: # Timeout más largo para descargas
                respuesta_descarga.raise_for_status() # Lanza HTTPError para respuestas 4xx/5xx

                # Determinar si es texto o binario basado en Content-Type
                tipo_contenido_respuesta = respuesta_descarga.headers.get("Content-Type", "").lower()
                es_texto = any(sub_tipo in tipo_contenido_respuesta for sub_tipo in ["text/", "/markdown", "/md", "/json", "/xml", "/html", "/xhtml", "/css", "/javascript", "/csv"])

                if es_texto:
                    # Decodificar como UTF-8, reemplazando errores
                    contenido_texto = respuesta_descarga.content.decode("utf-8", errors="replace")
                    with open(ruta_archivo_local_completa, "w", encoding="utf-8") as archivo_local:
                        archivo_local.write(contenido_texto)
                    registrador.debug(f"Archivo de texto '{nombre_final_archivo}' guardado con codificación UTF-8.")
                else: # Tratar como archivo binario
                    with open(ruta_archivo_local_completa, "wb") as archivo_local:
                        for chunk_datos in respuesta_descarga.iter_content(chunk_size=8192): # Escribir en chunks
                            if chunk_datos: # Filtrar keep-alive chunks vacíos
                                archivo_local.write(chunk_datos)
                    registrador.debug(f"Archivo binario '{nombre_final_archivo}' guardado.")

            registrador.info(f"Archivo '{nombre_final_archivo}' descargado exitosamente a {ruta_archivo_local_completa}.")
            return ruta_archivo_local_completa

        except requests.exceptions.HTTPError as e_http:
            registrador.error(f"Error HTTP descargando '{nombre_final_archivo}': {e_http} (URL: {url_archivo_moodle})")
            raise ErrorAPIMoodle(f"Falló la descarga del archivo '{nombre_final_archivo}' debido a un error HTTP: {e_http.response.status_code}",
                                 codigo_estado=e_http.response.status_code, datos_respuesta=e_http.response.text) from e_http
        except requests.exceptions.Timeout as e_timeout:
            registrador.error(f"Timeout descargando '{nombre_final_archivo}' desde {url_archivo_moodle}: {e_timeout}")
            raise ErrorAPIMoodle(f"Timeout durante la descarga del archivo '{nombre_final_archivo}'") from e_timeout
        except Exception as e_general: # Otros errores (ej. problemas de red, IO)
            registrador.exception(f"Error general descargando archivo '{nombre_final_archivo}' desde {url_archivo_moodle}: {e_general}")
            raise ErrorAPIMoodle(f"Error inesperado durante la descarga del archivo '{nombre_final_archivo}': {e_general}") from e_general
