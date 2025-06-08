import logging
import requests
from typing import List, Optional, Any, Dict
from urllib.parse import urljoin
from entrenai_refactor.api.modelos import CursoMoodle
from entrenai_refactor.config.configuracion import config

class ErrorAPIMoodle(Exception):
    pass

class ClienteMoodle:
    def __init__(self):
        self.logger = logging.getLogger("cliente_moodle")
        self.url_base = None
        if config.moodle_url:
            url_limpia = config.moodle_url + "/" if not config.moodle_url.endswith("/") else config.moodle_url
            self.url_base = urljoin(url_limpia, "webservice/rest/server.php")
        self.token = getattr(config, "moodle_token", None) or getattr(config, "token", None)
        self.sesion = requests.Session()
        if self.token:
            self.sesion.params = {
                "wstoken": self.token,
                "moodlewsrestformat": "json",
            }
        if self.url_base:
            self.logger.info(f"ClienteMoodle inicializado para URL: {self.url_base}")
        else:
            self.logger.warning("ClienteMoodle inicializado sin una URL base válida.")

    def _formatear_parametros(self, entrada: Any, prefijo: str = "", salida: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if salida is None:
            salida = {}
        if not isinstance(entrada, (list, dict)):
            salida[prefijo] = entrada
            return salida
        if isinstance(entrada, list):
            for idx, item in enumerate(entrada):
                self._formatear_parametros(item, f"{prefijo}[{idx}]", salida)
        elif isinstance(entrada, dict):
            for clave, item in entrada.items():
                self._formatear_parametros(item, f"{prefijo}[{clave}]" if prefijo else clave, salida)
        return salida

    def _peticion(self, funcion_ws: str, parametros: Optional[Dict[str, Any]] = None, metodo_http: str = "POST") -> Any:
        if not self.url_base:
            raise ErrorAPIMoodle("URL base de Moodle no configurada.")
        params_url = {
            "wstoken": self.token,
            "moodlewsrestformat": "json",
            "wsfunction": funcion_ws,
        }
        payload = self._formatear_parametros(parametros) if parametros else {}
        try:
            if metodo_http.upper() == "POST":
                respuesta = self.sesion.post(self.url_base, params=params_url, data=payload, timeout=30)
            elif metodo_http.upper() == "GET":
                todos_get = {**params_url, **payload}
                respuesta = self.sesion.get(self.url_base, params=todos_get, timeout=30)
            else:
                raise ErrorAPIMoodle(f"Método HTTP no soportado: {metodo_http}")
            respuesta.raise_for_status()
            datos = respuesta.json()
            if isinstance(datos, dict) and "exception" in datos:
                raise ErrorAPIMoodle(datos.get("message", "Error desconocido de Moodle"))
            return datos
        except Exception as e:
            self.logger.error(f"Error en petición a Moodle: {e}")
            raise ErrorAPIMoodle(str(e))

    def obtener_cursos_por_usuario(self, usuario_id: int) -> List[CursoMoodle]:
        if usuario_id <= 0:
            raise ValueError("ID de usuario inválido.")
        self.logger.info(f"Obteniendo cursos para usuario_id: {usuario_id}")
        datos = self._peticion("core_enrol_get_users_courses", {"userid": usuario_id})
        if not isinstance(datos, list):
            raise ErrorAPIMoodle("Respuesta inesperada de Moodle al obtener cursos.")
        cursos = []
        for c in datos:
            cursos.append(CursoMoodle(
                id=c.get("id"),
                nombre_corto=c.get("shortname", ""),
                nombre_completo=c.get("fullname", ""),
                nombre_mostrar=c.get("displayname", c.get("fullname", "")),
                resumen=c.get("summary", None)
            ))
        return cursos 