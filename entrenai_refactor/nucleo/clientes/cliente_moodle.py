from pathlib import Path
from typing import List, Optional, Dict, Any
from urllib.parse import urljoin

import requests

from entrenai_refactor.api import modelos as modelos_api # Para evitar conflicto de nombres si hay un modulo 'modelos' local
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

    def __str__(self):
        return f"{super().__str__()} (Código de Estado: {self.codigo_estado}, Respuesta: {self.datos_respuesta})"


class ClienteMoodle:
    """Cliente para interactuar con la API de Web Services de Moodle."""

    url_base_api: Optional[str]

    def __init__(self, sesion: Optional[requests.Session] = None):
        self.config_moodle = configuracion_global.moodle
        if not self.config_moodle.url:
            registrador.error("URL de Moodle no configurada. ClienteMoodle no será funcional.")
            self.url_base_api = None
        else:
            url_limpia = self.config_moodle.url + "/" if not self.config_moodle.url.endswith("/") else self.config_moodle.url
            self.url_base_api = urljoin(url_limpia, "webservice/rest/server.php")

        self.sesion = sesion or requests.Session()
        if self.config_moodle.token:
            self.sesion.params = {
                "wstoken": self.config_moodle.token,
                "moodlewsrestformat": "json",
            }

        if self.url_base_api:
            registrador.info(f"ClienteMoodle inicializado para URL: {self.url_base_api.rsplit('/', 1)[0]}")
        else:
            registrador.warning("ClienteMoodle inicializado sin una URL base API válida.")

    @staticmethod
    def _procesar_datos_cursos(datos_cursos: Any) -> List[modelos_api.CursoMoodle]:
        """Ayudante para procesar y validar datos de cursos de la API de Moodle."""
        if not isinstance(datos_cursos, list):
            if (
                isinstance(datos_cursos, dict)
                and "courses" in datos_cursos # Algunas funciones devuelven { "courses": [] }
                and isinstance(datos_cursos["courses"], list)
            ):
                datos_cursos = datos_cursos["courses"]
            else:
                raise ErrorAPIMoodle(
                    "Los datos de cursos no están en el formato de lista esperado.",
                    datos_respuesta=datos_cursos,
                )
        return [modelos_api.CursoMoodle(**cd) for cd in datos_cursos]

    def _formatear_parametros_moodle(
        self, args_entrada: Any, prefijo: str = "", dict_salida: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Transforma una estructura de diccionario/lista a un diccionario plano para la API de Moodle."""
        if dict_salida is None:
            dict_salida = {}
        if not isinstance(args_entrada, (list, dict)):
            dict_salida[prefijo] = args_entrada
            return dict_salida
        if isinstance(args_entrada, list):
            for i, item in enumerate(args_entrada):
                self._formatear_parametros_moodle(item, f"{prefijo}[{i}]", dict_salida)
        elif isinstance(args_entrada, dict):
            for clave, item in args_entrada.items():
                self._formatear_parametros_moodle(
                    item, f"{prefijo}[{clave}]" if prefijo else clave, dict_salida
                )
        return dict_salida

    def _realizar_peticion(
        self,
        funcion_ws: str,
        parametros_payload: Optional[Dict[str, Any]] = None,
        metodo_http: str = "POST",
    ) -> Any:
        """Realiza una petición a la API de Moodle."""
        if not self.url_base_api:
            raise ErrorAPIMoodle("URL base de Moodle no configurada.")

        parametros_url = {
            "wstoken": self.config_moodle.token, # Token también en params por si acaso
            "moodlewsrestformat": "json",
            "wsfunction": funcion_ws,
        }
        payload_api_formateado = (
            self._formatear_parametros_moodle(parametros_payload) if parametros_payload else {}
        )
        respuesta: Optional[requests.Response] = None

        try:
            registrador.debug(
                f"Llamando a función API Moodle '{funcion_ws}' con método {metodo_http.upper()}. URL: {self.url_base_api}"
            )
            if metodo_http.upper() == "POST":
                respuesta = self.sesion.post(
                    self.url_base_api,
                    params=parametros_url,
                    data=payload_api_formateado,
                    timeout=30,
                )
            elif metodo_http.upper() == "GET":
                todos_params_get = {**parametros_url, **payload_api_formateado}
                respuesta = self.sesion.get(self.url_base_api, params=todos_params_get, timeout=30)
            else:
                raise ErrorAPIMoodle(f"Método HTTP no soportado: {metodo_http}")

            respuesta.raise_for_status()
            datos_json = respuesta.json()

            if isinstance(datos_json, dict) and "exception" in datos_json:
                mensaje_error = datos_json.get("message", "Error desconocido de Moodle")
                registrador.error(
                    f"Error API Moodle para '{funcion_ws}': {datos_json.get('errorcode')} - {mensaje_error}"
                )
                raise ErrorAPIMoodle(mensaje=mensaje_error, datos_respuesta=datos_json)
            return datos_json
        except requests.exceptions.HTTPError as error_http:
            texto_respuesta = error_http.response.text if error_http.response is not None else "Sin respuesta"
            codigo = error_http.response.status_code if error_http.response is not None else None
            registrador.error(
                f"Error HTTP para '{funcion_ws}': {error_http} - Respuesta: {texto_respuesta}"
            )
            raise ErrorAPIMoodle(
                f"Error HTTP: {codigo}", codigo_estado=codigo, datos_respuesta=texto_respuesta
            ) from error_http
        except requests.exceptions.Timeout as error_timeout:
            registrador.error(f"Timeout para '{funcion_ws}': {error_timeout}")
            raise ErrorAPIMoodle(f"Timeout al conectar con Moodle: {error_timeout}") from error_timeout
        except requests.exceptions.RequestException as error_peticion:
            registrador.error(f"Excepción de petición para '{funcion_ws}': {error_peticion}")
            raise ErrorAPIMoodle(str(error_peticion)) from error_peticion
        except ValueError as error_json: # Error al decodificar JSON
            texto_respuesta = respuesta.text if respuesta is not None else "Sin respuesta"
            registrador.error(
                f"Error decodificación JSON para '{funcion_ws}': {error_json} - Respuesta: {texto_respuesta}"
            )
            raise ErrorAPIMoodle(
                f"Falló la decodificación de la respuesta JSON: {error_json}",
                datos_respuesta=texto_respuesta,
            ) from error_json

    # --- Métodos de Obtención de Datos ---
    def obtener_cursos_usuario(self, id_usuario: int) -> List[modelos_api.CursoMoodle]:
        """Obtiene los cursos de un usuario específico."""
        if id_usuario <= 0:
            raise ValueError("ID de usuario inválido.")
        registrador.info(f"Obteniendo cursos para id_usuario: {id_usuario}")
        try:
            datos_cursos = self._realizar_peticion(
                "core_enrol_get_users_courses", {"userid": id_usuario}
            )
            return self._procesar_datos_cursos(datos_cursos)
        except ErrorAPIMoodle as e:
            registrador.error(f"Falló la obtención de cursos para el usuario {id_usuario}: {e}")
            raise
        except Exception as e: # Captura general para errores inesperados
            registrador.exception(f"Error inesperado en obtener_cursos_usuario para {id_usuario}: {e}")
            raise ErrorAPIMoodle(f"Error inesperado obteniendo cursos: {e}")

    def obtener_todos_los_cursos(self) -> List[modelos_api.CursoMoodle]:
        """Recupera todos los cursos disponibles en el sitio Moodle."""
        registrador.info("Obteniendo todos los cursos disponibles de Moodle")
        try:
            datos_cursos = self._realizar_peticion("core_course_get_courses")
            return self._procesar_datos_cursos(datos_cursos)
        except ErrorAPIMoodle as e:
            registrador.error(f"Falló la obtención de todos los cursos: {e}")
            raise
        except Exception as e:
            registrador.exception(f"Error inesperado en obtener_todos_los_cursos: {e}")
            raise ErrorAPIMoodle(f"Error inesperado obteniendo todos los cursos: {e}")

    def obtener_contenidos_curso(self, id_curso: int) -> List[Dict[str, Any]]:
        """Obtiene los contenidos de un curso (secciones y módulos). Devuelve la estructura cruda."""
        registrador.info(f"Obteniendo contenidos para id_curso: {id_curso}")
        try:
            return self._realizar_peticion("core_course_get_contents", {"courseid": id_curso})
        except ErrorAPIMoodle as e:
            registrador.error(f"Falló la obtención de contenidos para el curso {id_curso}: {e}")
            raise

    def obtener_seccion_por_nombre(self, id_curso: int, nombre_seccion: str) -> Optional[modelos_api.SeccionMoodle]:
        """Recupera una sección específica por su nombre dentro de un curso."""
        registrador.info(f"Buscando sección '{nombre_seccion}' en curso {id_curso}")
        try:
            contenidos_curso = self.obtener_contenidos_curso(id_curso)
            if not isinstance(contenidos_curso, list):
                registrador.error(f"Se esperaba una lista de secciones, se obtuvo {type(contenidos_curso)}")
                return None
            for datos_seccion in contenidos_curso:
                if datos_seccion.get("name") == nombre_seccion:
                    registrador.info(f"Sección '{nombre_seccion}' encontrada con ID: {datos_seccion.get('id')}")
                    return modelos_api.SeccionMoodle(**datos_seccion)
            registrador.info(f"Sección '{nombre_seccion}' no encontrada en curso {id_curso}.")
            return None
        except ErrorAPIMoodle as e:
            registrador.error(f"Error API buscando sección '{nombre_seccion}': {e}")
            return None
        except Exception as e:
            registrador.exception(f"Error inesperado buscando sección '{nombre_seccion}': {e}")
            return None

    def obtener_modulo_curso_por_nombre(
        self, id_curso: int, id_seccion_objetivo: int, nombre_modulo_objetivo: str, tipo_mod_objetivo: Optional[str] = None
    ) -> Optional[modelos_api.ModuloMoodle]:
        """Encuentra un módulo específico por nombre dentro de una sección de un curso."""
        registrador.info(
            f"Buscando módulo '{nombre_modulo_objetivo}' (tipo: {tipo_mod_objetivo or 'cualquiera'}) en curso {id_curso}, sección {id_seccion_objetivo}"
        )
        try:
            contenidos_curso = self.obtener_contenidos_curso(id_curso)
            if not isinstance(contenidos_curso, list):
                registrador.error(f"Se esperaba lista de contenidos, se obtuvo {type(contenidos_curso)}")
                return None
            for datos_seccion in contenidos_curso:
                if datos_seccion.get("id") == id_seccion_objetivo:
                    for datos_modulo in datos_seccion.get("modules", []):
                        coincide_nombre = datos_modulo.get("name") == nombre_modulo_objetivo
                        coincide_tipo = (
                            tipo_mod_objetivo is None
                            or datos_modulo.get("modname") == tipo_mod_objetivo
                        )
                        if coincide_nombre and coincide_tipo:
                            registrador.info(f"Módulo '{nombre_modulo_objetivo}' encontrado (ID: {datos_modulo.get('id')})")
                            return modelos_api.ModuloMoodle(**datos_modulo)
                    registrador.info(f"Módulo '{nombre_modulo_objetivo}' no encontrado en sección {id_seccion_objetivo}.")
                    return None
            registrador.info(f"Sección {id_seccion_objetivo} no encontrada en curso {id_curso}.")
            return None
        except ErrorAPIMoodle as e:
            registrador.error(f"Error API buscando módulo '{nombre_modulo_objetivo}': {e}")
            return None
        except Exception as e:
            registrador.exception(f"Error inesperado buscando módulo '{nombre_modulo_objetivo}': {e}")
            return None

    def _parsear_contenidos_carpeta(self, modulo_carpeta: dict, id_cm_carpeta: int) -> List[modelos_api.ArchivoMoodle]:
        """Parsea los contenidos de un módulo de carpeta para extraer información de archivos."""
        archivos_datos = []
        for contenido in modulo_carpeta.get("contents", []):
            campos_requeridos = ("filename", "filepath", "filesize", "fileurl", "timemodified")
            if contenido.get("type") == "file" and all(k in contenido for k in campos_requeridos):
                archivos_datos.append(modelos_api.ArchivoMoodle(**contenido))
                registrador.debug(f"Archivo encontrado en carpeta: {contenido.get('filename')}")
            else:
                registrador.warning(f"Omitiendo contenido en carpeta {id_cm_carpeta}: {contenido}")
        registrador.info(f"Se encontraron {len(archivos_datos)} archivos en la carpeta {id_cm_carpeta}")
        return archivos_datos

    def _extraer_archivos_carpeta(self, id_curso: int, id_cm_carpeta: int) -> List[modelos_api.ArchivoMoodle]:
        """Método ayudante para extraer archivos de un módulo de carpeta dentro de los contenidos de un curso."""
        try:
            contenidos_curso = self.obtener_contenidos_curso(id_curso)
            for seccion in contenidos_curso:
                for modulo in seccion.get("modules", []):
                    if modulo.get("id") == id_cm_carpeta:
                        return self._parsear_contenidos_carpeta(modulo, id_cm_carpeta)
            registrador.warning(f"Módulo de carpeta {id_cm_carpeta} no encontrado en curso {id_curso}")
            return []
        except Exception as e:
            registrador.exception(f"Error extrayendo archivos de carpeta: {e}")
            return []

    def obtener_archivos_carpeta(self, id_cm_carpeta: int) -> List[modelos_api.ArchivoMoodle]:
        """Recupera todos los archivos de un módulo de carpeta de Moodle."""
        registrador.info(f"Obteniendo archivos para el módulo de carpeta ID (cmid): {id_cm_carpeta}")
        try:
            # Necesitamos el ID del curso para luego buscar la carpeta en core_course_get_contents
            # Usamos core_course_get_course_module para obtener el ID del curso y verificar tipo
            detalles_modulo_ws = self._realizar_peticion("core_course_get_course_module", {"cmid": id_cm_carpeta})

            if not detalles_modulo_ws or "cm" not in detalles_modulo_ws:
                registrador.error(f"No se pudieron obtener detalles para el módulo con cmid {id_cm_carpeta}")
                return []

            info_cm = detalles_modulo_ws["cm"]
            registrador.debug(f"Detalles del módulo: {info_cm}")

            if info_cm.get("modname") != "folder":
                registrador.error(f"Módulo con ID {id_cm_carpeta} no es una carpeta, es un '{info_cm.get('modname')}'")
                return []

            id_curso = info_cm.get("course")
            if not id_curso:
                registrador.error(f"No se pudo determinar el ID del curso para el módulo {id_cm_carpeta}")
                return []

            return self._extraer_archivos_carpeta(id_curso, id_cm_carpeta)
        except ErrorAPIMoodle as e:
            registrador.error(f"Error API obteniendo archivos para carpeta {id_cm_carpeta}: {e}")
            return []
        except Exception as e:
            registrador.exception(f"Error inesperado obteniendo archivos para carpeta {id_cm_carpeta}: {e}")
            return []

    def obtener_configuracion_n8n_curso(self, id_curso: int) -> Optional[Dict[str, Any]]:
        """Obtiene las configuraciones de N8N específicas de un curso desde Moodle."""
        registrador.info(f"Obteniendo configuración N8N para curso {id_curso}")
        try:
            datos_respuesta = self._realizar_peticion("local_entrenai_get_course_n8n_settings", {"courseid": id_curso})
            if not datos_respuesta or not isinstance(datos_respuesta, dict) or "exception" in datos_respuesta: # 'exception' in datos_respuesta es redundante por el manejo en _realizar_peticion
                registrador.warning(f"Configuraciones N8N no disponibles o respuesta inválida para curso {id_curso}. Respuesta: {datos_respuesta}")
                return None

            configuraciones = {}
            campos_esperados = ["initial_message", "system_message_append", "chat_title", "input_placeholder"]
            for campo in campos_esperados:
                if campo in datos_respuesta and datos_respuesta[campo] is not None: # Asegurar que el campo existe y no es None
                    configuraciones[campo] = datos_respuesta[campo]

            return configuraciones if configuraciones else None
        except ErrorAPIMoodle as e:
            registrador.warning(f"Error API obteniendo configuraciones N8N para curso {id_curso}: {e}")
            return None
        except Exception as e:
            registrador.exception(f"Error inesperado obteniendo configuraciones N8N para curso {id_curso}: {e}")
            return None

    # --- Métodos de Creación/Modificación ---
    def crear_seccion_curso(self, id_curso: int, nombre_seccion: str, posicion: int = 1) -> Optional[modelos_api.SeccionMoodle]:
        """Asegura la existencia de una sección en un curso. Si no existe, la crea y la devuelve."""
        registrador.info(f"Asegurando sección '{nombre_seccion}' en curso {id_curso} en posición {posicion}")

        seccion_existente = self.obtener_seccion_por_nombre(id_curso, nombre_seccion)
        if seccion_existente:
            registrador.info(f"Sección '{nombre_seccion}' ya existe con ID {seccion_existente.id}. Usando existente.")
            return seccion_existente

        registrador.info(f"Sección '{nombre_seccion}' no encontrada. Intentando crear con 'local_wsmanagesections_create_sections'.")
        try:
            # local_wsmanagesections_create_sections espera un array de secciones a crear
            payload_crear = {
                "courseid": id_curso,
                "sections": [{
                    "name": nombre_seccion, # Nombre deseado
                    "summary": "", # Sumario opcional
                    "sequence": "", # IDs de modulos, dejar vacío para nueva seccion
                    "visible": 1,
                    # 'number' o 'position' no son parámetros directos aquí, se gestiona por orden o WS más específico
                }]
            }
            # NOTA: local_wsmanagesections_create_sections puede no estar disponible o no permitir nombres al crear.
            # La versión en `src` usaba local_wsmanagesections_create_sections y luego obtenía detalles.
            # Si el WS no permite nombre al crear, se crea con nombre por defecto y luego se actualiza.
            # Por ahora, asumimos que el WS `local_wsmanagesections_update_sections` puede crearla si no existe, o `create_sections` con nombre.
            # Si `create_sections` no toma nombre, se necesitaría un `update_sections` después.
            # Vamos a probar una estrategia de "actualizar/crear" con local_wsmanagesections_update_sections
            # que parece más robusto si el WS lo soporta para creación implícita o es el mismo para renombrar.

            # Estrategia alternativa: crear con nombre por defecto y luego renombrar
            # 1. Crear sección (nombre por defecto)
            payload_creacion_simple = {"courseid": id_curso, "position": posicion, "number": 1} # Esto es hipotético
            # datos_creados = self._realizar_peticion("local_wsmanagesections_create_sections", payload_creacion_simple) # Asumiendo que este WS existe
            # if not isinstance(datos_creados, list) or not datos_creados:
            #     raise ErrorAPIMoodle("Falló la creación de la estructura de la sección.", datos_respuesta=datos_creados)
            # id_nueva_seccion = datos_creados[0].get("id")

            # 2. Actualizar la sección creada con el nombre deseado
            # payload_actualizar = {"courseid": id_curso, "sections": [{"id": id_nueva_seccion, "name": nombre_seccion, "summary": ""}]}
            # self._realizar_peticion("local_wsmanagesections_update_sections", payload_actualizar)
            # return self.obtener_seccion_por_nombre(id_curso, nombre_seccion) # Verificar

            # Usando la lógica de `src` que parece depender de un `local_wsmanagesections_create_sections`
            # que devuelve el ID y luego se usa `local_wsmanagesections_get_sections`
            # Esto requiere que el WS `local_wsmanagesections_create_sections` exista y funcione así.
            # Por simplicidad y siguiendo el patrón de `create_module_in_section`, intentaremos crear y luego obtener.
            # Si falla, es porque Moodle no tiene un WS unificado para "crear o actualizar sección con nombre".

            # El WS `local_wsmanagesections_update_sections` en el original se usa para *añadir módulos* a secciones existentes.
            # `local_wsmanagesections_create_sections` es el más probable para crear.
            # `local_wsmanagesections_get_sections` para obtener.
            # `local_wsmanagesections_update_sections` (con otro formato de payload) para actualizar nombre/sumario.

            # Paso 1: Crear la sección (puede tener un nombre por defecto)
            # El `position` en el create_sections del original era para el número de secciones a crear, no la posición.
            # La posición se determina por el orden en el array `sections` o Moodle lo asigna.
            datos_creados = self._realizar_peticion("local_wsmanagesections_create_sections", {"courseid": id_curso, "sections": [{}]}) # Crear una sección vacía
            if not datos_creados or not isinstance(datos_creados, list) or not datos_creados[0].get("id"):
                 raise ErrorAPIMoodle("No se pudo crear la sección o obtener su ID.", datos_respuesta=datos_creados)
            id_nueva_seccion = datos_creados[0]["id"]

            # Paso 2: Actualizar la sección creada con el nombre y sumario deseados
            payload_actualizacion = {
                "courseid": id_curso, # Requerido por el WS wrapper
                "sections": [{
                    "id": id_nueva_seccion,
                    "name": nombre_seccion,
                    "summary": "", # Sumario vacío por defecto
                    "summaryformat": 1 # Formato HTML
                }]
            }
            self._realizar_peticion("local_wsmanagesections_update_sections", payload_actualizacion)
            registrador.info(f"Sección creada con ID {id_nueva_seccion} y actualizada con nombre '{nombre_seccion}'.")

            # Paso 3: Obtener la sección actualizada para devolverla
            # Esto podría optimizarse si update_sections devolviera el objeto completo.
            return self.obtener_seccion_por_nombre(id_curso, nombre_seccion)

        except ErrorAPIMoodle as e:
            registrador.error(f"Error API creando/actualizando sección '{nombre_seccion}': {e}")
            return None
        except Exception as e:
            registrador.exception(f"Error inesperado creando/actualizando sección '{nombre_seccion}': {e}")
            return None

    def crear_modulo_en_seccion(
        self, id_curso: int, id_seccion: int, nombre_modulo: str, tipo_mod: str,
        parametros_instancia: Optional[Dict[str, Any]] = None,
        opciones_comunes_modulo: Optional[List[Dict[str, Any]]] = None # Como 'visible', 'groupmode'
    ) -> Optional[modelos_api.ModuloMoodle]:
        """Crea un módulo en una sección específica. Si ya existe uno con el mismo nombre y tipo, lo devuelve."""
        modulo_existente = self.obtener_modulo_curso_por_nombre(id_curso, id_seccion, nombre_modulo, tipo_mod)
        if modulo_existente:
            registrador.info(f"Módulo '{nombre_modulo}' ({tipo_mod}) ya existe en sección {id_seccion}. ID: {modulo_existente.id}")
            return modulo_existente

        registrador.info(f"Creando módulo '{nombre_modulo}' ({tipo_mod}) en curso {id_curso}, sección {id_seccion}")
        try:
            # El WS local_wsmanagesections_update_sections se usa para añadir/modificar módulos en una sección.
            # Espera el 'sectionreturn' para saber qué sección modificar y los módulos dentro.
            datos_modulo_api = {
                "modname": tipo_mod,
                "name": nombre_modulo,
                # "section": id_seccion, # No es necesario aquí, se especifica en 'sectionreturn'
            }
            if parametros_instancia: # Parámetros específicos del tipo de módulo (ej. externalurl para 'url')
                datos_modulo_api.update(parametros_instancia)

            # Opciones comunes del módulo (visible, idnumber, etc.)
            # El WS original los espera como una lista de diccionarios {name: x, value: y}
            # pero local_wsmanagesections_update_sections parece tomarlos directamente.
            if opciones_comunes_modulo:
                 for opt in opciones_comunes_modulo:
                    datos_modulo_api[opt["name"]] = opt["value"]

            payload = {
                "courseid": id_curso, # Requerido por el WS wrapper
                "sections": [{
                    "id": id_seccion, # ID de la sección donde se añadirá el módulo
                    "modules": [datos_modulo_api]
                }]
            }

            # Esta función no devuelve el ID del módulo creado directamente.
            self._realizar_peticion("local_wsmanagesections_update_sections", payload)
            registrador.info(f"Petición para crear/actualizar módulo '{nombre_modulo}' enviada.")

            # Volver a obtener el módulo para confirmar creación y obtener ID.
            return self.obtener_modulo_curso_por_nombre(id_curso, id_seccion, nombre_modulo, tipo_mod)

        except ErrorAPIMoodle as e:
            registrador.error(f"Error API añadiendo módulo '{nombre_modulo}': {e}")
            return None
        except Exception as e:
            registrador.exception(f"Error inesperado añadiendo módulo '{nombre_modulo}': {e}")
            return None

    def crear_carpeta_en_seccion(self, id_curso: int, id_seccion: int, nombre_carpeta: str, introduccion: str = "") -> Optional[modelos_api.ModuloMoodle]:
        registrador.info(f"Asegurando carpeta '{nombre_carpeta}' en curso {id_curso}, sección {id_seccion}")
        params_instancia = {
            "intro": introduccion or f"Carpeta para {nombre_carpeta}",
            "introformat": 1, # Formato HTML
            "display": 0,
            "showexpanded": 1,
        }
        opciones_comunes = [{"name": "visible", "value": 1}]
        return self.crear_modulo_en_seccion(id_curso, id_seccion, nombre_carpeta, "folder", params_instancia, opciones_comunes)

    def crear_url_en_seccion(
        self, id_curso: int, id_seccion: int, nombre_url: str, url_externa: str,
        descripcion: str = "", modo_visualizacion: int = 0
    ) -> Optional[modelos_api.ModuloMoodle]:
        registrador.info(f"Asegurando URL '{nombre_url}' -> '{url_externa}' en curso {id_curso}, sección {id_seccion}")
        params_instancia = {
            "externalurl": url_externa,
            "intro": descripcion or f"Enlace a {nombre_url}",
            "introformat": 1, # Formato HTML
            "display": modo_visualizacion,
        }
        opciones_comunes = [{"name": "visible", "value": 1}]
        return self.crear_modulo_en_seccion(id_curso, id_seccion, nombre_url, "url", params_instancia, opciones_comunes)

    def actualizar_sumario_seccion(self, id_curso: int, id_seccion: int, nuevo_sumario: str, formato_sumario: int = 1) -> bool:
        """Actualiza el sumario (descripción) de una sección específica."""
        registrador.info(f"Actualizando sumario para sección ID: {id_seccion} en curso ID: {id_curso}")
        try:
            payload = {
                "courseid": id_curso,
                "sections": [{
                    "id": id_seccion,
                    "summary": nuevo_sumario,
                    "summaryformat": formato_sumario
                }]
            }
            self._realizar_peticion("local_wsmanagesections_update_sections", payload)
            registrador.info(f"Sumario de sección {id_seccion} actualizado exitosamente.")
            return True
        except ErrorAPIMoodle as e:
            registrador.error(f"Error API actualizando sumario de sección {id_seccion} en curso {id_curso}: {e}")
            return False
        except Exception as e:
            registrador.exception(f"Error inesperado actualizando sumario de sección {id_seccion}: {e}")
            return False

    # --- Descarga de Archivos ---
    def descargar_archivo(self, url_archivo: str, directorio_descarga: Path, nombre_archivo: str) -> Path:
        """Descarga un archivo desde una URL de Moodle a un directorio local."""
        if not self.config_moodle.token:
            raise ErrorAPIMoodle("Token de Moodle no configurado, no se pueden descargar archivos.")

        directorio_descarga.mkdir(parents=True, exist_ok=True)
        ruta_archivo_local = directorio_descarga / nombre_archivo
        registrador.info(f"Descargando archivo Moodle desde {url_archivo} a {ruta_archivo_local}")

        try:
            url_efectiva = str(url_archivo) # Asegurar que es string
            if "token=" not in url_efectiva and "wstoken=" not in url_efectiva and self.config_moodle.token:
                conector = "&" if "?" in url_efectiva else "?"
                url_efectiva += f"{conector}token={self.config_moodle.token}"

            cabeceras = {"Accept-Encoding": "identity"} # Evitar compresión automática

            with requests.get(url_efectiva, stream=True, headers=cabeceras, timeout=60) as r: # Timeout más largo para descargas
                r.raise_for_status()
                tipo_contenido = r.headers.get("Content-Type", "").lower()

                if "text/" in tipo_contenido or \
                   tipo_contenido.endswith(("/markdown", "/md", "/json", "/xml", "/html", "/xhtml", "/css", "/javascript", "/csv")):
                    contenido = r.content.decode("utf-8", errors="replace")
                    with open(ruta_archivo_local, "w", encoding="utf-8") as f:
                        f.write(contenido)
                else: # Archivo binario
                    with open(ruta_archivo_local, "wb") as f:
                        for chunk in r.iter_content(chunk_size=8192):
                            if chunk:
                                f.write(chunk)
            registrador.info(f"Archivo '{nombre_archivo}' descargado exitosamente.")
            return ruta_archivo_local
        except requests.exceptions.HTTPError as e:
            registrador.error(f"Error HTTP descargando '{nombre_archivo}': {e} (URL: {url_archivo})")
            raise ErrorAPIMoodle(f"Falló la descarga del archivo '{nombre_archivo}': {e}") from e
        except Exception as e:
            registrador.exception(f"Error descargando archivo '{nombre_archivo}' desde {url_archivo}: {e}")
            raise ErrorAPIMoodle(f"Error inesperado descargando archivo '{nombre_archivo}': {e}") from e

[end of entrenai_refactor/nucleo/clientes/cliente_moodle.py]
