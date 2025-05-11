import requests
from typing import List, Optional, Dict, Any
from urllib.parse import urljoin

from src.entrenai.config import N8NConfig
from src.entrenai.core.models import N8NWorkflow  # Assuming this model exists
from src.entrenai.utils.logger import get_logger

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
    """
    Client for interacting with the N8N API.
    """

    def __init__(self, config: N8NConfig, session: Optional[requests.Session] = None):
        self.config = config
        self.base_url = (
            config.url
        )  # N8N API base URL (e.g., http://localhost:5678/api/v1)
        self.session = session or requests.Session()

        if self.config.api_key:
            self.session.headers.update({"X-N8N-API-KEY": self.config.api_key})

        if not self.base_url:
            logger.error("N8N URL not configured. N8NClient will not be functional.")
            # Or raise ValueError("N8N URL must be configured")
        else:
            # Ensure base_url ends with /api/v1 if not already present
            if not self.base_url.endswith(("/api/v1", "/api/v1/")):
                self.base_url = urljoin(self.base_url, "api/v1/")
            else:  # Ensure it ends with a slash
                if not self.base_url.endswith("/"):
                    self.base_url += "/"
            logger.info(f"N8NClient initialized for URL: {self.base_url}")
            try:
                # Attempt a simple health check or status check if available
                # For example, listing workflows (often requires auth)
                self.get_workflows_list(limit=1)
                logger.info(f"N8NClient connection to {self.base_url} seems OK.")
            except N8NClientError as e:
                logger.warning(
                    f"N8NClient initial check failed for {self.base_url}: {e}. This might be due to auth or endpoint not found."
                )
            except Exception as e:
                logger.warning(
                    f"N8NClient initial check failed for {self.base_url} with an unexpected error: {e}"
                )

    def _make_request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        json_data: Optional[Dict[str, Any]] = None,
    ) -> Any:
        """
        Helper method to make requests to the N8N API.
        """
        if not self.base_url:
            logger.error(
                "N8NClient is not configured with a base URL. Cannot make request."
            )
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
            # Add other methods (DELETE, etc.) if needed
            else:
                raise N8NClientError(f"Unsupported HTTP method: {method}")

            response.raise_for_status()  # Raises HTTPError for bad responses (4XX or 5XX)

            # N8N API might return empty body for 204 No Content, handle this
            if response.status_code == 204:
                return None

            data = response.json()
            return data
        except requests.exceptions.HTTPError as http_err:
            err_msg = f"HTTP error occurred while calling N8N endpoint '{endpoint}': {http_err}"
            resp_text = (
                response.text if response is not None else "No response text available"
            )
            status = response.status_code if response is not None else None
            logger.error(f"{err_msg} - Response: {resp_text}")
            raise N8NClientError(
                message=str(http_err), status_code=status, response_data=resp_text
            ) from http_err
        except requests.exceptions.RequestException as req_err:
            logger.error(
                f"Request exception occurred while calling N8N endpoint '{endpoint}': {req_err}"
            )
            raise N8NClientError(message=str(req_err)) from req_err
        except ValueError as json_err:  # Includes JSONDecodeError
            err_msg = f"JSON decode error for N8N endpoint '{endpoint}': {json_err}"
            resp_text = (
                response.text if response is not None else "No response text available"
            )
            logger.error(f"{err_msg} - Response: {resp_text}")
            raise N8NClientError(
                message=f"Failed to decode JSON response: {json_err}",
                response_data=resp_text,
            ) from json_err

    def get_workflows_list(
        self, limit: Optional[int] = None, tags: Optional[str] = None
    ) -> List[N8NWorkflow]:
        """
        Retrieves a list of workflows from N8N.
        API endpoint: GET /workflows
        """
        params = {}
        if limit is not None:
            params["limit"] = limit
        if tags is not None:
            params["tags"] = tags  # Comma-separated string of tags

        try:
            response_data = self._make_request("GET", "workflows", params=params)
            # N8N API for workflows usually returns a dict with a 'data' key containing the list
            if (
                isinstance(response_data, dict)
                and "data" in response_data
                and isinstance(response_data["data"], list)
            ):
                workflows_raw = response_data["data"]
            elif isinstance(
                response_data, list
            ):  # Some endpoints might return a list directly
                workflows_raw = response_data
            else:
                logger.error(
                    f"Unexpected response structure for get_workflows_list: {response_data}"
                )
                raise N8NClientError(
                    "Workflow list data is not in expected format.",
                    response_data=response_data,
                )

            workflows = [N8NWorkflow(**wf_data) for wf_data in workflows_raw]
            logger.info(f"Retrieved {len(workflows)} workflows from N8N.")
            return workflows
        except N8NClientError as e:
            logger.error(f"Failed to get workflows list from N8N: {e}")
            raise
        except Exception as e:
            logger.exception(f"An unexpected error occurred in get_workflows_list: {e}")
            raise N8NClientError(f"Unexpected error fetching N8N workflows: {e}")

    def get_workflow_details(self, workflow_id: str) -> Optional[N8NWorkflow]:
        """
        Retrieves details for a specific workflow.
        API endpoint: GET /workflows/{workflow_id}
        """
        try:
            workflow_data = self._make_request("GET", f"workflows/{workflow_id}")
            # N8N API for single workflow usually returns a dict with a 'data' key
            if isinstance(workflow_data, dict) and "data" in workflow_data:
                return N8NWorkflow(**workflow_data["data"])
            elif (
                isinstance(workflow_data, dict) and "id" in workflow_data
            ):  # If 'data' key is not present but 'id' is
                return N8NWorkflow(**workflow_data)
            else:
                logger.error(
                    f"Unexpected response structure for get_workflow_details (id: {workflow_id}): {workflow_data}"
                )
                return None  # Or raise error
        except N8NClientError as e:
            if e.status_code == 404:
                logger.warning(f"Workflow with ID '{workflow_id}' not found in N8N.")
                return None
            logger.error(f"Failed to get details for workflow '{workflow_id}': {e}")
            raise
        except Exception as e:
            logger.exception(
                f"An unexpected error occurred in get_workflow_details for workflow '{workflow_id}': {e}"
            )
            raise N8NClientError(f"Unexpected error fetching N8N workflow details: {e}")

    # --- Placeholder methods for Fase 2.1 requirements ---
    # The actual implementation of these can be complex and depends heavily on N8N's API capabilities
    # for dynamic workflow management and parameterization.

    def configure_and_deploy_chat_workflow(
        self,
        course_id: int,
        qdrant_collection_name: str,
        ollama_config: Dict[str, Any],  # e.g. host, models
        # Potentially a template workflow ID or definition
    ) -> Optional[str]:  # Returns the chat webhook URL or None
        """
        Configures and deploys/activates a chat workflow for a given course.
        This is a complex operation and might involve:
        1. Finding a template workflow.
        2. Updating its nodes/parameters (e.g., Qdrant collection, Ollama models).
        3. Activating the workflow.
        4. Retrieving its webhook URL.

        For now, this is a placeholder. A simpler approach might be to assume a workflow
        is manually created and tagged, and this function just retrieves its details (like webhook URL)
        based on `self.config.chat_workflow_id` or tags.
        """
        logger.info(
            f"Attempting to configure/deploy N8N chat workflow for course_id: {course_id}"
        )

        # Simplistic approach: Use a pre-configured workflow ID from .env
        if self.config.chat_workflow_id:
            logger.info(
                f"Using pre-configured N8N_CHAT_WORKFLOW_ID: {self.config.chat_workflow_id}"
            )
            workflow_details = self.get_workflow_details(self.config.chat_workflow_id)
            if workflow_details and workflow_details.active:
                # How to get the specific webhook URL for *this* chat instance?
                # N8N webhook URLs are typically static per trigger node.
                # If the workflow is designed to handle multiple courses, it needs a way to
                # differentiate them, e.g., by a path parameter in the webhook or a query param.
                # The N8N_WEBHOOK_URL in config might be the base, and we append course_id.
                # This needs to align with the N8N workflow's Webhook node setup.
                if (
                    self.config.webhook_url
                ):  # This is the N8N instance's general webhook URL
                    # Assume the workflow's trigger webhook URL is the main N8N webhook URL + /workflow-path/course_id
                    # This is highly dependent on N8N workflow design.
                    # For a generic chat, it might be just the workflow's trigger URL.
                    # Let's assume the workflow_details.webhook_url is the direct trigger URL if available.
                    if workflow_details.webhook_url:
                        logger.info(
                            f"Chat workflow '{workflow_details.name}' is active. Webhook URL: {workflow_details.webhook_url}"
                        )
                        return str(workflow_details.webhook_url)
                    else:  # Fallback if model doesn't have webhook_url, construct one (less reliable)
                        # This part is speculative and depends on N8N setup.
                        # Often, the webhook URL is the N8N instance URL + /webhook/ + workflow_id or a custom path.
                        # For a production workflow, the URL is usually static.
                        # The N8N_WEBHOOK_URL from config is the base URL for N8N's webhooks.
                        # The actual path is defined in the N8N webhook node.
                        # If the workflow is meant to be a single endpoint, its URL is static.
                        # If it's a template to be copied, then it's more complex.
                        # For now, let's assume the N8N_WEBHOOK_URL in config is the one to use,
                        # or a specific one for the chat workflow.
                        # This part needs clarification based on N8N setup.
                        logger.warning(
                            f"Webhook URL not directly available in N8NWorkflow model for workflow {self.config.chat_workflow_id}. "
                            f"Using N8N_WEBHOOK_URL from config: {self.config.webhook_url} as a base. "
                            f"This might need adjustment based on actual N8N workflow trigger URL."
                        )
                        return self.config.webhook_url  # This might be too generic.
                else:
                    logger.error(
                        f"N8N_WEBHOOK_URL not configured, cannot determine chat URL for workflow {self.config.chat_workflow_id}"
                    )
                    return None
            elif workflow_details:
                logger.warning(
                    f"Chat workflow '{workflow_details.name}' (ID: {self.config.chat_workflow_id}) found but is not active."
                )
                return None
            else:
                logger.error(
                    f"Pre-configured chat workflow with ID '{self.config.chat_workflow_id}' not found."
                )
                return None
        else:
            logger.warning(
                "N8N_CHAT_WORKFLOW_ID not set in config. Cannot automatically configure chat workflow."
            )
            # Here, one might implement logic to find/create a workflow based on tags or a template.
            # For Phase 2.1, this is out of scope.
            return None


