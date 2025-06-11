import json  # For loading workflow JSON
from pathlib import Path  # For workflow_json_path
from typing import List, Optional, Dict, Any
from urllib.parse import urljoin
import uuid # Importar uuid para generar IDs aleatorios

import requests

from src.entrenai.api.models import N8NWorkflow
from src.entrenai.config import N8NConfig
from src.entrenai.config.logger import get_logger

logger = get_logger(__name__)


class N8NClientError(Exception):
    """Custom exception for N8NClient errors."""

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
        return f"{super().__str__()} (Status Code: {self.status_code}, Response: {self.response_data})"


class N8NClient:
    def __init__(self, config: N8NConfig, session: Optional[requests.Session] = None):
        self.config = config
        self.base_url = config.url
        self.session = session or requests.Session()

        if self.config.api_key:
            self.session.headers.update({"X-N8N-API-KEY": self.config.api_key})

        if not self.base_url:
            logger.error("N8N URL not configured. N8NClient will not be functional.")
        else:
            if not self.base_url.endswith(("/api/v1", "/api/v1/")):
                self.base_url = urljoin(self.base_url, "api/v1/")
            else:
                if not self.base_url.endswith("/"):
                    self.base_url += "/"
            logger.info(f"N8NClient initialized for URL: {self.base_url}")
            # Initial check removed to avoid errors if N8N is not fully up or auth fails silently here.
            # Methods will handle connection errors.

    def _make_request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        json_data: Optional[Dict[str, Any]] = None,
    ) -> Any:
        if not self.base_url:
            raise N8NClientError("N8NClient not configured with base URL.")
        url = urljoin(self.base_url, endpoint)
        response: Optional[requests.Response] = None
        try:
            if method.upper() == "GET":
                response = self.session.get(url, params=params)
            elif method.upper() == "POST":
                response = self.session.post(url, params=params, json=json_data)
            elif method.upper() == "PUT":
                response = self.session.put(url, params=params, json=json_data)
            else:
                raise N8NClientError(f"Unsupported HTTP method: {method}")
            response.raise_for_status()
            if response.status_code == 204:
                return None
            return response.json()
        except requests.exceptions.HTTPError as http_err:
            resp_text = response.text if response is not None else "No response"
            status = response.status_code if response is not None else None
            logger.error(
                f"HTTP error calling N8N {endpoint}: {http_err} - Response: {resp_text}"
            )
            raise N8NClientError(
                str(http_err), status_code=status, response_data=resp_text
            ) from http_err
        except requests.exceptions.RequestException as req_err:
            logger.error(f"Request exception for N8N {endpoint}: {req_err}")
            raise N8NClientError(str(req_err)) from req_err
        except ValueError as json_err:  # JSONDecodeError
            resp_text = response.text if response is not None else "No response"
            logger.error(
                f"JSON decode error for N8N {endpoint}: {json_err} - Response: {resp_text}"
            )
            raise N8NClientError(
                f"Failed to decode JSON response: {json_err}", response_data=resp_text
            ) from json_err

    def get_workflows_list(
        self, limit: Optional[int] = None, tags: Optional[str] = None
    ) -> List[N8NWorkflow]:
        params: Dict[str, Any] = {}  # Explicitly type params as Dict[str, Any]
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
                    "Workflow list data not in expected format.",
                    response_data=response_data,
                )
            return [N8NWorkflow(**wf_data) for wf_data in workflows_raw]
        except N8NClientError as n8n_error:
            logger.error(f"Failed to get workflows list from N8N: {n8n_error}")
            raise
        except (
            Exception
        ) as parsing_error:  # Catch any other parsing error for N8NWorkflow
            logger.exception(
                f"Unexpected error parsing N8N workflows list: {parsing_error}"
            )
            raise N8NClientError(
                f"Unexpected error parsing N8N workflows: {parsing_error}"
            )

    def get_workflow_details(self, workflow_id: str) -> Optional[N8NWorkflow]:
        try:
            workflow_data = self._make_request("GET", f"workflows/{workflow_id}")
            if isinstance(workflow_data, dict) and "data" in workflow_data:
                return N8NWorkflow(**workflow_data["data"])
            elif isinstance(workflow_data, dict) and "id" in workflow_data:
                return N8NWorkflow(**workflow_data)
            return None
        except N8NClientError as n8n_error:
            if n8n_error.status_code == 404:
                return None
            logger.error(
                f"Failed to get details for workflow '{workflow_id}': {n8n_error}"
            )
            raise
        except Exception as general_error:
            logger.exception(
                f"Unexpected error fetching N8N workflow details for '{workflow_id}': {general_error}"
            )
            raise N8NClientError(
                f"Unexpected error fetching N8N workflow details: {general_error}"
            )

    def import_workflow(
        self, workflow_json_content: Dict[str, Any]
    ) -> Optional[N8NWorkflow]:
        """Imports a workflow from a JSON content. If a workflow with the same name exists, it might be updated."""
        try:
            logger.info(
                f"Importing workflow '{workflow_json_content.get('name', 'Unknown name')}' to N8N."
            )

            # Create a clean workflow JSON with only the required properties
            # Based on n8n API documentation
            workflow_data = {
                "name": workflow_json_content.get("name", "Imported Workflow"),
                "nodes": workflow_json_content.get("nodes", []),
                "connections": workflow_json_content.get("connections", {}),
                "settings": workflow_json_content.get("settings", {}),
                # "tags" field is read-only according to N8N API, removing it
            }

            # Add staticData if it exists in the original JSON
            if "staticData" in workflow_json_content:
                workflow_data["staticData"] = workflow_json_content["staticData"]

            imported_workflow_data = self._make_request(
                "POST", "workflows", json_data=workflow_data
            )

            # The response structure for workflow creation/import can vary.
            # It often returns the full workflow object.
            if (
                isinstance(imported_workflow_data, dict)
                and "id" in imported_workflow_data
            ):
                logger.info(
                    f"Workflow imported/updated successfully. ID: {imported_workflow_data['id']}"
                )
                return N8NWorkflow(**imported_workflow_data)
            else:
                logger.error(
                    f"Unexpected response structure after importing workflow: {imported_workflow_data}"
                )
                return None
        except N8NClientError as n8n_error:
            logger.error(f"Failed to import workflow into N8N: {n8n_error}")
            return None
        except Exception as general_error:
            logger.exception(
                f"Unexpected error during N8N workflow import: {general_error}"
            )
            return None

    def activate_workflow(self, workflow_id: str) -> bool:
        """Activates a workflow by its ID."""
        try:
            self._make_request("POST", f"workflows/{workflow_id}/activate")
            logger.info(f"Successfully activated workflow ID: {workflow_id}")
            return True
        except N8NClientError as n8n_error:
            logger.error(f"Failed to activate workflow ID {workflow_id}: {n8n_error}")
            return False
        except Exception as general_error:
            logger.exception(
                f"Unexpected error activating N8N workflow ID {workflow_id}: {general_error}"
            )
            return False

    def delete_workflow(self, workflow_id: str) -> bool:
        """Deletes a workflow by its ID."""
        try:
            logger.info(f"Attempting to delete N8N workflow with ID: {workflow_id}")
            self._make_request("DELETE", f"workflows/{workflow_id}")
            logger.info(f"Successfully deleted N8N workflow with ID: {workflow_id}")
            return True
        except N8NClientError as n8n_error:
            logger.error(f"Failed to delete N8N workflow '{workflow_id}': {n8n_error}")
            return False
        except Exception as general_error:
            logger.exception(
                f"Unexpected error deleting N8N workflow '{workflow_id}': {general_error}"
            )
            return False

    def update_workflow(
        self, workflow_id: str, workflow_data: Dict[str, Any]
    ) -> Optional[N8NWorkflow]:
        """
        Actualiza un workflow existente en N8N.
        
        Args:
            workflow_id: ID del workflow a actualizar
            workflow_data: Datos completos del workflow (debe incluir toda la estructura)
            
        Returns:
            N8NWorkflow actualizado o None si falló
        """
        try:
            logger.info(f"Updating N8N workflow with ID: {workflow_id}")
            
            # Preparar datos del workflow para la actualización
            # Según la API de N8N, necesitamos enviar la estructura completa
            clean_workflow_data = {
                "name": workflow_data.get("name", "Updated Workflow"),
                "nodes": workflow_data.get("nodes", []),
                "connections": workflow_data.get("connections", {}),
                "settings": workflow_data.get("settings", {}),
            }
            # Agregar campos opcionales si existen
            if "staticData" in workflow_data:
                clean_workflow_data["staticData"] = workflow_data["staticData"]
            # Nunca enviar 'active' (es read-only y la API lo rechaza)
            # if "active" in workflow_data:
            #     clean_workflow_data["active"] = workflow_data["active"]
            # Si hay otros campos prohibidos, también los eliminamos aquí
            # (por ahora, solo 'active' es problemático según la doc y la comunidad)
            updated_workflow_data = self._make_request(
                "PUT", f"workflows/{workflow_id}", json_data=clean_workflow_data
            )
            
            if isinstance(updated_workflow_data, dict) and "id" in updated_workflow_data:
                logger.info(f"Successfully updated workflow with ID: {workflow_id}")
                return N8NWorkflow(**updated_workflow_data)
            else:
                logger.error(
                    f"Unexpected response structure after updating workflow {workflow_id}: {updated_workflow_data}"
                )
                return None
                
        except N8NClientError as n8n_error:
            logger.error(f"Failed to update N8N workflow '{workflow_id}': {n8n_error}")
            return None
        except Exception as general_error:
            logger.exception(
                f"Unexpected error updating N8N workflow '{workflow_id}': {general_error}"
            )
            return None

    def _get_webhook_url_from_workflow_json(
        self, workflow_json: Dict[str, Any]
    ) -> Optional[str]:
        """Helper to extract webhookId from the chatTrigger node in the workflow JSON."""
        nodes = workflow_json.get("nodes", [])
        for node in nodes:
            if node.get("type") == "@n8n/n8n-nodes-langchain.chatTrigger":
                webhook_id = node.get("webhookId")
                if (
                    webhook_id and self.config.url
                ):  # self.config.url is the N8N instance base URL
                    # Construct the full webhook URL
                    # N8N instance URL might be http://localhost:5678
                    # Webhook URL is typically N8N_URL/webhook/webhookId or N8N_URL/webhook-test/webhookId
                    # For production webhooks, it's usually /webhook/
                    # This needs to be confirmed with N8N documentation or testing.
                    # Assuming self.config.webhook_url is the base for webhooks (e.g. http://localhost:5678)
                    if self.config.webhook_url:
                        return urljoin(self.config.webhook_url, f"webhook/{webhook_id}/chat")
                    else:  # Fallback to base N8N URL if specific webhook_url is not set
                        return urljoin(self.config.url, f"webhook/{webhook_id}/chat")
        return None

    def get_workflow_webhooks(
        self, workflow_id: str
    ) -> Optional[List[Dict[str, Any]]]:
        """Get all webhook URLs for a workflow directly from the N8N API."""
        try:
            # Get the full workflow JSON content
            workflow_json_content = self._make_request("GET", f"workflows/{workflow_id}")

            if not workflow_json_content:
                logger.warning(f"No workflow JSON content found for ID: {workflow_id}")
                return None

            webhook_nodes = []
            nodes_list = workflow_json_content.get("nodes", [])
            for node in nodes_list:
                # Check for webhook nodes
                if (
                    node.get("type", "").endswith("Trigger")
                    or "webhook" in node.get("type", "").lower()
                ):
                    webhook_data = {
                        "nodeId": node.get("id", None),
                        "name": node.get("name", None),
                        "webhookId": node.get("webhookId", None),
                        "type": node.get("type", None),
                    }
                    webhook_nodes.append(webhook_data)

            if webhook_nodes:
                logger.info(
                    f"Found {len(webhook_nodes)} webhook nodes in workflow {workflow_id}"
                )
                return webhook_nodes

            # If no webhooks found, return None
            logger.warning(f"No webhook nodes found in workflow {workflow_id}")
            return None

        except N8NClientError as n8n_error:
            logger.error(
                f"Failed to get webhooks for workflow ID {workflow_id}: {n8n_error}"
            )
            return None
        except Exception as general_error:
            logger.exception(
                f"Unexpected error getting webhooks for workflow ID {workflow_id}: {general_error}"
            )
            return None

    def get_webhook_url_for_workflow(self, workflow_id: str) -> Optional[str]:
        """Try different methods to get the webhook URL for a workflow."""
        # Método 1: Intentar obtener webhooks de los detalles del workflow
        webhooks = self.get_workflow_webhooks(workflow_id)
        if webhooks:
            for webhook in webhooks:
                # Buscar webhooks con un ID
                webhook_id = webhook.get("webhookId")
                if webhook_id:
                    # Construir la URL del webhook
                    if self.config.webhook_url:
                        webhook_url = urljoin(
                            self.config.webhook_url, f"webhook/{webhook_id}/chat"
                        )
                        logger.info(f"Found webhook URL using node ID: {webhook_url}")
                        return webhook_url
                    elif self.config.url:
                        # Extraer la base URL (sin /api/v1/)
                        base_url = self.config.url
                        if "/api/v1" in base_url:
                            base_url = base_url.split("/api/v1")[0]
                        webhook_url = urljoin(base_url, f"webhook/{webhook_id}/chat")
                        logger.info(f"Found webhook URL using node ID: {webhook_url}")
                        return webhook_url

        # Método 2: Intentar usar la configuración por defecto con la plantilla de workflow
        if self.config.workflow_json_path:
            try:
                with open(Path(self.config.workflow_json_path), "r") as f:
                    template_json = json.load(f)
                    # Buscar nodos de tipo webhook o trigger
                    for node in template_json.get("nodes", []):
                        # Verificar si es un nodo de webhook
                        if (
                            node.get("type", "").endswith("Trigger")
                            or "webhook" in node.get("type", "").lower()
                        ):
                            webhook_id = node.get("webhookId")
                            if webhook_id:
                                if self.config.webhook_url:
                                    webhook_url = urljoin(
                                        self.config.webhook_url, f"webhook/{webhook_id}/chat"
                                    )
                                    logger.info(
                                        f"Generated webhook URL from template: {webhook_url}"
                                    )
                                    return webhook_url
                                elif self.config.url:
                                    # Extraer la base URL (sin /api/v1/)
                                    base_url = self.config.url
                                    if "/api/v1" in base_url:
                                        base_url = base_url.split("/api/v1")[0]
                                    webhook_url = urljoin(
                                        base_url, f"webhook/{webhook_id}/chat"
                                    )
                                    logger.info(
                                        f"Generated webhook URL from template: {webhook_url}"
                                    )
                                    return webhook_url
            except Exception as template_error:
                logger.error(
                    f"Error attempting to generate webhook URL from template: {template_error}"
                )

        # No se pudo obtener el webhook por ningún método
        return None

    def configure_and_deploy_chat_workflow(
        self,
        course_id: int,
        course_name: str,
        qdrant_collection_name: str,
        ai_config_params: Dict[str, Any],  # Unified AI config params
        initial_messages: Optional[str] = None,
        system_message: Optional[str] = None,
        input_placeholder: Optional[str] = None,
        chat_title: Optional[str] = None,
    ) -> Optional[str]:
        logger.info(
            f"Configuring and deploying N8N chat workflow for course_id: {course_id}"
        )

        # Buscar si ya existe un workflow para este curso
        try:
            logger.info(f"Checking for existing workflows for course {course_id}...")
            existing_workflows = self.get_workflows_list()
            if not existing_workflows:
                logger.info("No existing workflows found.")
            else:
                logger.info(f"Found {len(existing_workflows)} total workflows.")

            workflow_prefix = f"Entrenai - {course_id}"
            active_workflow = None

            # Primero buscar un workflow activo con el nombre exacto
            exact_name = f"Entrenai - {course_id} - {course_name}"
            for workflow in existing_workflows:
                if workflow.name == exact_name:
                    if workflow.active:
                        logger.info(
                            f"Found exact match active workflow: {workflow.name}"
                        )
                        webhook_url = (
                            self.get_webhook_url_for_workflow(workflow.id)
                            if workflow.id
                            else None
                        )
                        if webhook_url:
                            logger.info(
                                f"Using existing workflow. Webhook URL: {webhook_url}"
                            )
                            return webhook_url
                    active_workflow = workflow
                    break

            # Si no encontramos uno con el nombre exacto, buscar cualquier workflow activo para este curso
            if not active_workflow:
                for workflow in existing_workflows:
                    if workflow.name and workflow.name.startswith(workflow_prefix):
                        if workflow.active:
                            logger.info(
                                f"Found active workflow for course: {workflow.name}"
                            )
                            webhook_url = (
                                self.get_webhook_url_for_workflow(workflow.id)
                                if workflow.id
                                else None
                            )
                            if webhook_url:
                                logger.info(
                                    f"Using existing workflow. Webhook URL: {webhook_url}"
                                )
                                return webhook_url
                        active_workflow = workflow
                        break

            # Si encontramos un workflow pero no pudimos obtener su webhook URL, intentar activarlo
            if active_workflow and active_workflow.id:
                logger.info(
                    f"Found workflow {active_workflow.name}, attempting to activate it..."
                )
                if self.activate_workflow(active_workflow.id):
                    logger.info(
                        f"Successfully activated workflow ID: {active_workflow.id}"
                    )
                    # Intentar obtener webhook URL después de activación
                    webhook_url = self.get_webhook_url_for_workflow(active_workflow.id)
                    if webhook_url:
                        logger.info(
                            f"Successfully activated workflow. Webhook URL: {webhook_url}"
                        )
                        return webhook_url

                    # Si aún no se puede obtener el webhook después de activar, intenta leer el workflow template
                    # y extraer la estructura del nodo para generar la URL
                    if self.config.workflow_json_path:
                        try:
                            with open(Path(self.config.workflow_json_path), "r") as f:
                                template_json = json.load(f)
                                # Construir una URL basada en la plantilla y el ID del workflow
                                for node in template_json.get("nodes", []):
                                    if (
                                        node.get("type")
                                        == "@n8n/n8n-nodes-langchain.chatTrigger"
                                    ):
                                        webhook_id = node.get("webhookId")
                                        if webhook_id and self.config.webhook_url:
                                            webhook_url = urljoin(
                                                self.config.webhook_url,
                                                f"webhook/{webhook_id}",
                                            )
                                            logger.info(
                                                f"Generated webhook URL from template: {webhook_url}"
                                            )
                                            return webhook_url
                        except Exception as template_error:
                            logger.error(
                                f"Error attempting to generate webhook URL from template: {template_error}"
                            )

                # Si llegamos aquí, significa que no pudimos obtener el webhook URL del workflow existente
                logger.warning(
                    f"Could not get webhook URL from existing workflow {active_workflow.name}. Creating new one."
                )

        except Exception as workflow_check_error:
            logger.error(f"Error checking existing workflows: {workflow_check_error}")
            # Continuamos con la creación de un nuevo workflow

        if not self.config.workflow_json_path:
            logger.error("N8N_WORKFLOW_JSON_PATH not configured. Cannot load workflow.")
            return None

        workflow_file = Path(self.config.workflow_json_path)
        if not workflow_file.is_file():
            logger.error(f"N8N workflow JSON file not found at: {workflow_file}")
            return None

        try:
            with open(workflow_file, "r") as f:
                workflow_json_content = json.load(f)
        except Exception as file_error:
            logger.error(
                f"Failed to read or parse N8N workflow JSON from {workflow_file}: {file_error}"
            )
            return None

        # Modificar el contenido del JSON del workflow
        # Asegurarse de que el JSON se modifique bien y no rompa la estructura.
        # Los campos a modificar son:
        # - initialMessages: dentro de nodes[0].parameters.initialMessages
        # - inputPlaceholder: dentro de nodes[0].parameters.options.inputPlaceholder
        # - title: dentro de nodes[0].parameters.options.title
        # - systemMessage: dentro de nodes[1].parameters.options.systemMessage

        # Cargar el contenido del workflow JSON
        workflow_file = Path(self.config.workflow_json_path)
        if not workflow_file.is_file():
            logger.error(f"N8N workflow JSON file not found at: {workflow_file}")
            return None

        try:
            with open(workflow_file, "r") as f:
                workflow_json_content = json.load(f)
        except Exception as file_error:
            logger.error(
                f"Failed to read or parse N8N workflow JSON from {workflow_file}: {file_error}"
            )
            return None

        # Modificar el nombre del workflow
        workflow_json_content["name"] = f"Entrenai - {course_id} - {course_name}"

        # Modificar los parámetros del nodo 'When chat message received'
        chat_trigger_node = next(
            (
                node
                for node in workflow_json_content.get("nodes", [])
                if node.get("type") == "@n8n/n8n-nodes-langchain.chatTrigger"
            ),
            None,
        )
        if chat_trigger_node:
            # Generar un UUID aleatorio y asignarlo al webhookId
            generated_webhook_id = str(uuid.uuid4())
            chat_trigger_node["webhookId"] = generated_webhook_id
            logger.info(f"Generated and set webhookId: {generated_webhook_id}")

            if "parameters" in chat_trigger_node:
                if initial_messages is not None:
                    chat_trigger_node["parameters"]["initialMessages"] = initial_messages
                    logger.info(f"Updated initialMessages to: {initial_messages}")
                if "options" in chat_trigger_node["parameters"]:
                    if input_placeholder is not None:
                        chat_trigger_node["parameters"]["options"][
                            "inputPlaceholder"
                        ] = input_placeholder
                        logger.info(f"Updated inputPlaceholder to: {input_placeholder}")
                    if chat_title is not None:
                        chat_trigger_node["parameters"]["options"]["title"] = chat_title
                        logger.info(f"Updated chat_title to: {chat_title}")
        else:
            logger.warning(
                "Chat trigger node not found in workflow JSON. Cannot update initial messages/options or set webhookId."
            )

        # Modificar los parámetros del nodo 'AI Agent' (índice 1)
        ai_agent_node = next(
            (
                node
                for node in workflow_json_content.get("nodes", [])
                if node.get("type") == "@n8n/n8n-nodes-langchain.agent"
            ),
            None,
        )
        if ai_agent_node and "parameters" in ai_agent_node:
            if "options" in ai_agent_node["parameters"]:
                if system_message is not None:
                    ai_agent_node["parameters"]["options"]["systemMessage"] = (
                        ai_agent_node["parameters"]["options"].get("systemMessage", "")
                        + "\n"
                        + system_message
                    )
                    logger.info(f"Appended systemMessage with: {system_message}")
        else:
            logger.warning(
                "AI Agent node or its parameters not found in workflow JSON. Cannot update system message."
            )

        # Actualizar la colección de Qdrant (ahora Pgvector) y los parámetros del modelo de IA
        for node in workflow_json_content.get("nodes", []):
            if node.get("type") == "@n8n/n8n-nodes-langchain.vectorStorePGVector":
                if "parameters" in node and "tableName" in node["parameters"]:
                    node["parameters"]["tableName"] = qdrant_collection_name
                    logger.info(
                        f"Patched Pgvector table name in workflow JSON to: {qdrant_collection_name}"
                    )
            elif node.get("type") == "@n8n/n8n-nodes-langchain.lmChatGoogleGemini":
                if "parameters" in node and "modelName" in node["parameters"]:
                    if ai_config_params.get("selected_provider") == "gemini":
                        node["parameters"]["modelName"] = ai_config_params.get(
                            "qa_model"
                        )
                        logger.info(
                            f"Patched Gemini QA model in workflow JSON to: {ai_config_params.get('qa_model')}"
                        )
            elif node.get("type") == "@n8n/n8n-nodes-langchain.embeddingsGoogleGemini":
                if "parameters" in node and "modelName" in node["parameters"]:
                    if ai_config_params.get("selected_provider") == "gemini":
                        node["parameters"]["modelName"] = ai_config_params.get(
                            "embedding_model"
                        )
                        logger.info(
                            f"Patched Gemini Embedding model in workflow JSON to: {ai_config_params.get('embedding_model')}"
                        )
            # Add logic for Ollama if needed, similar to Gemini
            # For Ollama, the 'lmChatOllama' and 'embeddingsOllama' nodes would need to be targeted.
            # The current workflow JSON only has Gemini nodes.

        imported_workflow = self.import_workflow(workflow_json_content)
        if not imported_workflow or not imported_workflow.id:
            logger.error("Failed to import the N8N workflow from JSON.")
            return None

        if not imported_workflow.active:
            logger.info(
                f"Workflow '{imported_workflow.name}' (ID: {imported_workflow.id}) is not active. Attempting to activate."
            )
            if not self.activate_workflow(imported_workflow.id):
                logger.error(f"Failed to activate workflow ID: {imported_workflow.id}")
                return None
        else:
            logger.info(
                f"Workflow '{imported_workflow.name}' (ID: {imported_workflow.id}) is already active."
            )

        # Extract webhookId from the original JSON to construct the URL,
        # as the imported_workflow model might not directly expose it in a simple way.
        webhook_url = self._get_webhook_url_from_workflow_json(workflow_json_content)

        if webhook_url:
            logger.info(f"Chat workflow deployed. Webhook URL: {webhook_url}")
            return webhook_url
        else:
            logger.error(
                f"Could not determine webhook URL for workflow '{imported_workflow.name}'. Check chatTrigger node in JSON."
            )
            # Fallback to configured N8N_WEBHOOK_URL if all else fails, though it's less specific.
            return self.config.webhook_url


