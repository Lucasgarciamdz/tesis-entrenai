from pathlib import Path
from typing import List, Optional, Dict, Any
from urllib.parse import urljoin

import requests

from entrenai_refactor.api import modelos as modelos_api # Modelos Pydantic para la API
from entrenai_refactor.config.configuracion import configuracion_global
from entrenai_refactor.config.registrador import obtener_registrador

registrador = obtener_registrador(__name__)


class ErrorAPIMoodle(Exception):
    """Excepción personalizada para errores relacionados con la API de Moodle."""

    def __init__(
        self,
        mensaje: str,
        codigo_estado: Optional[int] = None,
        datos_respuesta: Optional[Any] = None,
        nombre_funcion_ws: Optional[str] = None, # Añadido para más contexto
    ):
        super().__init__(mensaje)
        self.codigo_estado = codigo_estado
        self.datos_respuesta = datos_respuesta
        self.nombre_funcion_ws = nombre_funcion_ws
        registrador.debug(f"Excepción ErrorAPIMoodle creada: '{mensaje}', WS: {nombre_funcion_ws}, Código: {codigo_estado}, Respuesta: {datos_respuesta}")

    def __str__(self):
        detalle_ws = f" (Función WS: {self.nombre_funcion_ws})" if self.nombre_funcion_ws else ""
        detalle_codigo = f", Código de Estado: {self.codigo_estado}" if self.codigo_estado is not None else ""
        # No incluir datos_respuesta directamente en str si es muy largo o complejo, solo en logs.
        return f"{super().__str__()}{detalle_ws}{detalle_codigo}"


