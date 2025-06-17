import json
from pathlib import Path
from typing import Optional, Dict, Any
from urllib.parse import urljoin
import uuid
import requests
from loguru import logger


class N8NClientError(Exception):
    """Excepción para errores del cliente N8N."""
    
    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code


class N8NClient:
    """Cliente simplificado para N8N."""
    
    def __init__(self, url: str, api_key: str):
        self.base_url = urljoin(url.rstrip('/') + '/', "api/v1/")
        self.api_key = api_key
        self.session = requests.Session()
        self.session.headers.update({"X-N8N-API-KEY": api_key})
        logger.info(f"N8NClient inicializado para: {url}")
    
    def _make_request(self, method: str, endpoint: str, json_data: Optional[Dict[str, Any]] = None) -> Any:
        """Realiza una petición a la API de N8N."""
        url = urljoin(self.base_url, endpoint)
        
        try:
            if method.upper() == "GET":
                response = self.session.get(url)
            elif method.upper() == "POST":
                response = self.session.post(url, json=json_data)
            elif method.upper() == "PUT":
                response = self.session.put(url, json=json_data)
            else:
                raise N8NClientError(f"Método HTTP no soportado: {method}")
            
            response.raise_for_status()
            
            if response.status_code == 204:
                return None
            return response.json()
            
        except requests.RequestException as e:
            raise N8NClientError(f"Error de conexión: {str(e)}")
        except json.JSONDecodeError as e:
            raise N8NClientError(f"Error decodificando respuesta JSON: {str(e)}")
    
    def get_workflows_list(self) -> list:
        """Obtiene la lista de workflows."""
        return self._make_request("GET", "workflows")
    
    def import_workflow(self, workflow_data: Dict[str, Any]) -> Dict[str, Any]:
        """Importa un workflow a N8N."""
        return self._make_request("POST", "workflows", json_data=workflow_data)
    
    def activate_workflow(self, workflow_id: str) -> None:
        """Activa un workflow."""
        self._make_request("PUT", f"workflows/{workflow_id}/activate")
        logger.info(f"Workflow {workflow_id} activado")
    
    def configure_and_deploy_chat_workflow(
        self, 
        course_id: int, 
        table_name: str, 
        initial_messages: str = "",
        workflow_json_path: Optional[str] = None
    ) -> str:
        """
        Configura y despliega el workflow de chat para un curso.
        
        Args:
            course_id: ID del curso
            table_name: Nombre de la tabla de vectores
            initial_messages: Mensajes iniciales del chat
            workflow_json_path: Ruta al archivo JSON del workflow
            
        Returns:
            URL del webhook del chat configurado
        """
        # Cargar el template base del workflow
        if workflow_json_path and Path(workflow_json_path).exists():
            with open(workflow_json_path, 'r', encoding='utf-8') as f:
                workflow_template = json.load(f)
        else:
            # Template básico si no existe archivo
            workflow_template = self._get_basic_chat_workflow_template()
        
        # Configurar el workflow con los datos del curso
        workflow_name = f"Chat_Curso_{course_id}"
        workflow_id = str(uuid.uuid4())
        
        # Personalizar el workflow
        workflow_data = {
            "name": workflow_name,
            "nodes": workflow_template.get("nodes", []),
            "connections": workflow_template.get("connections", {}),
            "active": False,  # Se activará después
            "settings": {
                "executionOrder": "v1"
            }
        }
        
        # Configurar nodos específicos del curso
        for node in workflow_data["nodes"]:
            if node.get("type") == "n8n-nodes-base.webhook":
                # Configurar webhook
                node["webhookId"] = workflow_id
                node["parameters"]["path"] = f"chat-curso-{course_id}"
            elif "pgvector" in node.get("type", "").lower():
                # Configurar conexión a base de datos
                if "parameters" not in node:
                    node["parameters"] = {}
                node["parameters"]["table"] = table_name
            elif "messages" in node.get("name", "").lower():
                # Configurar mensajes iniciales
                if "parameters" not in node:
                    node["parameters"] = {}
                node["parameters"]["initialMessages"] = initial_messages
        
        try:
            # Importar el workflow
            imported_workflow = self.import_workflow(workflow_data)
            workflow_id = imported_workflow.get("id")
            
            if not workflow_id:
                raise N8NClientError("No se pudo obtener el ID del workflow importado")
            
            # Activar el workflow
            self.activate_workflow(workflow_id)
            
            # Construir la URL del webhook
            webhook_url = f"{self.base_url.replace('/api/v1/', '')}/webhook/chat-curso-{course_id}"
            
            logger.info(f"Workflow de chat configurado para curso {course_id}: {webhook_url}")
            return webhook_url
            
        except Exception as e:
            logger.error(f"Error configurando workflow para curso {course_id}: {e}")
            raise N8NClientError(f"Error configurando workflow: {str(e)}")
    
    def _get_basic_chat_workflow_template(self) -> Dict[str, Any]:
        """Retorna un template básico de workflow de chat."""
        return {
            "nodes": [
                {
                    "parameters": {
                        "path": "chat",
                        "httpMethod": "POST",
                        "responseMode": "responseNode"
                    },
                    "id": str(uuid.uuid4()),
                    "name": "Webhook",
                    "type": "n8n-nodes-base.webhook",
                    "typeVersion": 1,
                    "position": [240, 300]
                },
                {
                    "parameters": {
                        "respondWith": "text",
                        "responseBody": "¡Hola! Soy el asistente del curso."
                    },
                    "id": str(uuid.uuid4()),
                    "name": "Respond to Webhook",
                    "type": "n8n-nodes-base.respondToWebhook",
                    "typeVersion": 1,
                    "position": [640, 300]
                }
            ],
            "connections": {
                "Webhook": {
                    "main": [
                        [
                            {
                                "node": "Respond to Webhook",
                                "type": "main",
                                "index": 0
                            }
                        ]
                    ]
                }
            }
        }


def get_n8n_client() -> N8NClient:
    """Función dependency para FastAPI."""
    from entrenai.config.settings import settings
    return N8NClient(url=settings.n8n_url, api_key=settings.n8n_api_key)
