import requests
import json # For loading workflow JSON
from pathlib import Path # For workflow_json_path
from typing import List, Optional, Dict, Any
from urllib.parse import urljoin

from src.entrenai.config import N8NConfig, OllamaConfig # OllamaConfig for type hint
from src.entrenai.core.models import N8NWorkflow
from src.entrenai.utils.logger import get_logger

logger = get_logger(__name__)

class N8NClientError(Exception):
    """Custom exception for N8NClient errors."""
    def __init__(self, message: str, status_code: Optional[int] = None, response_data: Optional[Any] = None):
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

    def _make_request(self, method: str, endpoint: str, params: Optional[Dict[str, Any]] = None, json_data: Optional[Dict[str, Any]] = None) -> Any:
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
            if response.status_code == 204: return None
            return response.json()
        except requests.exceptions.HTTPError as http_err:
            resp_text = response.text if response is not None else "No response"
            status = response.status_code if response is not None else None
            logger.error(f"HTTP error calling N8N {endpoint}: {http_err} - Response: {resp_text}")
            raise N8NClientError(str(http_err), status_code=status, response_data=resp_text) from http_err
        except requests.exceptions.RequestException as req_err:
            logger.error(f"Request exception for N8N {endpoint}: {req_err}")
            raise N8NClientError(str(req_err)) from req_err
        except ValueError as json_err: # JSONDecodeError
            resp_text = response.text if response is not None else "No response"
            logger.error(f"JSON decode error for N8N {endpoint}: {json_err} - Response: {resp_text}")
            raise N8NClientError(f"Failed to decode JSON response: {json_err}", response_data=resp_text) from json_err

    def get_workflows_list(self, limit: Optional[int] = None, tags: Optional[str] = None) -> List[N8NWorkflow]:
        params = {}
        if limit is not None: params['limit'] = limit
        if tags is not None: params['tags'] = tags
        try:
            response_data = self._make_request("GET", "workflows", params=params)
            if isinstance(response_data, dict) and "data" in response_data and isinstance(response_data["data"], list):
                workflows_raw = response_data["data"]
            elif isinstance(response_data, list):
                 workflows_raw = response_data
            else:
                raise N8NClientError("Workflow list data not in expected format.", response_data=response_data)
            return [N8NWorkflow(**wf_data) for wf_data in workflows_raw]
        except N8NClientError as e:
            logger.error(f"Failed to get workflows list from N8N: {e}")
            raise
        except Exception as e: # Catch any other parsing error for N8NWorkflow
            logger.exception(f"Unexpected error parsing N8N workflows list: {e}")
            raise N8NClientError(f"Unexpected error parsing N8N workflows: {e}")


    def get_workflow_details(self, workflow_id: str) -> Optional[N8NWorkflow]:
        try:
            workflow_data = self._make_request("GET", f"workflows/{workflow_id}")
            if isinstance(workflow_data, dict) and "data" in workflow_data:
                 return N8NWorkflow(**workflow_data["data"])
            elif isinstance(workflow_data, dict) and "id" in workflow_data:
                 return N8NWorkflow(**workflow_data)
            return None
        except N8NClientError as e:
            if e.status_code == 404: return None
            logger.error(f"Failed to get details for workflow '{workflow_id}': {e}")
            raise
        except Exception as e:
            logger.exception(f"Unexpected error fetching N8N workflow details for '{workflow_id}': {e}")
            raise N8NClientError(f"Unexpected error fetching N8N workflow details: {e}")

    def import_workflow(self, workflow_json_content: Dict[str, Any]) -> Optional[N8NWorkflow]:
        """Imports a workflow from a JSON content. If a workflow with the same name exists, it might be updated."""
        try:
            # N8N's import endpoint is typically POST /workflows (same as create)
            # It might update if a workflow with the same ID exists in the JSON, or by name.
            # For safety, let's assume it creates or updates based on N8N's internal logic.
            # The provided JSON has an "id", N8N might use this to update if it exists.
            logger.info(f"Importing workflow '{workflow_json_content.get('name', 'Unknown name')}' to N8N.")
            imported_workflow_data = self._make_request("POST", "workflows", json_data=workflow_json_content)
            
            # The response structure for workflow creation/import can vary.
            # It often returns the full workflow object.
            if isinstance(imported_workflow_data, dict) and "id" in imported_workflow_data:
                logger.info(f"Workflow imported/updated successfully. ID: {imported_workflow_data['id']}")
                return N8NWorkflow(**imported_workflow_data)
            else:
                logger.error(f"Unexpected response structure after importing workflow: {imported_workflow_data}")
                return None
        except N8NClientError as e:
            logger.error(f"Failed to import workflow into N8N: {e}")
            return None
        except Exception as e:
            logger.exception(f"Unexpected error during N8N workflow import: {e}")
            return None

    def activate_workflow(self, workflow_id: str) -> bool:
        """Activates a workflow by its ID."""
        try:
            self._make_request("POST", f"workflows/{workflow_id}/activate")
            logger.info(f"Successfully activated workflow ID: {workflow_id}")
            return True
        except N8NClientError as e:
            logger.error(f"Failed to activate workflow ID {workflow_id}: {e}")
            return False
        except Exception as e:
            logger.exception(f"Unexpected error activating N8N workflow ID {workflow_id}: {e}")
            return False

    def _get_webhook_url_from_workflow_json(self, workflow_json: Dict[str, Any]) -> Optional[str]:
        """Helper to extract webhookId from the chatTrigger node in the workflow JSON."""
        nodes = workflow_json.get("nodes", [])
        for node in nodes:
            if node.get("type") == "@n8n/n8n-nodes-langchain.chatTrigger":
                webhook_id = node.get("webhookId")
                if webhook_id and self.config.url: # self.config.url is the N8N instance base URL
                    # Construct the full webhook URL
                    # N8N instance URL might be http://localhost:5678
                    # Webhook URL is typically N8N_URL/webhook/webhookId or N8N_URL/webhook-test/webhookId
                    # For production webhooks, it's usually /webhook/
                    # This needs to be confirmed with N8N documentation or testing.
                    # Assuming self.config.webhook_url is the base for webhooks (e.g. http://localhost:5678)
                    if self.config.webhook_url:
                        return urljoin(self.config.webhook_url, f"webhook/{webhook_id}")
                    else: # Fallback to base N8N URL if specific webhook_url is not set
                        return urljoin(self.config.url, f"webhook/{webhook_id}")
        return None

    def configure_and_deploy_chat_workflow(
        self,
        course_id: int, # For logging and potential future use in parametrization
        qdrant_collection_name: str, # For potential future use in parametrization
        ollama_config_params: Dict[str, Any], # For potential future use in parametrization
    ) -> Optional[str]:
        logger.info(f"Configuring and deploying N8N chat workflow for course_id: {course_id}")

        if not self.config.workflow_json_path:
            logger.error("N8N_WORKFLOW_JSON_PATH not configured. Cannot load workflow.")
            return None
        
        workflow_file = Path(self.config.workflow_json_path)
        if not workflow_file.is_file():
            logger.error(f"N8N workflow JSON file not found at: {workflow_file}")
            return None

        try:
            with open(workflow_file, 'r') as f:
                workflow_json_content = json.load(f)
        except Exception as e:
            logger.error(f"Failed to read or parse N8N workflow JSON from {workflow_file}: {e}")
            return None

        # TODO: Parameterize workflow_json_content here if needed (Option B)
        # For now, we assume Option A: workflow is generic or configured via N8N UI/env vars.
        # Example for Option B (modifying Qdrant collection name):
        # for node in workflow_json_content.get("nodes", []):
        #     if node.get("type") == "@n8n/n8n-nodes-langchain.vectorStoreQdrant":
        #         if "parameters" in node and "qdrantCollection" in node["parameters"]:
        #             node["parameters"]["qdrantCollection"]["value"] = qdrant_collection_name
        #             node["parameters"]["qdrantCollection"]["cachedResultName"] = qdrant_collection_name
        #             logger.info(f"Patched Qdrant collection in workflow JSON to: {qdrant_collection_name}")
        #             break
        
        imported_workflow = self.import_workflow(workflow_json_content)
        if not imported_workflow or not imported_workflow.id:
            logger.error("Failed to import the N8N workflow from JSON.")
            return None

        if not imported_workflow.active:
            logger.info(f"Workflow '{imported_workflow.name}' (ID: {imported_workflow.id}) is not active. Attempting to activate.")
            if not self.activate_workflow(imported_workflow.id):
                logger.error(f"Failed to activate workflow ID: {imported_workflow.id}")
                return None
        else:
            logger.info(f"Workflow '{imported_workflow.name}' (ID: {imported_workflow.id}) is already active.")

        # Extract webhookId from the original JSON to construct the URL,
        # as the imported_workflow model might not directly expose it in a simple way.
        webhook_url = self._get_webhook_url_from_workflow_json(workflow_json_content)
        
        if webhook_url:
            logger.info(f"Chat workflow deployed. Webhook URL: {webhook_url}")
            return webhook_url
        else:
            logger.error(f"Could not determine webhook URL for workflow '{imported_workflow.name}'. Check chatTrigger node in JSON.")
            # Fallback to configured N8N_WEBHOOK_URL if all else fails, though it's less specific.
            return self.config.webhook_url