if __name__ == "__main__":
    from src.entrenai.config import n8n_config

    if not n8n_config.url:
        print("N8N_URL must be set in .env for this test.")
    else:
        print(
            f"Attempting to connect to N8N at {n8n_config.url} (API base: {N8NClient(config=n8n_config).base_url})..."
        )
        # Note: The N8NClient constructor itself might try to make a call if not handled carefully.
        try:
            n8n_client = N8NClient(config=n8n_config)
            if n8n_client.base_url:  # Check if client initialized properly
                print("N8N client initialized.")

                # Test get_workflows_list
                print("\nAttempting to get list of workflows (limit 5)...")
                try:
                    workflows = n8n_client.get_workflows_list(limit=5)
                    if workflows:
                        print(f"Successfully retrieved {len(workflows)} workflows:")
                        for wf in workflows:
                            print(
                                f"  - ID: {wf.id}, Name: {wf.name}, Active: {wf.active}, Webhook: {wf.webhook_url}"
                            )
                            # Try to get details for the first one if ID is present
                            if wf.id:
                                print(
                                    f"    Attempting to get details for workflow ID: {wf.id}"
                                )
                                details = n8n_client.get_workflow_details(wf.id)
                                if details:
                                    print(
                                        f"      Details: Name: {details.name}, Active: {details.active}"
                                    )
                                else:
                                    print(
                                        f"      Could not get details for workflow ID: {wf.id}"
                                    )
                                break  # Only test one detail call
                    else:
                        print("No workflows found or an error occurred.")
                except N8NClientError as e:
                    print(f"N8N API Error during get_workflows_list test: {e}")
                except Exception as e:
                    print(f"Unexpected error during get_workflows_list test: {e}")

                # Test configure_and_deploy_chat_workflow (using placeholder logic)
                print(
                    "\nAttempting to 'configure/deploy' chat workflow (using placeholder logic)..."
                )
                if n8n_config.chat_workflow_id:
                    chat_url = n8n_client.configure_and_deploy_chat_workflow(
                        course_id=123,
                        qdrant_collection_name="entrenai_course_123",
                        ollama_config={
                            "host": "http://ollama:11434",
                            "model": "llama3",
                        },
                    )
                    if chat_url:
                        print(f"Placeholder chat URL obtained: {chat_url}")
                    else:
                        print("Could not obtain placeholder chat URL.")
                else:
                    print(
                        "N8N_CHAT_WORKFLOW_ID not set in .env, skipping configure_and_deploy_chat_workflow test."
                    )

            else:
                print("Failed to initialize N8N client (base_url is None). Check logs.")
        except N8NClientError as e:
            print(f"N8NClientError during initialization or test: {e}")
        except Exception as e:
            print(f"An unexpected error occurred during N8NClient test: {e}")