if __name__ == "__main__":
    from src.entrenai.config import (
        n8n_config,
        ollama_config,
    )  # Added ollama_config for test

    if not n8n_config.url:
        print("N8N_URL must be set in .env for this test.")
    elif (
        not n8n_config.workflow_json_path
        or not Path(n8n_config.workflow_json_path).is_file()
    ):
        print(
            f"N8N_WORKFLOW_JSON_PATH is not set or file not found at '{n8n_config.workflow_json_path}'."
        )
    else:
        print(
            f"Attempting to connect to N8N at {n8n_config.url} (API base: {N8NClient(config=n8n_config).base_url})..."
        )
        try:
            n8n_client = N8NClient(config=n8n_config)
            if n8n_client.base_url:
                print("N8N client initialized.")

                # Test configure_and_deploy_chat_workflow
                print("\nAttempting to configure and deploy chat workflow from JSON...")
                # Prepare AI config params for the test call
                ai_cfg_params = {
                    "selected_provider": "ollama",  # Or "gemini"
                    "ollama": {
                        "host": ollama_config.host,
                        "embedding_model": ollama_config.embedding_model,
                        "qa_model": ollama_config.qa_model,
                    },
                    # Add gemini config if needed for testing
                }
                chat_webhook_url = n8n_client.configure_and_deploy_chat_workflow(
                    course_id=999,
                    course_name="Test Course",
                    qdrant_collection_name="entrenai_course_999_test",
                    ai_config_params=ai_cfg_params,
                    initial_messages="Hola desde el test!",
                    system_message="Soy un asistente de prueba.",
                    input_placeholder="Escribe aquí...",
                    chat_title="Asistente de Prueba",
                )
                if chat_webhook_url:
                    print(
                        f"Chat workflow deployed/checked. Webhook URL: {chat_webhook_url}"
                    )
                else:
                    print(
                        "Failed to configure/deploy chat workflow or get webhook URL."
                    )
            else:
                print("Failed to initialize N8N client (base_url is None). Check logs.")
        except N8NClientError as n8n_error:
            print(f"N8NClientError during initialization or test: {n8n_error}")
        except Exception as general_error:
            print(
                f"An unexpected error occurred during N8NClient test: {general_error}"
            )
