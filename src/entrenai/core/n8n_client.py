import requests
import json
import os
from typing import List, Optional, Dict, Any
from urllib.parse import urljoin

from src.entrenai.config import N8NConfig, base_config
from src.entrenai.core.models import N8NWorkflow
from src.entrenai.utils.logger import get_logger

logger = get_logger(__name__)


class N8NClientError(Exception):
    """Excepción personalizada para errores de N8NClient."""

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


class N8NClient:
    """Cliente para interactuar con la API de N8N."""

    base_url: Optional[str]
    api_key: Optional[str]
    webhook_url: Optional[str]

    def __init__(self, config: N8NConfig, session: Optional[requests.Session] = None):
        self.config = config
        self.base_url = config.url
        self.api_key = config.api_key
        self.webhook_url = config.webhook_url
        self.session = session or requests.Session()

        if self.config.api_key:
            self.session.headers.update({"X-N8N-API-KEY": self.config.api_key})

        if not self.base_url:
            logger.error("URL de N8N no configurada. N8NClient no será funcional.")
        else:
            if not self.base_url.endswith("/"):
                self.base_url += "/"
            if not self.base_url.endswith("api/v1/"):
                self.base_url = urljoin(self.base_url, "api/v1/")
            logger.info(f"N8NClient inicializado para URL base: {self.base_url}")

    def _make_request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        json_data: Optional[Dict[str, Any]] = None,
    ) -> Any:
        """Realiza una petición a la API de N8N."""
        if not self.base_url:
            raise N8NClientError("N8NClient no configurado con URL base.")

        url = urljoin(self.base_url, endpoint)
        response: Optional[requests.Response] = None
        try:
            logger.debug(
                f"Llamando a N8N API endpoint '{endpoint}' con método {method.upper()}. URL: {url}"
            )
            if method.upper() == "GET":
                response = self.session.get(url, params=params)
            elif method.upper() == "POST":
                response = self.session.post(url, params=params, json=json_data)
            elif method.upper() == "PUT":
                response = self.session.put(url, params=params, json=json_data)
            elif method.upper() == "DELETE":
                response = self.session.delete(url, params=params)
            else:
                raise N8NClientError(f"Método HTTP no soportado: {method}")

            response.raise_for_status()

            if response.status_code == 204:  # No Content
                return None
            return response.json()

        except requests.exceptions.HTTPError as http_err:
            resp_text = response.text if response is not None else "Sin respuesta"
            status = response.status_code if response is not None else None
            logger.error(
                f"Error HTTP llamando a N8N {endpoint}: {http_err} - Respuesta: {resp_text}"
            )
            raise N8NClientError(
                str(http_err), status_code=status, response_data=resp_text
            ) from http_err
        except requests.exceptions.RequestException as req_err:
            logger.error(f"Excepción de petición para N8N {endpoint}: {req_err}")
            raise N8NClientError(str(req_err)) from req_err
        except ValueError as json_err:
            resp_text = response.text if response is not None else "Sin respuesta"
            logger.error(
                f"Error de decodificación JSON para N8N {endpoint}: {json_err} - Respuesta: {resp_text}"
            )
            raise N8NClientError(
                f"Falló la decodificación de la respuesta JSON: {json_err}",
                response_data=resp_text,
            ) from json_err

    def get_workflows_list(
        self, limit: Optional[int] = None, tags: Optional[str] = None
    ) -> List[N8NWorkflow]:
        """Obtiene una lista de workflows de N8N."""
        params = {}
        if limit is not None:
            params["limit"] = limit
        if tags is not None:
            params["tags"] = tags
        try:
            response_data = self._make_request("GET", "workflows", params=params)
            if (
                isinstance(response_data, dict)
                and "data" in response_data
                and isinstance(response_data["data"], list)
            ):
                workflows_raw = response_data["data"]
            elif isinstance(response_data, list):
                workflows_raw = response_data
            else:
                raise N8NClientError(
                    "Lista de workflows no está en el formato esperado.",
                    response_data=response_data,
                )
            return [N8NWorkflow(**wf_data) for wf_data in workflows_raw]
        except N8NClientError as e:
            logger.error(f"Falló la obtención de la lista de workflows de N8N: {e}")
            raise
        except Exception as e:
            logger.exception(
                f"Error inesperado parseando lista de workflows de N8N: {e}"
            )
            raise N8NClientError(f"Error inesperado parseando workflows de N8N: {e}")

    def get_workflow_details_json(self, workflow_id: str) -> Optional[Dict[str, Any]]:
        """Obtiene la estructura JSON completa de un workflow específico por su ID."""
        try:
            workflow_data = self._make_request("GET", f"workflows/{workflow_id}")
            # La API GET /workflows/{id} devuelve el objeto workflow completo
            if isinstance(workflow_data, dict) and "id" in workflow_data:
                return workflow_data
            logger.warning(
                f"Respuesta inesperada o estructura no válida para detalles JSON de workflow '{workflow_id}': {workflow_data}"
            )
            return None
        except N8NClientError as e:
            if e.status_code == 404:
                logger.info(
                    f"Workflow con ID '{workflow_id}' no encontrado en N8N (para JSON completo)."
                )
                return None
            logger.error(
                f"Falló la obtención de detalles JSON para workflow '{workflow_id}': {e}"
            )
            raise
        except Exception as e:
            logger.exception(
                f"Error inesperado obteniendo detalles JSON de workflow N8N para '{workflow_id}': {e}"
            )
            raise N8NClientError(
                f"Error inesperado obteniendo detalles JSON de workflow N8N: {e}"
            )

    def import_workflow(
        self, workflow_json_content: Dict[str, Any]
    ) -> Optional[N8NWorkflow]:
        """
        Importa un workflow desde un contenido JSON.
        Esto típicamente crea un nuevo workflow en N8N.
        """
        try:
            workflow_name = workflow_json_content.get(
                "name", "Workflow Importado Sin Nombre"
            )
            logger.info(f"Intentando importar/crear workflow '{workflow_name}' en N8N.")

            # Campos permitidos para la creación de un workflow según la API de N8N (típicos)
            # Documentación de N8N API (ej. /v1/workflows POST) especifica los campos.
            # Generalmente son: name, nodes, connections, settings, staticData.
            # Campos como 'id', 'active', 'tags', 'createdAt', 'updatedAt' son usualmente de solo lectura o gestionados por N8N.
            allowed_fields = {"name", "nodes", "connections", "settings", "staticData"}

            payload_for_n8n: Dict[str, Any] = {
                key: value
                for key, value in workflow_json_content.items()
                if key in allowed_fields
            }
            # Asegurar que los campos esenciales estén, aunque sea vacíos si no están en el original
            payload_for_n8n.setdefault(
                "name", "Workflow Importado"
            )  # N8N requiere un nombre
            payload_for_n8n.setdefault("nodes", [])
            payload_for_n8n.setdefault("connections", {})
            payload_for_n8n.setdefault("settings", {})
            # staticData es opcional y solo se incluye si está presente en el original

            logger.debug(
                f"Payload limpio para N8N import/create: {json.dumps(payload_for_n8n, indent=2)}"
            )

            imported_workflow_data = self._make_request(
                "POST", "workflows", json_data=payload_for_n8n
            )

            # La respuesta de N8N para POST /workflows usualmente es el objeto del workflow creado.
            if (
                isinstance(imported_workflow_data, dict)
                and "id" in imported_workflow_data
            ):
                logger.info(
                    f"Workflow importado/creado exitosamente. ID: {imported_workflow_data['id']}"
                )
                return N8NWorkflow(**imported_workflow_data)
            # A veces N8N puede devolver una lista con un solo elemento
            elif (
                isinstance(imported_workflow_data, list)
                and len(imported_workflow_data) == 1
                and "id" in imported_workflow_data[0]
            ):
                logger.info(
                    f"Workflow importado/creado exitosamente (respuesta en lista). ID: {imported_workflow_data[0]['id']}"
                )
                return N8NWorkflow(**imported_workflow_data[0])
            else:
                logger.error(
                    f"Estructura de respuesta inesperada después de importar workflow: {imported_workflow_data}"
                )
                return None
        except N8NClientError as e:
            logger.error(f"Falló la importación del workflow a N8N: {e}")
            return None
        except Exception as e:
            logger.exception(
                f"Error inesperado durante la importación del workflow de N8N: {e}"
            )
            return None

    def activate_workflow(self, workflow_id: str) -> bool:
        """Activa un workflow por su ID."""
        try:
            self._make_request("POST", f"workflows/{workflow_id}/activate")
            logger.info(f"Workflow ID: {workflow_id} activado exitosamente.")
            return True
        except N8NClientError as e:
            logger.error(f"Falló la activación del workflow ID {workflow_id}: {e}")
            return False
        except Exception as e:
            logger.exception(
                f"Error inesperado activando workflow N8N ID {workflow_id}: {e}"
            )
            return False

    def delete_workflow(self, workflow_id: str) -> bool:
        """Elimina un workflow por su ID."""
        try:
            self._make_request("DELETE", f"workflows/{workflow_id}")
            logger.info(f"Workflow ID: {workflow_id} eliminado exitosamente.")
            return True
        except N8NClientError as e:
            logger.error(f"Falló la eliminación del workflow ID {workflow_id}: {e}")
            return False
        except Exception as e:
            logger.exception(
                f"Error inesperado eliminando workflow N8N ID {workflow_id}: {e}"
            )
            return False

    def _get_webhook_url_from_workflow_json(
        self, workflow_json: Dict[str, Any]
    ) -> Optional[str]:
        """Extrae el webhookId del nodo chatTrigger en el JSON del workflow y construye la URL."""
        nodes = workflow_json.get("nodes", [])
        for node in nodes:
            if node.get("type") == "@n8n/n8n-nodes-langchain.chatTrigger":
                webhook_id = node.get("webhookId")
                if webhook_id:
                    base_webhook_url = self.webhook_url or self.base_url
                    if not base_webhook_url:
                        logger.error(
                            "No se pudo determinar la URL base para webhooks de N8N (N8N_WEBHOOK_URL o N8N_URL no configuradas)."
                        )
                        return None

                    if (
                        "/api/v1" in base_webhook_url
                    ):  # Asegurar que no use el path de la API
                        base_webhook_url = base_webhook_url.split("/api/v1")[0]
                    if not base_webhook_url.endswith("/"):
                        base_webhook_url += "/"

                    final_webhook_url = urljoin(
                        base_webhook_url, f"webhook/{webhook_id}"
                    )
                    logger.debug(f"URL de webhook construida: {final_webhook_url}")
                    return final_webhook_url
        logger.warning(
            "No se encontró nodo de tipo '@n8n/n8n-nodes-langchain.chatTrigger' con 'webhookId' en el JSON del workflow."
        )
        return None

    def configure_and_deploy_chat_workflow(
        self,
        course_id: int,
        course_name: str,
        qdrant_collection_name: str,
        ai_params: Dict[str, Any],
        workflow_template_path: Optional[str] = None,
    ) -> Optional[str]:
        """Configura y despliega el workflow de chat en N8N.

        Args:
            course_id: ID del curso en Moodle
            course_name: Nombre del curso
            qdrant_collection_name: Nombre de la colección en Qdrant
            ai_params: Parámetros del proveedor de IA (Ollama o Gemini)
            workflow_template_path: Ruta opcional a la plantilla del workflow

        Returns:
            URL del webhook del workflow de chat
        """
        template_path = workflow_template_path or self.config.workflow_template_path

        if not template_path or not os.path.exists(template_path):
            logger.error(
                f"Plantilla de workflow no encontrada en la ruta: {template_path}"
            )
            return None

        try:
            with open(template_path, "r", encoding="utf-8") as f:
                workflow_template = json.load(f)
        except Exception as e:
            logger.error(f"Error al cargar la plantilla del workflow: {e}")
            return None

        # Personalizar el workflow
        try:
            workflow_name = (
                f"Entrenai_Chat_Curso_{course_id}_{course_name.replace(' ', '_')}"
            )
            workflow_template["name"] = workflow_name

            # Actualizar nodos con parámetros específicos del curso
            for node in workflow_template.get("nodes", []):
                # Actualizar el nodo de Qdrant con el nombre de la colección
                if (
                    node.get("type") == "n8n-nodes-base.httpRequest"
                    and "qdrant" in str(node.get("parameters", {})).lower()
                ):
                    # Parámetros de Qdrant (supone un nodo HTTP Request a Qdrant)
                    if "parameters" in node:
                        # Actualizar el payload JSON para incluir el nombre de la colección
                        if "body" in node["parameters"]:
                            body = json.loads(node["parameters"]["body"])
                            if "collection_name" in body:
                                body["collection_name"] = qdrant_collection_name
                            node["parameters"]["body"] = json.dumps(body)

                # Actualizar nodos de IA (Ollama o Gemini)
                if node.get("type") == "n8n-nodes-base.httpRequest" and (
                    "ollama" in str(node.get("parameters", {})).lower()
                    or "gemini" in str(node.get("parameters", {})).lower()
                ):
                    # Actualizar parámetros de IA siguiendo el tipo de proveedor
                    if "parameters" in node:
                        # Detectar si es un nodo para embeddings o para QA
                        node_purpose = (
                            "embedding" if "embed" in str(node).lower() else "qa"
                        )

                        # Determinar qué proveedor de IA se está usando
                        ai_provider = base_config.ai_provider

                        if ai_provider == "ollama":
                            # Configurar nodo para Ollama
                            if "url" in node["parameters"]:
                                if node_purpose == "embedding":
                                    node["parameters"]["url"] = (
                                        f"{ai_params.get('host', 'http://ollama:11434')}/api/embeddings"
                                    )
                                else:  # qa
                                    node["parameters"]["url"] = (
                                        f"{ai_params.get('host', 'http://ollama:11434')}/api/chat"
                                    )

                            if "body" in node["parameters"]:
                                body = json.loads(node["parameters"]["body"])
                                if node_purpose == "embedding":
                                    body["model"] = ai_params.get(
                                        "embedding_model", "nomic-embed-text"
                                    )
                                else:  # qa
                                    body["model"] = ai_params.get("qa_model", "llama3")
                                node["parameters"]["body"] = json.dumps(body)

                        elif ai_provider == "gemini":
                            # Configurar nodo para Gemini
                            if "url" in node["parameters"]:
                                if node_purpose == "embedding":
                                    node["parameters"]["url"] = (
                                        "https://generativelanguage.googleapis.com/v1/models/embedding-001:embedContent"
                                    )
                                else:  # qa
                                    model = ai_params.get(
                                        "qa_model", "gemini-1.5-flash"
                                    )
                                    node["parameters"]["url"] = (
                                        f"https://generativelanguage.googleapis.com/v1/models/{model}:generateContent"
                                    )

                            # Añadir API key a los parámetros
                            if "headers" in node["parameters"]:
                                headers = json.loads(node["parameters"]["headers"])
                                headers["x-goog-api-key"] = ai_params.get("api_key", "")
                                node["parameters"]["headers"] = json.dumps(headers)
                            else:
                                node["parameters"]["headers"] = json.dumps(
                                    {"x-goog-api-key": ai_params.get("api_key", "")}
                                )

            # TODO: Implementar la operación real de crear/actualizar el workflow en N8N
            # Queda como trabajo futuro. Por ahora, devolver una URL de webhook simulada

            if self.webhook_url:
                return f"{self.webhook_url}/{workflow_name}"
            else:
                return None

        except Exception as e:
            logger.error(f"Error al personalizar el workflow: {e}")
            return None
