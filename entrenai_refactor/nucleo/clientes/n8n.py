import requests
from typing import List, Optional, Dict, Any
from urllib.parse import urljoin
import logging

class ErrorN8n(Exception):
    pass

class ClienteN8n:
    def __init__(self, url_base: str, api_key: Optional[str] = None):
        self.logger = logging.getLogger("cliente_n8n")
        self.url_base = url_base.rstrip("/") + "/api/v1/"
        self.sesion = requests.Session()
        if api_key:
            self.sesion.headers.update({"X-N8N-API-KEY": api_key})
        self.logger.info(f"ClienteN8n inicializado para URL: {self.url_base}")

    def _peticion(self, metodo: str, endpoint: str, parametros: Optional[Dict[str, Any]] = None, datos_json: Optional[Dict[str, Any]] = None):
        url = urljoin(self.url_base, endpoint)
        try:
            if metodo.upper() == "GET":
                resp = self.sesion.get(url, params=parametros)
            elif metodo.upper() == "POST":
                resp = self.sesion.post(url, params=parametros, json=datos_json)
            elif metodo.upper() == "PUT":
                resp = self.sesion.put(url, params=parametros, json=datos_json)
            else:
                raise ErrorN8n(f"Método HTTP no soportado: {metodo}")
            resp.raise_for_status()
            if resp.status_code == 204:
                return None
            return resp.json()
        except Exception as e:
            self.logger.error(f"Error en petición a N8n: {e}")
            raise ErrorN8n(str(e))

    def obtener_flujos(self) -> List[Dict[str, Any]]:
        datos = self._peticion("GET", "workflows")
        return datos.get("data", []) if isinstance(datos, dict) else datos

    def obtener_flujo(self, flujo_id: str) -> Optional[Dict[str, Any]]:
        datos = self._peticion("GET", f"workflows/{flujo_id}")
        if isinstance(datos, dict) and "data" in datos:
            return datos["data"]
        return datos

    def importar_flujo(self, flujo_json: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        datos = self._peticion("POST", "workflows", datos_json=flujo_json)
        return datos

    def actualizar_flujo(self, flujo_id: str, flujo_json: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        datos = self._peticion("PUT", f"workflows/{flujo_id}", datos_json=flujo_json)
        return datos 