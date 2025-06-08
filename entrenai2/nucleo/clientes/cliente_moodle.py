from pathlib import Path
from typing import List, Optional, Dict, Any, Union, Callable
from urllib.parse import urljoin

import requests

from entrenai2.api.modelos import (
    CursoMoodle,
    SeccionMoodle,
    ModuloMoodle,
    ArchivoMoodle,
)
from entrenai2.configuracion.configuracion import config
from entrenai2.configuracion.registrador import obtener_registrador

registrador = obtener_registrador(__name__)


class ErrorAPIMoodle(Exception):
    """Excepción personalizada para errores relacionados con la API de Moodle."""
    def __init__(self, mensaje: str, codigo_estado: Optional[int] = None, respuesta: Optional[Any] = None):
        super().__init__(mensaje)
        self.codigo_estado = codigo_estado
        self.respuesta = respuesta

    def __str__(self):
        detalles = f" (Código de Estado: {self.codigo_estado}, Respuesta: {self.respuesta})"
        return f"{super().__str__()}{detalles}"


class ClienteMoodle:
    """Cliente para interactuar con la API de Web Services de Moodle."""

    def __init__(self, sesion: Optional[requests.Session] = None):
        if not config.moodle.url or not config.moodle.token:
            registrador.error("La URL y el TOKEN de Moodle deben estar configurados.")
            raise ValueError("La URL y el TOKEN de Moodle no están configurados.")

        url_limpia = config.moodle.url.rstrip('/') + '/'
        self.url_base = urljoin(url_limpia, "webservice/rest/server.php")
        self.token = config.moodle.token
        self.sesion = sesion or requests.Session()
        
        registrador.info(f"ClienteMoodle inicializado para URL: {self.url_base.rsplit('/', 1)[0]}")

    def _formatear_parametros(self, args_entrada: Any, prefijo: str = "", dict_salida: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Transforma una estructura anidada a un diccionario plano para la API de Moodle."""
        if dict_salida is None:
            dict_salida = {}
        if isinstance(args_entrada, list):
            for i, item in enumerate(args_entrada):
                self._formatear_parametros(item, f"{prefijo}[{i}]", dict_salida)
        elif isinstance(args_entrada, dict):
            for key, item in args_entrada.items():
                self._formatear_parametros(item, f"{prefijo}[{key}]" if prefijo else key, dict_salida)
        else:
            dict_salida[prefijo] = args_entrada
        return dict_salida

    def _realizar_solicitud(self, funcion_ws: str, parametros: Optional[Dict[str, Any]] = None) -> Any:
        """Realiza una petición a la API de Moodle y maneja la respuesta."""
        params_base = {
            "wstoken": self.token,
            "moodlewsrestformat": "json",
            "wsfunction": funcion_ws,
        }
        
        carga_formateada = self._formatear_parametros(parametros) if parametros else {}
        respuesta = None
        
        try:
            registrador.debug(f"Llamando a la función '{funcion_ws}' de la API de Moodle.")
            respuesta = self.sesion.post(self.url_base, params=params_base, data=carga_formateada, timeout=30)
            respuesta.raise_for_status()
            
            datos_json = respuesta.json()

            if isinstance(datos_json, dict) and "exception" in datos_json:
                mensaje_error = datos_json.get("message", "Error desconocido de Moodle")
                registrador.error(f"Error en '{funcion_ws}': {datos_json.get('errorcode')} - {mensaje_error}")
                raise ErrorAPIMoodle(mensaje=mensaje_error, respuesta=datos_json)
            
            return datos_json

        except requests.exceptions.RequestException as e:
            codigo_estado = e.response.status_code if e.response else None
            texto_respuesta = e.response.text if e.response else "Sin respuesta"
            registrador.error(f"Error de conexión con Moodle para '{funcion_ws}': {e}")
            raise ErrorAPIMoodle(f"Error de conexión: {e}", codigo_estado=codigo_estado, respuesta=texto_respuesta) from e
        except ValueError as e:
            texto_respuesta = respuesta.text if respuesta else "Sin respuesta"
            registrador.error(f"Error de decodificación JSON para '{funcion_ws}': {e}")
            raise ErrorAPIMoodle(f"La respuesta de Moodle no es un JSON válido: {e}", respuesta=texto_respuesta) from e

    def obtener_cursos_por_usuario(self, id_usuario: int) -> List[CursoMoodle]:
        """Obtiene los cursos de un usuario específico."""
        registrador.info(f"Obteniendo cursos para el usuario con ID: {id_usuario}")
        datos_cursos = self._realizar_solicitud("core_enrol_get_users_courses", {"userid": id_usuario})
        if not isinstance(datos_cursos, list):
            raise ErrorAPIMoodle("La respuesta de cursos no es una lista.", respuesta=datos_cursos)
        return [CursoMoodle(**cd) for cd in datos_cursos]

    def obtener_todos_los_cursos(self) -> List[CursoMoodle]:
        """Recupera todos los cursos disponibles en el sitio Moodle."""
        registrador.info("Obteniendo todos los cursos de Moodle.")
        datos_cursos = self._realizar_solicitud("core_course_get_courses")
        if isinstance(datos_cursos, dict) and "courses" in datos_cursos:
             datos_cursos = datos_cursos["courses"]
        if not isinstance(datos_cursos, list):
            raise ErrorAPIMoodle("La respuesta de cursos no es una lista o un diccionario con la clave 'courses'.", respuesta=datos_cursos)
        return [CursoMoodle(**cd) for cd in datos_cursos]

    def obtener_contenidos_curso(self, id_curso: int) -> List[Dict[str, Any]]:
        """Obtiene todos los contenidos de un curso."""
        registrador.info(f"Obteniendo contenidos para el curso con ID: {id_curso}")
        return self._realizar_solicitud("core_course_get_contents", {"courseid": id_curso})

    def obtener_archivos_de_carpeta(self, id_modulo_carpeta: int) -> List[ArchivoMoodle]:
        """Recupera la lista de archivos dentro de un módulo de tipo 'folder'."""
        registrador.info(f"Obteniendo archivos del módulo de carpeta con ID: {id_modulo_carpeta}")
        try:
            detalles_modulo = self._realizar_solicitud("core_course_get_course_module", {"cmid": id_modulo_carpeta})
            if not detalles_modulo or "cm" not in detalles_modulo or detalles_modulo["cm"].get("modname") != "folder":
                registrador.warning(f"El módulo {id_modulo_carpeta} no es una carpeta válida.")
                return []
            
            id_curso = detalles_modulo["cm"]["course"]
            contenidos_curso = self.obtener_contenidos_curso(id_curso)

            for seccion in contenidos_curso:
                for modulo in seccion.get("modules", []):
                    if modulo.get("id") == id_modulo_carpeta:
                        archivos = [ArchivoMoodle(**contenido) for contenido in modulo.get("contents", []) if contenido.get("type") == "file"]
                        registrador.info(f"Se encontraron {len(archivos)} archivos en la carpeta {id_modulo_carpeta}.")
                        return archivos
            return []
        except ErrorAPIMoodle as e:
            registrador.error(f"No se pudieron obtener los archivos de la carpeta {id_modulo_carpeta}: {e}")
            return []

    def descargar_archivo(self, url_archivo: str, directorio_descarga: Path, nombre_archivo: str) -> Path:
        """Descarga un archivo desde una URL de Moodle a un directorio local."""
        directorio_descarga.mkdir(parents=True, exist_ok=True)
        ruta_archivo_local = directorio_descarga / nombre_archivo
        registrador.info(f"Descargando archivo desde Moodle a {ruta_archivo_local}")

        try:
            url_con_token = f"{url_archivo}?token={self.token}"
            with self.sesion.get(url_con_token, stream=True, timeout=60) as r:
                r.raise_for_status()
                with open(ruta_archivo_local, "wb") as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        f.write(chunk)
            registrador.info(f"Archivo '{nombre_archivo}' descargado exitosamente.")
            return ruta_archivo_local
        except requests.exceptions.RequestException as e:
            registrador.error(f"Error al descargar '{nombre_archivo}': {e}")
            raise ErrorAPIMoodle(f"Fallo en la descarga del archivo '{nombre_archivo}'", respuesta=str(e)) from e

    def asegurar_existencia_recurso(self, id_curso: int, nombre_recurso: str, creador_recurso: Callable[[], Optional[Union[ModuloMoodle, SeccionMoodle]]]) -> Optional[Union[ModuloMoodle, SeccionMoodle]]:
        """Asegura que un recurso exista, creándolo si es necesario."""
        registrador.info(f"Asegurando la existencia del recurso '{nombre_recurso}' en el curso {id_curso}.")
        contenidos = self.obtener_contenidos_curso(id_curso)
        for seccion in contenidos:
            if seccion.get("name") == nombre_recurso:
                registrador.info(f"La sección '{nombre_recurso}' ya existe.")
                return SeccionMoodle(**seccion)
            for modulo in seccion.get("modules", []):
                if modulo.get("name") == nombre_recurso:
                    registrador.info(f"El módulo '{nombre_recurso}' ya existe.")
                    return ModuloMoodle(**modulo)
        registrador.info(f"El recurso '{nombre_recurso}' no existe, procediendo a crearlo.")
        return creador_recurso()

    def crear_seccion_curso(self, id_curso: int, nombre_seccion: str) -> Optional[SeccionMoodle]:
        """Crea una sección si no existe. Requiere el plugin 'local_wsmanagesections' en Moodle."""
        registrador.info(f"Creando sección '{nombre_seccion}' en el curso {id_curso}.")
        try:
            resultado = self._realizar_solicitud("local_wsmanagesections_create_sections", {"courseid": id_curso, "sections": [{"name": nombre_seccion}]})
            if resultado and isinstance(resultado, list):
                return SeccionMoodle(**resultado[0])
            raise ErrorAPIMoodle("La creación de la sección no devolvió un resultado válido.", respuesta=resultado)
        except ErrorAPIMoodle as e:
            registrador.error(f"No se pudo crear la sección '{nombre_seccion}': {e}. Puede que el plugin 'local_wsmanagesections' no esté instalado.")
            return None

    def crear_carpeta_en_seccion(self, id_curso: int, id_seccion: int, nombre_carpeta: str) -> Optional[ModuloMoodle]:
        """Crea una carpeta en una sección específica."""
        registrador.info(f"Creando carpeta '{nombre_carpeta}' en la sección {id_seccion}.")
        parametros = {
            "courseid": id_curso,
            "modules": [{
                "modname": "folder",
                "name": nombre_carpeta,
                "section": id_seccion,
                "intro": f"Carpeta para {nombre_carpeta}",
            }]
        }
        self._realizar_solicitud("local_wsmanagesections_update_sections", parametros)
        # Tras crear, buscamos el módulo para devolver su info completa
        contenidos = self.obtener_contenidos_curso(id_curso)
        for seccion in contenidos:
            if seccion.get("id") == id_seccion:
                for modulo in seccion.get("modules", []):
                    if modulo.get("name") == nombre_carpeta and modulo.get("modname") == "folder":
                        return ModuloMoodle(**modulo)
        return None

    def crear_url_en_seccion(self, id_curso: int, id_seccion: int, nombre_url: str, url_externa: str) -> Optional[ModuloMoodle]:
        """Crea un recurso de tipo URL en una sección."""
        registrador.info(f"Creando URL '{nombre_url}' en la sección {id_seccion}.")
        parametros = {
            "courseid": id_curso,
            "modules": [{
                "modname": "url",
                "name": nombre_url,
                "section": id_seccion,
                "externalurl": url_externa,
            }]
        }
        self._realizar_solicitud("local_wsmanagesections_update_sections", parametros)
        # Tras crear, buscamos el módulo para devolver su info completa
        contenidos = self.obtener_contenidos_curso(id_curso)
        for seccion in contenidos:
            if seccion.get("id") == id_seccion:
                for modulo in seccion.get("modules", []):
                    if modulo.get("name") == nombre_url and modulo.get("modname") == "url":
                        return ModuloMoodle(**modulo)
        return None

    def obtener_configuracion_n8n_curso(self, id_curso: int) -> Optional[Dict[str, Any]]:
        """Obtiene las configuraciones de n8n de un curso. Requiere el plugin 'local_entrenai' en Moodle."""
        registrador.info(f"Obteniendo configuración de n8n para el curso {id_curso}.")
        try:
            configuracion = self._realizar_solicitud("local_entrenai_get_course_n8n_settings", {"courseid": id_curso})
            if not isinstance(configuracion, dict) or "exception" in configuracion:
                registrador.warning(f"No se encontró configuración de n8n para el curso {id_curso}.")
                return None
            return configuracion
        except ErrorAPIMoodle as e:
            registrador.error(f"No se pudo obtener la configuración de n8n para el curso {id_curso}: {e}")
            return None
