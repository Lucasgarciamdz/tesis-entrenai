import json
from pathlib import Path
from typing import List, Optional, Dict, Any
from urllib.parse import urljoin
import uuid

import requests

from entrenai2.api.modelos import FlujoTrabajoN8N
from entrenai2.configuracion.configuracion import config
from entrenai2.configuracion.registrador import obtener_registrador

registrador = obtener_registrador(__name__)


class ErrorClienteN8N(Exception):
    """Excepción personalizada para errores del Cliente N8N."""
    def __init__(self, mensaje: str, codigo_estado: Optional[int] = None, respuesta: Optional[Any] = None):
        super().__init__(mensaje)
        self.codigo_estado = codigo_estado
        self.respuesta = respuesta

    def __str__(self):
        detalles = f" (Código de Estado: {self.codigo_estado}, Respuesta: {self.respuesta})"
        return f"{super().__str__()}{detalles}"


class ClienteN8N:
    """Cliente para interactuar con la API de n8n."""

    def __init__(self, sesion: Optional[requests.Session] = None):
        self.url_base = None
        if config.n8n.url and config.n8n.clave_api:
            self.url_base = urljoin(config.n8n.url.rstrip('/') + '/', "api/v1/")
            self.sesion = sesion or requests.Session()
            self.sesion.headers.update({"X-N8N-API-KEY": config.n8n.clave_api})
            registrador.info(f"ClienteN8N inicializado para URL base: {self.url_base}")
        else:
            registrador.warning("La URL o la CLAVE_API de n8n no están configuradas. El cliente no será funcional.")
            self.sesion = requests.Session()

    def _realizar_solicitud(self, metodo: str, endpoint: str, datos_json: Optional[Dict[str, Any]] = None) -> Any:
        """Realiza una petición a la API de n8n y maneja la respuesta."""
        if not self.url_base:
            raise ErrorClienteN8N("El cliente N8N no está configurado.")
            
        url = urljoin(self.url_base, endpoint)
        respuesta = None
        try:
            registrador.debug(f"Realizando solicitud {metodo} a {url}")
            respuesta = self.sesion.request(method=metodo, url=url, json=datos_json, timeout=30)
            respuesta.raise_for_status()
            
            if respuesta.status_code == 204:
                return None
            return respuesta.json()

        except requests.exceptions.RequestException as e:
            codigo = e.response.status_code if e.response else None
            texto_resp = e.response.text if e.response else "Sin respuesta"
            registrador.error(f"Error de conexión con n8n en '{endpoint}': {e}")
            raise ErrorClienteN8N(f"Error de conexión: {e}", codigo_estado=codigo, respuesta=texto_resp) from e
        except ValueError as e:
            texto_resp = respuesta.text if respuesta else "Sin respuesta"
            registrador.error(f"Error de decodificación JSON en '{endpoint}': {e}")
            raise ErrorClienteN8N("La respuesta de n8n no es un JSON válido.", respuesta=texto_resp) from e

    def obtener_lista_flujos(self) -> List[FlujoTrabajoN8N]:
        """Obtiene la lista de todos los flujos de trabajo."""
        registrador.info("Obteniendo la lista de flujos de trabajo de n8n.")
        respuesta = self._realizar_solicitud("GET", "workflows")
        flujos_data = respuesta.get("data", [])
        return [FlujoTrabajoN8N(**datos) for datos in flujos_data]

    def obtener_detalles_flujo(self, id_flujo: str) -> Optional[FlujoTrabajoN8N]:
        """Obtiene los detalles de un flujo de trabajo específico."""
        registrador.info(f"Obteniendo detalles para el flujo de trabajo con ID: {id_flujo}")
        try:
            datos_flujo = self._realizar_solicitud("GET", f"workflows/{id_flujo}")
            if datos_flujo:
                return FlujoTrabajoN8N(**datos_flujo)
            return None
        except ErrorClienteN8N as e:
            if e.codigo_estado == 404:
                registrador.warning(f"Flujo de trabajo con ID {id_flujo} no encontrado.")
                return None
            raise

    def importar_flujo(self, datos_flujo: Dict[str, Any]) -> FlujoTrabajoN8N:
        """Importa un nuevo flujo de trabajo a n8n."""
        registrador.info(f"Importando nuevo flujo de trabajo: '{datos_flujo.get('name')}'")
        respuesta = self._realizar_solicitud("POST", "workflows", datos_json=datos_flujo)
        return FlujoTrabajoN8N(**respuesta)

    def activar_flujo(self, id_flujo: str) -> bool:
        """Activa un flujo de trabajo."""
        registrador.info(f"Activando flujo de trabajo con ID: {id_flujo}")
        try:
            self._realizar_solicitud("PATCH", f"workflows/{id_flujo}", datos_json={"active": True})
            return True
        except ErrorClienteN8N as e:
            registrador.error(f"No se pudo activar el flujo {id_flujo}: {e}")
            return False

    def obtener_url_webhook(self, datos_flujo: Dict[str, Any]) -> Optional[str]:
        """Extrae la URL del webhook del nodo de chat del flujo."""
        for nodo in datos_flujo.get("nodes", []):
            if "chatTrigger" in nodo.get("type", ""):
                id_webhook = nodo.get("webhookId")
                if id_webhook:
                    url_base_n8n = config.n8n.url or ""
                    url_base_webhook = config.n8n.url_webhook or url_base_n8n.replace("/api/v1/", "")
                    return urljoin(url_base_webhook.rstrip('/') + '/', f"webhook/{id_webhook}/chat")
        return None

    def configurar_y_desplegar_flujo_chat(self, id_curso: int, nombre_curso: str, nombre_coleccion_pgvector: str, **kwargs) -> Optional[str]:
        """
        Asegura que un flujo de chat para un curso exista, esté configurado y activo.
        Devuelve la URL del webhook si tiene éxito.
        """
        nombre_flujo = f"Entrenai - {id_curso} - {nombre_curso}"
        registrador.info(f"Configurando y desplegando flujo de chat para: '{nombre_flujo}'")

        flujos = self.obtener_lista_flujos()
        flujo_existente = next((f for f in flujos if f.nombre == nombre_flujo), None)

        if flujo_existente and flujo_existente.id:
            registrador.info(f"Se encontró un flujo existente con ID: {flujo_existente.id}")
            if not flujo_existente.activo:
                self.activar_flujo(flujo_existente.id)
            
            detalles = self.obtener_detalles_flujo(flujo_existente.id)
            return self.obtener_url_webhook(detalles.model_dump() if detalles else {})

        registrador.info("No se encontró un flujo existente. Creando uno nuevo desde la plantilla.")
        
        ruta_plantilla = Path(config.n8n.ruta_json_flujo)
        if not ruta_plantilla.is_file():
            raise FileNotFoundError(f"No se encontró la plantilla de flujo en: {ruta_plantilla}")

        with open(ruta_plantilla, "r") as f:
            plantilla_flujo = json.load(f)

        plantilla_flujo["name"] = nombre_flujo
        id_webhook_generado = str(uuid.uuid4())

        for nodo in plantilla_flujo.get("nodes", []):
            if "chatTrigger" in nodo.get("type", ""):
                nodo["webhookId"] = id_webhook_generado
            elif "vectorStorePGVector" in nodo.get("type", ""):
                if "parameters" not in nodo:
                    nodo["parameters"] = {}
                nodo["parameters"]["tableName"] = nombre_coleccion_pgvector
        
        flujo_importado = self.importar_flujo(plantilla_flujo)
        if not flujo_importado.id:
            raise ErrorClienteN8N("Falló la importación del flujo desde la plantilla.")

        self.activar_flujo(flujo_importado.id)
        
        flujo_final = self.obtener_detalles_flujo(flujo_importado.id)
        return self.obtener_url_webhook(flujo_final.model_dump() if flujo_final else {})
