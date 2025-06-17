"""Cliente simplificado para N8N."""

from typing import Optional, Dict, Any
import httpx
from loguru import logger

from ..config.settings import Settings, get_settings


class N8NAPIError(Exception):
    """Error de la API de N8N."""
    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code


class N8NClient:
    """Cliente simplificado para N8N."""
    
    def __init__(self, settings: Settings):
        self.base_url = settings.n8n.url.rstrip('/')
        self.token = settings.n8n.token
        self.client = httpx.Client(
            timeout=30.0,
            headers={"X-N8N-API-KEY": self.token}
        )
        logger.info(f"N8NClient inicializado para {self.base_url}")
    
    def _make_request(self, method: str, endpoint: str, data: Optional[Dict] = None) -> Any:
        """Realiza una petición a la API de N8N."""
        url = f"{self.base_url}/api/v1/{endpoint.lstrip('/')}"
        
        try:
            if method.upper() == "GET":
                response = self.client.get(url)
            elif method.upper() == "POST":
                response = self.client.post(url, json=data)
            elif method.upper() == "PUT":
                response = self.client.put(url, json=data)
            elif method.upper() == "DELETE":
                response = self.client.delete(url)
            else:
                raise N8NAPIError(f"Método HTTP no soportado: {method}")
            
            response.raise_for_status()
            
            if response.content:
                return response.json()
            return None
            
        except httpx.HTTPStatusError as e:
            raise N8NAPIError(f"Error HTTP: {e.response.status_code}", e.response.status_code)
        except httpx.RequestError as e:
            raise N8NAPIError(f"Error de conexión: {str(e)}")
    
    def create_workflow(self, name: str, course_id: int) -> Optional[str]:
        """Crea un workflow básico de chat para un curso."""
        try:
            # Workflow simplificado - template básico
            workflow_data = {
                "name": name,
                "active": True,
                "nodes": [
                    {
                        "name": "Webhook",
                        "type": "n8n-nodes-base.webhook",
                        "typeVersion": 1,
                        "position": [250, 300],
                        "parameters": {
                            "httpMethod": "POST",
                            "path": f"chat-curso-{course_id}",
                            "responseMode": "responseNode",
                            "options": {}
                        }
                    },
                    {
                        "name": "Respond to Webhook",
                        "type": "n8n-nodes-base.respondToWebhook",
                        "typeVersion": 1,
                        "position": [650, 300],
                        "parameters": {
                            "respondWith": "json",
                            "responseBody": "={{ { \"response\": \"Hola! Soy el asistente del curso. Esta es una respuesta básica.\" } }}"
                        }
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
            
            result = self._make_request("POST", "workflows", workflow_data)
            
            if result and "id" in result:
                workflow_id = result["id"]
                logger.info(f"Workflow creado con ID: {workflow_id}")
                
                # Activar el workflow
                self._make_request("POST", f"workflows/{workflow_id}/activate")
                
                return workflow_id
            
            return None
            
        except Exception as e:
            logger.error(f"Error creando workflow para curso {course_id}: {e}")
            return None
    
    def get_webhook_url(self, course_id: int) -> Optional[str]:
        """Obtiene la URL del webhook para un curso."""
        try:
            # Buscar workflows activos que contengan el course_id en el nombre
            workflows = self._make_request("GET", "workflows")
            
            if workflows and "data" in workflows:
                for workflow in workflows["data"]:
                    if f"curso-{course_id}" in workflow.get("name", "").lower():
                        # Construir URL del webhook
                        webhook_path = f"chat-curso-{course_id}"
                        webhook_url = f"{self.base_url}/webhook/{webhook_path}"
                        return webhook_url
            
            return None
            
        except Exception as e:
            logger.error(f"Error obteniendo webhook URL para curso {course_id}: {e}")
            return None
    
    def delete_workflow(self, workflow_name: str) -> bool:
        """Elimina un workflow por nombre."""
        try:
            # Buscar el workflow por nombre
            workflows = self._make_request("GET", "workflows")
            
            if workflows and "data" in workflows:
                for workflow in workflows["data"]:
                    if workflow.get("name") == workflow_name:
                        workflow_id = workflow["id"]
                        self._make_request("DELETE", f"workflows/{workflow_id}")
                        logger.info(f"Workflow {workflow_name} eliminado")
                        return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error eliminando workflow {workflow_name}: {e}")
            return False
    
    def update_workflow_config(self, course_id: int, vector_table: str, ai_config: Dict[str, Any]) -> bool:
        """Actualiza la configuración de un workflow existente."""
        try:
            # TODO: Implementar actualización de configuración del workflow
            # Esta función permite modificar el workflow para usar la tabla de vectores
            # y configuración de IA específica
            logger.warning("update_workflow_config no implementado completamente")
            return True
        except Exception as e:
            logger.error(f"Error actualizando configuración del workflow para curso {course_id}: {e}")
            return False
    
    def close(self):
        """Cierra el cliente HTTP."""
        self.client.close()


def get_n8n_client(settings: Settings = None) -> N8NClient:
    """Dependency para obtener el cliente de N8N."""
    if settings is None:
        settings = get_settings()
    return N8NClient(settings)