if __name__ == "__main__":
    from src.entrenai.config import n8n_config, ollama_config # Added ollama_config for test

    if not n8n_config.url:
        print("N8N_URL must be set in .env for this test.")
    elif not n8n_config.workflow_json_path or not Path(n8n_config.workflow_json_path).is_file():
        print(f"N8N_WORKFLOW_JSON_PATH is not set or file not found at '{n8n_config.workflow_json_path}'.")
    else:
        print(f"Attempting to connect to N8N at {n8n_config.url} (API base: {N8NClient(config=n8n_config).base_url})...")
        try:
            n8n_client = N8NClient(config=n8n_config)
            if n8n_client.base_url:
                print("N8N client initialized.")

                # Test configure_and_deploy_chat_workflow
                print("\nAttempting to configure and deploy chat workflow from JSON...")
                # Dummy OllamaConfig for the test call signature
                dummy_ollama_cfg_params = {"host": ollama_config.host, "embedding_model": ollama_config.embedding_model, "qa_model": ollama_config.qa_model}
                chat_webhook_url = n8n_client.configure_and_deploy_chat_workflow(
                    course_id=999, 
                    qdrant_collection_name="entrenai_course_999_test",
                    ollama_config_params=dummy_ollama_cfg_params
                )
                if chat_webhook_url:
                    print(f"Chat workflow deployed/checked. Webhook URL: {chat_webhook_url}")
                else:
                    print("Failed to configure/deploy chat workflow or get webhook URL.")
            else:
                print("Failed to initialize N8N client (base_url is None). Check logs.")
        except N8NClientError as e:
            print(f"N8NClientError during initialization or test: {e}")
        except Exception as e:
            print(f"An unexpected error occurred during N8NClient test: {e}")