class ClienteMoodle:
    """Cliente para interactuar con la API de Web Services de Moodle."""

    url_base_api: Optional[str] # URL completa al endpoint server.php de Moodle

    def __init__(self, sesion_http: Optional[requests.Session] = None): # Renombrado 'sesion' a 'sesion_http'
        """
        Inicializa el ClienteMoodle.

        Args:
            sesion_http: Opcional. Una instancia de requests.Session para reutilizar conexiones.
                         Si no se provee, se crea una nueva sesión.
        """
        self.config_moodle = configuracion_global.moodle # Acceso a la sub-configuración de Moodle
        if not self.config_moodle.url_moodle:
            registrador.error("URL de Moodle (MOODLE_URL) no configurada. ClienteMoodle no será funcional.")
            self.url_base_api = None
        else:
            # Asegurar que la URL base termine con una barra para unir correctamente con server.php
            url_instancia_moodle_limpia = self.config_moodle.url_moodle.rstrip("/") + "/"
            self.url_base_api = urljoin(url_instancia_moodle_limpia, "webservice/rest/server.php")

        self.sesion_http = sesion_http or requests.Session()
        if self.config_moodle.token_api_moodle:
            # Configurar parámetros por defecto para todas las peticiones de esta sesión
            self.sesion_http.params = { # type: ignore[attr-defined]
                "wstoken": self.config_moodle.token_api_moodle,
                "moodlewsrestformat": "json",
            }
        else:
            registrador.warning("Token de API de Moodle (MOODLE_TOKEN) no configurado. El cliente solo podrá acceder a funciones públicas.")

        if self.url_base_api:
            registrador.info(f"ClienteMoodle inicializado. URL base API Moodle: {self.url_base_api}")
        else:
            registrador.warning("ClienteMoodle inicializado sin una URL base API válida (MOODLE_URL no configurada).")

    @staticmethod
    def _procesar_datos_cursos_api(datos_cursos_api: Any) -> List[modelos_api.CursoMoodle]:
        """
        Procesa y valida la lista de datos de cursos recibida de la API de Moodle.
        Transforma los datos crudos en una lista de objetos `modelos_api.CursoMoodle`.
        """
        registrador.debug(f"Procesando datos de cursos recibidos de la API: {type(datos_cursos_api)}")
        cursos_procesados: List[modelos_api.CursoMoodle] = []

        lista_cursos_crudos = []
        if isinstance(datos_cursos_api, list):
            lista_cursos_crudos = datos_cursos_api
        elif isinstance(datos_cursos_api, dict) and "courses" in datos_cursos_api and isinstance(datos_cursos_api["courses"], list):
            # Algunas funciones WS (ej. core_course_get_courses) devuelven un dict con una clave 'courses'
            registrador.debug("Detectado formato de respuesta con clave 'courses'. Extrayendo lista de cursos.")
            lista_cursos_crudos = datos_cursos_api["courses"]
        else:
            mensaje_error = "Los datos de cursos no están en un formato esperado (ni lista directa, ni dict con clave 'courses')."
            registrador.error(f"{mensaje_error} Datos recibidos: {str(datos_cursos_api)[:200]}...") # Loguear solo una parte
            raise ErrorAPIMoodle(mensaje_error, datos_respuesta=datos_cursos_api) # No hay nombre_funcion_ws aquí

        for datos_curso_individual in lista_cursos_crudos:
            if not isinstance(datos_curso_individual, dict):
                registrador.warning(f"Elemento de curso inesperado (no es un diccionario): {datos_curso_individual}")
                continue
            try:
                # Validar y convertir usando el modelo Pydantic
                cursos_procesados.append(modelos_api.CursoMoodle(**datos_curso_individual))
            except Exception as e_validacion: # Captura error de validación de Pydantic u otros
                registrador.error(f"Error al procesar/validar datos de un curso individual (ID: {datos_curso_individual.get('id', 'desconocido')}): {e_validacion}")
        return cursos_procesados

    def _formatear_parametros_moodle(
        self, datos_entrada: Any, prefijo_actual: str = "", dict_salida_plano: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Transforma una estructura anidada de diccionarios/listas a un diccionario plano,
        formateando las claves como espera la API de Moodle (ej. 'courses[0][id]').
        Es un método recursivo.

        Args:
            datos_entrada: El diccionario o lista a aplanar.
            prefijo_actual: El prefijo acumulado para las claves (usado en llamadas recursivas).
            dict_salida_plano: El diccionario que acumula los resultados aplanados.

        Returns:
            Un diccionario con claves formateadas para la API de Moodle.
        """
        if dict_salida_plano is None:
            dict_salida_plano = {}

        if not isinstance(datos_entrada, (list, dict)):
            # Es un valor simple (string, int, bool), lo asignamos directamente con el prefijo actual.
            # Solo se asigna si el prefijo no está vacío, para evitar claves vacías si se llama con un valor simple.
            if prefijo_actual:
                 dict_salida_plano[prefijo_actual] = datos_entrada
            return dict_salida_plano

        if isinstance(datos_entrada, list):
            # Si es una lista, iteramos sobre sus elementos.
            for indice, valor_item_lista in enumerate(datos_entrada):
                nuevo_prefijo_lista = f"{prefijo_actual}[{indice}]"
                self._formatear_parametros_moodle(valor_item_lista, nuevo_prefijo_lista, dict_salida_plano)
        elif isinstance(datos_entrada, dict):
            # Si es un diccionario, iteramos sobre sus pares clave-valor.
            for clave_item_dict, valor_item_dict in datos_entrada.items():
                # Si el prefijo actual está vacío, el nuevo prefijo es solo la clave.
                # Si no, se concatena con el formato [clave].
                nuevo_prefijo_dict = f"{prefijo_actual}[{clave_item_dict}]" if prefijo_actual else clave_item_dict
                self._formatear_parametros_moodle(valor_item_dict, nuevo_prefijo_dict, dict_salida_plano)

        return dict_salida_plano

    def _realizar_peticion_api(
        self,
        nombre_funcion_ws: str,
        parametros_payload: Optional[Dict[str, Any]] = None,
        metodo_http: str = "POST", # Moodle WS usualmente usa POST, pero GET es posible
    ) -> Any:
        """
        Realiza una petición genérica a la API de Web Services de Moodle.
        Maneja la construcción de la URL, el formateo de parámetros y la gestión de errores.
        """
        if not self.url_base_api:
            registrador.error("URL base de Moodle no configurada. No se puede realizar la petición.")
            raise ErrorAPIMoodle("URL base de Moodle no configurada.", nombre_funcion_ws=nombre_funcion_ws)

        # Parámetros base para la URL que identifican la función del WS.
        # El token y el formato de respuesta ya están en self.sesion_http.params por defecto.
        params_url_funcion = {"wsfunction": nombre_funcion_ws}

        # Formatear el payload si existe (para POST va en 'data', para GET en 'params')
        payload_api_formateado = self._formatear_parametros_moodle(parametros_payload) if parametros_payload else {}

        respuesta_http: Optional[requests.Response] = None # Para asegurar que esté definida

        try:
            registrador.debug(
                f"Llamando a función API Moodle '{nombre_funcion_ws}' con método {metodo_http.upper()}. "
                f"URL base: {self.url_base_api}, Payload (antes de formatear para GET): {parametros_payload}"
            )
            if metodo_http.upper() == "POST":
                respuesta_http = self.sesion_http.post(
                    self.url_base_api,
                    params=params_url_funcion, # Solo wsfunction aquí
                    data=payload_api_formateado, # Payload formateado en el cuerpo
                    timeout=configuracion_global.moodle.get("timeout_peticiones_moodle", 30), # Timeout desde config o default
                )
            elif metodo_http.upper() == "GET":
                # Para GET, todos los parámetros (incluyendo los formateados del payload) van en la URL
                params_get_completos = {**params_url_funcion, **payload_api_formateado}
                respuesta_http = self.sesion_http.get(
                    self.url_base_api,
                    params=params_get_completos,
                    timeout=configuracion_global.moodle.get("timeout_peticiones_moodle", 30)
                )
            else:
                registrador.error(f"Método HTTP no soportado: {metodo_http} para la función '{nombre_funcion_ws}'")
                raise ErrorAPIMoodle(f"Método HTTP no soportado: {metodo_http}", nombre_funcion_ws=nombre_funcion_ws)

            respuesta_http.raise_for_status() # Lanza HTTPError para respuestas 4xx/5xx

            datos_json = respuesta_http.json()

            # Moodle puede devolver errores 200 OK pero con una estructura de excepción en el JSON
            if isinstance(datos_json, dict) and "exception" in datos_json:
                mensaje_error_moodle = datos_json.get("message", f"Error desconocido de Moodle en '{nombre_funcion_ws}'")
                codigo_error_moodle = datos_json.get("errorcode", "SIN_CODIGO_ERROR")
                registrador.error(
                    f"Error en respuesta de API Moodle (función '{nombre_funcion_ws}'): {codigo_error_moodle} - {mensaje_error_moodle}"
                )
                raise ErrorAPIMoodle(mensaje=mensaje_error_moodle, datos_respuesta=datos_json, nombre_funcion_ws=nombre_funcion_ws)

            registrador.debug(f"Respuesta exitosa de la función Moodle '{nombre_funcion_ws}'.")
            return datos_json

        except requests.exceptions.HTTPError as error_http:
            codigo_estado_error = error_http.response.status_code if error_http.response is not None else None
            texto_respuesta_error = error_http.response.text if error_http.response is not None else "Sin texto de respuesta."
            registrador.error(
                f"Error HTTP {codigo_estado_error} para '{nombre_funcion_ws}': {error_http}. Respuesta: {texto_respuesta_error[:200]}..."
            )
            raise ErrorAPIMoodle(
                f"Error HTTP: {codigo_estado_error}", codigo_estado=codigo_estado_error, datos_respuesta=texto_respuesta_error, nombre_funcion_ws=nombre_funcion_ws
            ) from error_http
        except requests.exceptions.Timeout as error_timeout:
            registrador.error(f"Timeout durante la petición a '{nombre_funcion_ws}': {error_timeout}")
            raise ErrorAPIMoodle(f"Timeout al conectar con Moodle para '{nombre_funcion_ws}'", nombre_funcion_ws=nombre_funcion_ws) from error_timeout
        except requests.exceptions.RequestException as error_peticion:
            registrador.error(f"Excepción de red/petición para '{nombre_funcion_ws}': {error_peticion}")
            raise ErrorAPIMoodle(f"Error de red o petición para '{nombre_funcion_ws}': {error_peticion}", nombre_funcion_ws=nombre_funcion_ws) from error_peticion
        except ValueError as error_json: # Error al decodificar JSON
            texto_respuesta_bruta = respuesta_http.text if respuesta_http is not None else "Sin respuesta HTTP."
            registrador.error(
                f"Error en decodificación JSON para '{nombre_funcion_ws}': {error_json}. Respuesta bruta: {texto_respuesta_bruta[:200]}..."
            )
            raise ErrorAPIMoodle(
                f"Falló la decodificación de la respuesta JSON para '{nombre_funcion_ws}'",
                datos_respuesta=texto_respuesta_bruta, nombre_funcion_ws=nombre_funcion_ws
            ) from error_json

    # --- Métodos de Obtención de Datos ---
    def obtener_cursos_de_usuario(self, id_usuario: int) -> List[modelos_api.CursoMoodle]:
        """Obtiene los cursos en los que un usuario específico está inscrito."""
        if not isinstance(id_usuario, int) or id_usuario <= 0:
            registrador.error(f"ID de usuario inválido proporcionado: {id_usuario}")
            raise ValueError("El ID de usuario debe ser un entero positivo.")

        nombre_funcion_ws = "core_enrol_get_users_courses"
        registrador.info(f"Obteniendo cursos para el ID de usuario: {id_usuario} (WS: {nombre_funcion_ws})")
        try:
            datos_cursos_api = self._realizar_peticion_api(nombre_funcion_ws, {"userid": id_usuario})
            cursos = self._procesar_datos_cursos_api(datos_cursos_api)
            registrador.info(f"Se encontraron {len(cursos)} cursos para el usuario {id_usuario}.")
            return cursos
        except ErrorAPIMoodle as e:
            # El error ya fue logueado en _realizar_peticion_api o _procesar_datos_cursos_api
            registrador.error(f"Falló la obtención de cursos para el usuario {id_usuario} (WS: {nombre_funcion_ws}): {e}")
            raise # Re-lanzar para que el llamador maneje
        except Exception as e_gen:
            registrador.exception(f"Error inesperado en obtener_cursos_de_usuario (usuario {id_usuario}, WS: {nombre_funcion_ws}): {e_gen}")
            raise ErrorAPIMoodle(f"Error inesperado obteniendo cursos del usuario {id_usuario}", nombre_funcion_ws=nombre_funcion_ws) from e_gen

    def obtener_todos_los_cursos_disponibles(self) -> List[modelos_api.CursoMoodle]:
        """Recupera todos los cursos disponibles en la instancia de Moodle."""
        nombre_funcion_ws = "core_course_get_courses"
        registrador.info(f"Obteniendo todos los cursos disponibles de Moodle (WS: {nombre_funcion_ws}).")
        try:
            datos_cursos_api = self._realizar_peticion_api(nombre_funcion_ws) # No necesita parámetros adicionales
            cursos = self._procesar_datos_cursos_api(datos_cursos_api)
            registrador.info(f"Se encontraron {len(cursos)} cursos en total en la instancia de Moodle.")
            return cursos
        except ErrorAPIMoodle as e:
            registrador.error(f"Falló la obtención de todos los cursos (WS: {nombre_funcion_ws}): {e}")
            raise
        except Exception as e_gen:
            registrador.exception(f"Error inesperado en obtener_todos_los_cursos_disponibles (WS: {nombre_funcion_ws}): {e_gen}")
            raise ErrorAPIMoodle("Error inesperado obteniendo todos los cursos", nombre_funcion_ws=nombre_funcion_ws) from e_gen

    def obtener_contenidos_de_curso(self, id_curso: int) -> List[Dict[str, Any]]:
        """
        Obtiene los contenidos de un curso (secciones y módulos).
        Devuelve la estructura cruda tal como la proporciona la API, que es una lista de secciones.
        """
        nombre_funcion_ws = "core_course_get_contents"
        registrador.info(f"Obteniendo contenidos para el curso ID: {id_curso} (WS: {nombre_funcion_ws})")
        try:
            contenidos_curso_api = self._realizar_peticion_api(nombre_funcion_ws, {"courseid": id_curso})
            if not isinstance(contenidos_curso_api, list):
                registrador.warning(f"Respuesta inesperada para contenidos del curso {id_curso} (WS: {nombre_funcion_ws}), se esperaba lista pero fue {type(contenidos_curso_api)}.")
                # Dependiendo de la política de errores, podría devolverse [] o lanzar ErrorAPIMoodle.
                # Por ahora, se devuelve para que el llamador decida, pero podría ser más estricto.
            return contenidos_curso_api # Devuelve la lista de secciones cruda
        except ErrorAPIMoodle as e:
            registrador.error(f"Falló la obtención de contenidos para el curso {id_curso} (WS: {nombre_funcion_ws}): {e}")
            raise
        except Exception as e_gen:
            registrador.exception(f"Error inesperado en obtener_contenidos_de_curso (curso {id_curso}, WS: {nombre_funcion_ws}): {e_gen}")
            raise ErrorAPIMoodle(f"Error inesperado obteniendo contenidos del curso {id_curso}", nombre_funcion_ws=nombre_funcion_ws) from e_gen


    def obtener_seccion_por_nombre(self, id_curso: int, nombre_seccion_buscada: str) -> Optional[modelos_api.SeccionMoodle]:
        """Recupera una sección específica por su nombre dentro de un curso."""
        registrador.info(f"Buscando sección con nombre '{nombre_seccion_buscada}' en el curso ID: {id_curso}")
        try:
            contenidos_del_curso = self.obtener_contenidos_de_curso(id_curso) # Lista de dicts de secciones
            if not isinstance(contenidos_del_curso, list):
                registrador.error(f"Se esperaba una lista de secciones para el curso {id_curso}, pero se obtuvo: {type(contenidos_del_curso)}. No se puede buscar la sección.")
                return None

            for datos_seccion_api in contenidos_del_curso:
                if not isinstance(datos_seccion_api, dict):
                    registrador.warning(f"Elemento de sección en contenidos del curso {id_curso} no es un diccionario: {datos_seccion_api}")
                    continue
                if datos_seccion_api.get("name") == nombre_seccion_buscada:
                    registrador.info(f"Sección '{nombre_seccion_buscada}' encontrada con ID: {datos_seccion_api.get('id')} en curso {id_curso}.")
                    return modelos_api.SeccionMoodle(**datos_seccion_api) # Validar y convertir

            registrador.info(f"Sección '{nombre_seccion_buscada}' no fue encontrada en el curso {id_curso}.")
            return None
        except ErrorAPIMoodle as e_api: # Error ya logueado en obtener_contenidos_de_curso
            registrador.warning(f"Error API Moodle al buscar sección '{nombre_seccion_buscada}' en curso {id_curso}: {e_api}")
            return None
        except Exception as e_gen: # Errores de validación Pydantic u otros
            registrador.exception(f"Error inesperado al buscar o procesar sección '{nombre_seccion_buscada}' en curso {id_curso}: {e_gen}")
            return None

    def obtener_modulo_de_curso_por_nombre(
        self, id_curso: int, id_seccion: int, nombre_modulo_buscado: str, tipo_modulo_deseado: Optional[str] = None
    ) -> Optional[modelos_api.ModuloMoodle]:
        """Encuentra un módulo específico por su nombre dentro de una sección de un curso."""
        mensaje_busqueda_log = (
            f"Buscando módulo '{nombre_modulo_buscado}' "
            f"(tipo: {tipo_modulo_deseado or 'cualquiera'}) "
            f"en curso ID: {id_curso}, sección ID: {id_seccion}"
        )
        registrador.info(mensaje_busqueda_log)
        try:
            contenidos_del_curso = self.obtener_contenidos_de_curso(id_curso) # Lista de dicts de secciones
            if not isinstance(contenidos_del_curso, list):
                registrador.error(f"Se esperaba una lista de contenidos para el curso {id_curso}, se obtuvo {type(contenidos_del_curso)}. No se puede buscar el módulo.")
                return None

            for datos_seccion_api in contenidos_del_curso:
                if not isinstance(datos_seccion_api, dict):
                    registrador.warning(f"Elemento de sección en contenidos del curso {id_curso} no es un diccionario: {datos_seccion_api}")
                    continue
                if datos_seccion_api.get("id") == id_seccion:
                    modulos_en_seccion_api = datos_seccion_api.get("modules", [])
                    if not isinstance(modulos_en_seccion_api, list):
                        registrador.warning(f"Los módulos en la sección {id_seccion} (curso {id_curso}) no son una lista: {modulos_en_seccion_api}")
                        return None # Sección encontrada pero sin módulos válidos
                    for datos_modulo_api in modulos_en_seccion_api:
                        if not isinstance(datos_modulo_api, dict):
                            registrador.warning(f"Elemento de módulo en sección {id_seccion} no es un diccionario: {datos_modulo_api}")
                            continue

                        nombre_modulo_api = datos_modulo_api.get("name")
                        tipo_modulo_api = datos_modulo_api.get("modname") # ej. 'folder', 'url', 'resource'

                        nombre_coincide = nombre_modulo_api == nombre_modulo_buscado
                        tipo_coincide = tipo_modulo_deseado is None or tipo_modulo_api == tipo_modulo_deseado

                        if nombre_coincide and tipo_coincide:
                            registrador.info(f"Módulo '{nombre_modulo_buscado}' (tipo: {tipo_modulo_api}) encontrado con ID: {datos_modulo_api.get('id')} en sección {id_seccion}.")
                            return modelos_api.ModuloMoodle(**datos_modulo_api) # Validar y convertir
                    registrador.info(f"Módulo '{nombre_modulo_buscado}' (tipo: {tipo_modulo_deseado or 'cualquiera'}) no encontrado en la sección {id_seccion} del curso {id_curso}.")
                    return None # Módulo no encontrado en esta sección, terminar búsqueda

            registrador.info(f"Sección con ID {id_seccion} no encontrada en el curso {id_curso} al buscar el módulo '{nombre_modulo_buscado}'.")
            return None # Sección no encontrada
        except ErrorAPIMoodle as e_api:
            registrador.warning(f"Error API Moodle al buscar módulo '{nombre_modulo_buscado}': {e_api}")
            return None
        except Exception as e_gen: # Errores de validación Pydantic u otros
            registrador.exception(f"Error inesperado al buscar o procesar módulo '{nombre_modulo_buscado}': {e_gen}")
            return None

    def _parsear_contenidos_modulo_carpeta(self, datos_modulo_carpeta: Dict[str, Any], id_modulo_curso_carpeta: int) -> List[modelos_api.ArchivoMoodle]:
        """
        Parsea los contenidos de un módulo de tipo 'folder' (obtenidos de `core_course_get_contents`)
        para extraer información de los archivos que contiene.
        """
        archivos_extraidos: List[modelos_api.ArchivoMoodle] = []
        contenidos_api_carpeta = datos_modulo_carpeta.get("contents", []) # 'contents' es la clave esperada
        if not isinstance(contenidos_api_carpeta, list):
            registrador.warning(f"Contenidos del módulo carpeta ID {id_modulo_curso_carpeta} no son una lista: {contenidos_api_carpeta}")
            return []

        for item_contenido_api in contenidos_api_carpeta:
            if not isinstance(item_contenido_api, dict):
                registrador.warning(f"Item de contenido en carpeta ID {id_modulo_curso_carpeta} no es un diccionario: {item_contenido_api}")
                continue

            # Verificar que el tipo sea 'file' y que tenga los campos mínimos para ser un archivo útil
            campos_requeridos_archivo = ("type", "filename", "filepath", "filesize", "fileurl", "timemodified")
            if item_contenido_api.get("type") == "file" and all(k in item_contenido_api for k in campos_requeridos_archivo):
                try:
                    archivos_extraidos.append(modelos_api.ArchivoMoodle(**item_contenido_api))
                    registrador.debug(f"Archivo '{item_contenido_api.get('filename')}' encontrado en carpeta ID (cmid): {id_modulo_curso_carpeta}")
                except Exception as e_validacion: # Error de validación Pydantic u otro
                    registrador.error(f"Error al procesar/validar archivo en carpeta (nombre: {item_contenido_api.get('filename', 'desconocido')}): {e_validacion}")
            else:
                registrador.debug(f"Omitiendo ítem no archivo o con campos faltantes en carpeta ID {id_modulo_curso_carpeta}: nombre '{item_contenido_api.get('filename', 'Sin nombre')}', tipo '{item_contenido_api.get('type')}'")

        registrador.info(f"Se encontraron {len(archivos_extraidos)} archivos en el módulo carpeta con ID de módulo de curso (cmid): {id_modulo_curso_carpeta}")
        return archivos_extraidos

    def _extraer_archivos_de_modulo_carpeta_en_curso(self, id_curso: int, id_modulo_curso_carpeta: int) -> List[modelos_api.ArchivoMoodle]:
        """
        Método ayudante para obtener los archivos de un módulo de carpeta específico,
        buscándolo dentro de la estructura de contenidos del curso obtenida por `core_course_get_contents`.
        """
        try:
            contenidos_del_curso = self.obtener_contenidos_de_curso(id_curso) # Lista de dicts de secciones
            if not isinstance(contenidos_del_curso, list):
                registrador.error(f"Contenidos del curso {id_curso} no son una lista, no se pueden buscar archivos de carpeta.")
                return []

            for seccion_api in contenidos_del_curso:
                if not isinstance(seccion_api, dict) or "modules" not in seccion_api or not isinstance(seccion_api["modules"], list):
                    continue # Saltar sección malformada o sin módulos
                for modulo_api in seccion_api["modules"]:
                    if isinstance(modulo_api, dict) and modulo_api.get("id") == id_modulo_curso_carpeta:
                        # Encontramos el módulo de carpeta, ahora parseamos sus contenidos
                        if modulo_api.get("modname") != "folder":
                             registrador.warning(f"Módulo con ID de curso (cmid) {id_modulo_curso_carpeta} encontrado pero no es tipo 'folder', es '{modulo_api.get('modname')}'")
                             return [] # No es una carpeta
                        return self._parsear_contenidos_modulo_carpeta(modulo_api, id_modulo_curso_carpeta)

            registrador.warning(f"Módulo de carpeta con ID (cmid) {id_modulo_curso_carpeta} no encontrado en el curso {id_curso}.")
            return []
        except ErrorAPIMoodle as e_api: # Errores de obtener_contenidos_de_curso
            registrador.error(f"Error API Moodle extrayendo archivos de carpeta ID {id_modulo_curso_carpeta} en curso {id_curso}: {e_api}")
            return []
        except Exception as e_gen: # Otros errores (ej. procesamiento, validación)
            registrador.exception(f"Error inesperado extrayendo archivos de carpeta ID {id_modulo_curso_carpeta} en curso {id_curso}: {e_gen}")
            return []

    def obtener_archivos_de_carpeta(self, id_modulo_curso_carpeta: int) -> List[modelos_api.ArchivoMoodle]:
        """
        Recupera la lista de archivos contenidos en un módulo de Moodle de tipo 'carpeta'.
        Utiliza el ID del módulo de curso (cmid) de la carpeta.

        Este método primero obtiene el ID del curso al que pertenece el módulo de carpeta,
        y luego busca los archivos dentro de la estructura de contenidos de ese curso.
        """
        nombre_funcion_ws_detalle_modulo = "core_course_get_course_module"
        registrador.info(f"Obteniendo archivos para el módulo de carpeta con ID de módulo de curso (cmid): {id_modulo_curso_carpeta} (WS: {nombre_funcion_ws_detalle_modulo})")
        try:
            # Primero, obtenemos detalles del módulo para verificar que es una carpeta y obtener el ID del curso.
            datos_modulo_api = self._realizar_peticion_api(nombre_funcion_ws_detalle_modulo, {"cmid": id_modulo_curso_carpeta})

            if not datos_modulo_api or "cm" not in datos_modulo_api or not isinstance(datos_modulo_api["cm"], dict):
                registrador.error(f"No se pudieron obtener detalles válidos para el módulo con cmid {id_modulo_curso_carpeta} usando {nombre_funcion_ws_detalle_modulo}.")
                return []

            info_modulo_curso = datos_modulo_api["cm"] # Información del Course Module (cm)
            registrador.debug(f"Detalles del módulo cmid {id_modulo_curso_carpeta}: {info_modulo_curso}")

            if info_modulo_curso.get("modname") != "folder":
                registrador.error(f"El módulo con cmid {id_modulo_curso_carpeta} no es de tipo 'folder', sino '{info_modulo_curso.get('modname')}'")
                return []

            id_curso_asociado = info_modulo_curso.get("course")
            if not id_curso_asociado or not isinstance(id_curso_asociado, int):
                registrador.error(f"No se pudo determinar un ID de curso válido para el módulo cmid {id_modulo_curso_carpeta}. ID obtenido: {id_curso_asociado}")
                return []

            # Ahora que tenemos el id_curso y sabemos que es una carpeta, usamos el método ayudante que busca en `core_course_get_contents`
            return self._extraer_archivos_de_modulo_carpeta_en_curso(id_curso_asociado, id_modulo_curso_carpeta)
        except ErrorAPIMoodle as e_api:
            registrador.error(f"Error API Moodle obteniendo archivos para carpeta cmid {id_modulo_curso_carpeta}: {e_api}")
            return []
        except Exception as e_gen:
            registrador.exception(f"Error inesperado obteniendo archivos para carpeta cmid {id_modulo_curso_carpeta}: {e_gen}")
            return []

    def obtener_configuracion_n8n_de_curso(self, id_curso: int) -> Optional[Dict[str, Any]]:
        """
        Obtiene las configuraciones de N8N específicas de un curso desde Moodle,
        utilizando un plugin local de Moodle 'local_entrenai_get_course_n8n_settings' (nombre de ejemplo).
        """
        nombre_funcion_ws_config_n8n = "local_entrenai_get_course_n8n_settings" # Este WS debe existir en Moodle
        registrador.info(f"Obteniendo configuración N8N para el curso ID: {id_curso} (WS: {nombre_funcion_ws_config_n8n})")
        try:
            datos_respuesta_api = self._realizar_peticion_api(nombre_funcion_ws_config_n8n, {"courseid": id_curso})

            if not datos_respuesta_api or not isinstance(datos_respuesta_api, dict):
                registrador.warning(f"Configuraciones N8N no disponibles o respuesta inválida para curso {id_curso} (WS: {nombre_funcion_ws_config_n8n}). Respuesta: {datos_respuesta_api}")
                return None

            # Filtrar y devolver solo los campos esperados y no nulos/vacíos
            configuraciones_n8n_curso: Dict[str, Any] = {}
            campos_esperados_config_n8n = ["initial_message", "system_message_append", "chat_title", "input_placeholder"]
            for campo_config in campos_esperados_config_n8n:
                valor_campo = datos_respuesta_api.get(campo_config) # Usar .get() para evitar KeyError
                if valor_campo is not None and (not isinstance(valor_campo, str) or valor_campo.strip()): # No nulo y no string vacío
                    configuraciones_n8n_curso[campo_config] = valor_campo

            if configuraciones_n8n_curso:
                registrador.info(f"Configuraciones N8N obtenidas para curso {id_curso}: {list(configuraciones_n8n_curso.keys())}")
                return configuraciones_n8n_curso
            else:
                registrador.info(f"No se encontraron configuraciones N8N específicas (o todas estaban vacías) para el curso {id_curso} (WS: {nombre_funcion_ws_config_n8n}).")
                return None
        except ErrorAPIMoodle as e_api:
            # Si el WS no existe, Moodle puede devolver un error "invalidfunction" o similar.
            if "invalidfunction" in str(e_api.datos_respuesta).lower() or "ಕೋಡ್ ದೋಷ" in str(e_api.datos_respuesta).lower(): # Heurística para detectar error de WS no encontrado
                 registrador.warning(f"El Web Service '{nombre_funcion_ws_config_n8n}' podría no estar disponible en Moodle. No se pudo obtener config N8N para curso {id_curso}.")
            else: # Otro error de la API
                registrador.warning(f"Error API Moodle obteniendo configuraciones N8N para curso {id_curso} (WS: {nombre_funcion_ws_config_n8n}): {e_api}")
            return None
        except Exception as e_gen:
            registrador.exception(f"Error inesperado obteniendo configuraciones N8N para curso {id_curso} (WS: {nombre_funcion_ws_config_n8n}): {e_gen}")
            return None

    # --- Métodos de Creación/Modificación ---
    def asegurar_seccion_curso(self, id_curso: int, nombre_seccion: str) -> Optional[modelos_api.SeccionMoodle]:
        """
        Asegura la existencia de una sección en un curso. Si no existe, la crea.
        Devuelve el objeto `modelos_api.SeccionMoodle` de la sección.
        Requiere Web Services locales en Moodle: 'local_wsmanagesections_create_sections' y 'local_wsmanagesections_update_sections' (nombres de ejemplo).
        """
        registrador.info(f"Asegurando existencia de sección '{nombre_seccion}' en curso ID: {id_curso}")

        seccion_existente = self.obtener_seccion_por_nombre(id_curso, nombre_seccion)
        if seccion_existente:
            registrador.info(f"Sección '{nombre_seccion}' ya existe con ID {seccion_existente.id} en curso {id_curso}. No se creará una nueva.")
            return seccion_existente

        registrador.info(f"Sección '{nombre_seccion}' no encontrada en curso {id_curso}. Intentando crear...")
        nombre_ws_crear_seccion = "local_wsmanagesections_create_sections" # WS para crear la estructura de la sección
        nombre_ws_actualizar_seccion = "local_wsmanagesections_update_sections" # WS para nombrar/detallar la sección

        try:
            # Paso 1: Crear una nueva sección. Moodle podría asignarle un nombre por defecto o ninguno.
            # El WS 'local_wsmanagesections_create_sections' esperaría una lista de secciones a crear.
            payload_creacion = {"courseid": id_curso, "sections": [{}]} # Crear una sección vacía inicialmente
            respuesta_creacion_api = self._realizar_peticion_api(nombre_ws_crear_seccion, payload_creacion)

            # Validar respuesta de creación y obtener ID de la nueva sección
            if not respuesta_creacion_api or not isinstance(respuesta_creacion_api, list) or not respuesta_creacion_api[0].get("id"):
                 registrador.error(f"No se pudo crear la sección o obtener su ID. Respuesta de '{nombre_ws_crear_seccion}': {respuesta_creacion_api}")
                 raise ErrorAPIMoodle("Falló la creación de la estructura de la sección.", datos_respuesta=respuesta_creacion_api, nombre_funcion_ws=nombre_ws_crear_seccion)
            id_nueva_seccion = respuesta_creacion_api[0]["id"]
            registrador.info(f"Estructura de sección base creada con ID {id_nueva_seccion} en curso {id_curso} (WS: {nombre_ws_crear_seccion}).")

            # Paso 2: Actualizar la sección recién creada con el nombre y sumario deseados.
            payload_actualizacion = {
                "courseid": id_curso,
                "sections": [{
                    "id": id_nueva_seccion,
                    "name": nombre_seccion,
                    "summary": f"Contenidos y recursos para {nombre_seccion}.", # Sumario por defecto
                    "summaryformat": 1 # 1 = Formato HTML
                }]
            }
            self._realizar_peticion_api(nombre_ws_actualizar_seccion, payload_actualizacion)
            registrador.info(f"Sección ID {id_nueva_seccion} actualizada con nombre '{nombre_seccion}' (WS: {nombre_ws_actualizar_seccion}).")

            # Paso 3: Obtener la sección completamente actualizada para devolverla (y verificar).
            seccion_final_creada = self.obtener_seccion_por_nombre(id_curso, nombre_seccion)
            if not seccion_final_creada: # Si después de crear y actualizar no se encuentra, algo falló.
                 registrador.error(f"No se pudo obtener la sección '{nombre_seccion}' (ID esperado: {id_nueva_seccion}) después de intentar crearla y actualizarla en curso {id_curso}.")
                 # Esto podría indicar un problema con los WS o un retraso en Moodle.
            return seccion_final_creada

        except ErrorAPIMoodle as e_api:
            registrador.error(f"Error API Moodle durante la creación/actualización de la sección '{nombre_seccion}' en curso {id_curso}: {e_api}")
            return None # Devolver None si hay un error de API Moodle
        except Exception as e_gen: # Otros errores inesperados
            registrador.exception(f"Error inesperado al asegurar/crear la sección '{nombre_seccion}' en curso {id_curso}: {e_gen}")
            return None

    def crear_o_actualizar_modulo_en_seccion(
        self, id_curso: int, id_seccion: int, nombre_modulo: str, tipo_modulo: str, # ej. 'url', 'folder', 'resource'
        parametros_especificos_modulo: Optional[Dict[str, Any]] = None, # ej. {'externalurl': 'http://...'} para 'url'
        opciones_comunes_modulo: Optional[List[Dict[str, Any]]] = None # ej. [{'name': 'visible', 'value': 1}]
    ) -> Optional[modelos_api.ModuloMoodle]:
        """
        Crea un nuevo módulo en una sección específica de un curso. Si ya existe un módulo
        con el mismo nombre y tipo en esa sección, lo devuelve sin crear uno nuevo.
        Requiere el Web Service local 'local_wsmanagesections_update_sections' (nombre de ejemplo)
        que permita añadir módulos a una sección.
        """
        # Primero, verificar si el módulo ya existe para evitar duplicados.
        modulo_existente = self.obtener_modulo_de_curso_por_nombre(id_curso, id_seccion, nombre_modulo, tipo_modulo)
        if modulo_existente:
            registrador.info(f"Módulo '{nombre_modulo}' (tipo: {tipo_modulo}) ya existe en sección {id_seccion} (curso {id_curso}) con ID de módulo de curso (cmid) {modulo_existente.id}. No se creará uno nuevo.")
            return modulo_existente

        nombre_ws_actualizar_seccion_con_modulos = "local_wsmanagesections_update_sections"
        registrador.info(f"Creando módulo '{nombre_modulo}' (tipo: {tipo_modulo}) en curso ID: {id_curso}, sección ID: {id_seccion} (WS: {nombre_ws_actualizar_seccion_con_modulos})")
        try:
            # Preparar datos del módulo para la API
            datos_api_modulo_nuevo = {
                "modname": tipo_modulo,
                "name": nombre_modulo,
            }
            if parametros_especificos_modulo: # Añadir parámetros específicos del tipo de módulo
                datos_api_modulo_nuevo.update(parametros_especificos_modulo)

            if opciones_comunes_modulo: # Añadir opciones comunes (visibilidad, etc.)
                 for opcion_comun in opciones_comunes_modulo:
                    if "name" in opcion_comun and "value" in opcion_comun:
                        datos_api_modulo_nuevo[opcion_comun["name"]] = opcion_comun["value"]
                    else:
                        registrador.warning(f"Opción común de módulo malformada y omitida: {opcion_comun}")

            # El WS 'local_wsmanagesections_update_sections' se usa para añadir módulos a una sección existente.
            # Espera el 'id' de la sección y una lista de módulos a añadir/modificar.
            payload_api_actualizacion_seccion = {
                "courseid": id_curso,
                "sections": [{
                    "id": id_seccion,
                    "modules": [datos_api_modulo_nuevo] # Lista con un solo módulo a crear
                }]
            }

            self._realizar_peticion_api(nombre_ws_actualizar_seccion_con_modulos, payload_api_actualizacion_seccion)
            registrador.info(f"Petición para crear módulo '{nombre_modulo}' (tipo: {tipo_modulo}) en sección {id_seccion} enviada a {nombre_ws_actualizar_seccion_con_modulos}.")

            # Después de crear, volvemos a obtener el módulo para confirmar y obtener su ID de módulo de curso (cmid) y detalles completos.
            modulo_recien_creado = self.obtener_modulo_de_curso_por_nombre(id_curso, id_seccion, nombre_modulo, tipo_modulo)
            if modulo_recien_creado:
                registrador.info(f"Módulo '{nombre_modulo}' (tipo: {tipo_modulo}) creado/confirmado con ID de módulo de curso (cmid) {modulo_recien_creado.id} en sección {id_seccion}.")
            else:
                registrador.warning(f"Módulo '{nombre_modulo}' (tipo: {tipo_modulo}) no encontrado inmediatamente después del intento de creación en sección {id_seccion}. Puede haber un retraso o error no capturado.")
            return modulo_recien_creado

        except ErrorAPIMoodle as e_api:
            registrador.error(f"Error API Moodle al añadir módulo '{nombre_modulo}' (tipo: {tipo_modulo}) en sección {id_seccion}: {e_api}")
            return None
        except Exception as e_gen: # Otros errores inesperados
            registrador.exception(f"Error inesperado al añadir módulo '{nombre_modulo}' (tipo: {tipo_modulo}) en sección {id_seccion}: {e_gen}")
            return None

    def crear_carpeta_en_seccion(self, id_curso: int, id_seccion: int, nombre_carpeta: str, introduccion: str = "") -> Optional[modelos_api.ModuloMoodle]:
        """Crea un módulo de tipo 'carpeta' en una sección específica."""
        registrador.info(f"Creando o asegurando carpeta '{nombre_carpeta}' en curso ID: {id_curso}, sección ID: {id_seccion}")
        parametros_carpeta = {
            "intro": introduccion or f"Carpeta para recursos relacionados con {nombre_carpeta}.", # Descripción de la carpeta
            "introformat": 1, # 1 = Formato HTML para la introducción
            "display": 0, # 0 para mostrar en página de curso, 1 para mostrar en página separada
            "showexpanded": 1, # 1 para mostrar expandida por defecto, 0 para colapsada
        }
        opciones_comunes_visibilidad = [{"name": "visible", "value": 1}] # Hacer visible por defecto
        return self.crear_o_actualizar_modulo_en_seccion(id_curso, id_seccion, nombre_carpeta, "folder", parametros_carpeta, opciones_comunes_visibilidad)

    def crear_url_en_seccion(
        self, id_curso: int, id_seccion: int, nombre_recurso_url: str, url_externa: str,
        descripcion_recurso: str = "", modo_visualizacion_url: int = 0 # 0=Automático, 1=Embebido, 2=Abrir, 3=Popup
    ) -> Optional[modelos_api.ModuloMoodle]:
        """Crea un módulo de tipo 'URL' (enlace web) en una sección específica."""
        registrador.info(f"Creando o asegurando URL '{nombre_recurso_url}' -> '{url_externa}' en curso ID: {id_curso}, sección ID: {id_seccion}")
        parametros_url_especificos = {
            "externalurl": url_externa,
            "intro": descripcion_recurso or f"Enlace al recurso externo: {nombre_recurso_url}", # Descripción del recurso URL
            "introformat": 1, # 1 = Formato HTML
            "display": modo_visualizacion_url, # Cómo se muestra el URL (0=auto, 1=embed, 2=open, 3=popup, etc.)
        }
        opciones_comunes_visibilidad = [{"name": "visible", "value": 1}] # Hacer visible por defecto
        return self.crear_o_actualizar_modulo_en_seccion(
            id_curso, id_seccion, nombre_recurso_url, "url", parametros_url_especificos, opciones_comunes_visibilidad
        )

    def actualizar_sumario_de_seccion(self, id_curso: int, id_seccion: int, nuevo_sumario: str, formato_sumario: int = 1) -> bool:
        """
        Actualiza el sumario (descripción) de una sección específica de un curso.
        Requiere el Web Service local 'local_wsmanagesections_update_sections'.
        """
        nombre_ws_actualizar_seccion = "local_wsmanagesections_update_sections"
        registrador.info(f"Actualizando sumario para la sección ID: {id_seccion} en el curso ID: {id_curso} (WS: {nombre_ws_actualizar_seccion})")
        try:
            payload_api_actualizacion = {
                "courseid": id_curso,
                "sections": [{
                    "id": id_seccion,
                    "summary": nuevo_sumario,
                    "summaryformat": formato_sumario # 1=HTML, 0=Moodle Auto-Format, 2=Plain text, 4=Markdown
                }]
            }
            # Utiliza el mismo WS que para añadir módulos, pero aquí solo actualiza campos de la sección.
            self._realizar_peticion_api(nombre_ws_actualizar_seccion, payload_api_actualizacion)
            registrador.info(f"Sumario de la sección {id_seccion} (curso {id_curso}) actualizado exitosamente.")
            return True
        except ErrorAPIMoodle as e_api:
            registrador.error(f"Error API Moodle al actualizar sumario de sección {id_seccion} en curso {id_curso}: {e_api}")
            return False
        except Exception as e_gen:
            registrador.exception(f"Error inesperado al actualizar sumario de sección {id_seccion} (curso {id_curso}): {e_gen}")
            return False

    # --- Descarga de Archivos ---
    def descargar_archivo_moodle(self, url_archivo_moodle_original: str, directorio_destino_descarga: Path, nombre_final_archivo: str) -> Path:
        """
        Descarga un archivo desde una URL de Moodle a un directorio local especificado.
        Asegura que el token de Moodle se añade a la URL si es necesario.
        Maneja tanto archivos de texto como binarios.

        Args:
            url_archivo_moodle_original: URL del archivo en Moodle (puede o no tener token).
            directorio_destino_descarga: Directorio local donde se guardará el archivo.
            nombre_final_archivo: Nombre que tendrá el archivo guardado localmente.

        Returns:
            La ruta (Path) completa al archivo descargado localmente.

        Raises:
            ErrorAPIMoodle: Si falla la descarga o hay un error de configuración.
            IOError, OSError: Si hay problemas al escribir el archivo localmente.
        """
        if not self.config_moodle.token_api_moodle:
            registrador.error("Token de API de Moodle no configurado. No se pueden descargar archivos autenticados.")
            raise ErrorAPIMoodle("Token de API de Moodle no configurado, necesario para la descarga de archivos.")

        # Asegurar que el directorio de descarga exista
        directorio_destino_descarga.mkdir(parents=True, exist_ok=True)
        ruta_archivo_local_completa = directorio_destino_descarga / nombre_final_archivo

        registrador.info(f"Iniciando descarga de archivo Moodle desde '{url_archivo_moodle_original}' a '{ruta_archivo_local_completa}'")

        try:
            url_descarga_con_token = str(url_archivo_moodle_original) # Asegurar que es un string
            # Añadir token a la URL si no está ya presente (insensible a mayúsculas para 'token' y 'wstoken')
            if "token=" not in url_descarga_con_token.lower() and "wstoken=" not in url_descarga_con_token.lower():
                conector_url = "&" if "?" in url_descarga_con_token else "?"
                url_descarga_con_token += f"{conector_url}token={self.config_moodle.token_api_moodle}"
                registrador.debug("Token de Moodle añadido a la URL de descarga.")

            # Cabecera para evitar problemas con codificación de contenido por parte del servidor (ej. gzip)
            # y asegurar que se reciba el contenido tal cual.
            cabeceras_peticion_descarga = {"Accept-Encoding": "identity"}
            timeout_descarga = configuracion_global.moodle.get("timeout_descargas_moodle", 120) # Timeout más largo para descargas

            # Realizar la petición de descarga en streaming para manejar archivos grandes
            with self.sesion_http.get(url_descarga_con_token, stream=True, headers=cabeceras_peticion_descarga, timeout=timeout_descarga) as respuesta_descarga:
                respuesta_descarga.raise_for_status() # Lanza HTTPError para respuestas 4xx/5xx

                # Determinar si es texto o binario basado en Content-Type (heurística)
                tipo_contenido_respuesta = respuesta_descarga.headers.get("Content-Type", "").lower()
                # Lista extendida de tipos MIME que se considerarán texto
                subtipos_texto = ["text/", "/markdown", "/md", "/json", "/xml", "/html", "/xhtml", "/css", "/javascript", "/csv", "application/rtf", "application/x-subrip"]
                es_archivo_texto = any(sub_tipo_texto in tipo_contenido_respuesta for sub_tipo_texto in subtipos_texto)

                if es_archivo_texto:
                    # Decodificar como UTF-8, reemplazando errores para evitar fallos en contenido mixto.
                    contenido_texto_archivo = respuesta_descarga.content.decode("utf-8", errors="replace")
                    with open(ruta_archivo_local_completa, "w", encoding="utf-8") as archivo_local:
                        archivo_local.write(contenido_texto_archivo)
                    registrador.debug(f"Archivo de texto '{nombre_final_archivo}' (tipo: {tipo_contenido_respuesta}) guardado con codificación UTF-8.")
                else: # Tratar como archivo binario
                    with open(ruta_archivo_local_completa, "wb") as archivo_local:
                        for chunk_datos_binarios in respuesta_descarga.iter_content(chunk_size=8192): # Escribir en chunks
                            if chunk_datos_binarios: # Filtrar keep-alive chunks vacíos si los hubiera
                                archivo_local.write(chunk_datos_binarios)
                    registrador.debug(f"Archivo binario '{nombre_final_archivo}' (tipo: {tipo_contenido_respuesta}) guardado.")

            registrador.info(f"Archivo '{nombre_final_archivo}' descargado exitosamente a {ruta_archivo_local_completa}.")
            return ruta_archivo_local_completa

        except requests.exceptions.HTTPError as e_http:
            registrador.error(f"Error HTTP {e_http.response.status_code} descargando '{nombre_final_archivo}': {e_http} (URL original: {url_archivo_moodle_original})")
            raise ErrorAPIMoodle(f"Falló la descarga del archivo '{nombre_final_archivo}' debido a un error HTTP: {e_http.response.status_code}",
                                 codigo_estado=e_http.response.status_code, datos_respuesta=e_http.response.text) from e_http
        except requests.exceptions.Timeout as e_timeout:
            registrador.error(f"Timeout descargando '{nombre_final_archivo}' desde {url_archivo_moodle_original}: {e_timeout}")
            raise ErrorAPIMoodle(f"Timeout durante la descarga del archivo '{nombre_final_archivo}'") from e_timeout
        except IOError as e_io: # Errores al escribir el archivo local
            registrador.error(f"Error de E/S al guardar el archivo descargado '{nombre_final_archivo}' en '{ruta_archivo_local_completa}': {e_io}")
            raise # Re-lanzar IOError para que sea manejada por el llamador
        except Exception as e_general: # Otros errores (ej. problemas de red no HTTP, etc.)
            registrador.exception(f"Error general descargando archivo '{nombre_final_archivo}' desde {url_archivo_moodle_original}: {e_general}")
            raise ErrorAPIMoodle(f"Error inesperado durante la descarga del archivo '{nombre_final_archivo}': {e_general}") from e_general

[end of entrenai_refactor/nucleo/clientes/cliente_moodle.py]
