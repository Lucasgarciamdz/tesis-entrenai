import json
from pathlib import Path
from typing import Dict, Optional

from src.entrenai.config.logger import get_logger
from src.entrenai.core.clients.n8n_client import N8NClient
from src.entrenai.config import base_config

logger = get_logger(__name__)


class N8NWorkflowService:
    """Servicio para manejo de workflows de N8N."""
    
    def __init__(self, n8n_client: N8NClient):
        self.n8n = n8n_client
    
    def configure_and_deploy_workflow(
        self,
        course_id: int,
        course_name: str,
        pgvector_table_name: str,
        ai_config_params: Dict,
        initial_messages: Optional[str] = None,
        system_message: Optional[str] = None,
        input_placeholder: Optional[str] = None,
        chat_title: Optional[str] = None,
    ) -> Optional[str]:
        """
        Configura y despliega el workflow de N8N.
        Retorna la URL del chat o None si falla.
        """
        logger.info(f"Configurando workflow N8N para curso '{course_name}' (ID: {course_id})")
        
        # Cargar plantilla apropiada
        workflow_data = self._load_workflow_template()
        if not workflow_data:
            return None
        
        # Modificar tabla de Pgvector
        if not self._update_pgvector_table_name(workflow_data, pgvector_table_name):
            logger.warning("No se pudo actualizar el nombre de tabla en el workflow")
        
        # Desplegar workflow
        return self.n8n.configure_and_deploy_chat_workflow(
            course_id=course_id,
            course_name=course_name,
            qdrant_collection_name=pgvector_table_name,
            ai_config_params=ai_config_params,
            initial_messages=initial_messages,
            system_message=system_message,
            input_placeholder=input_placeholder,
            chat_title=chat_title,
        )
    
    def delete_workflow_for_course(self, course_id: int, course_name: str) -> bool:
        """Identifica y elimina el workflow existente para un curso."""
        workflow_name_prefix = f"Entrenai - {course_id}"
        exact_workflow_name = f"{workflow_name_prefix} - {course_name}"
        
        all_workflows = self.n8n.get_workflows_list()
        existing_workflow_id = None
        
        # Buscar por nombre exacto primero
        for wf in all_workflows:
            if wf.name == exact_workflow_name and wf.active:
                existing_workflow_id = wf.id
                break
        
        # Buscar por prefijo si no hay coincidencia exacta
        if not existing_workflow_id:
            for wf in all_workflows:
                if wf.name and wf.name.startswith(workflow_name_prefix) and wf.active:
                    existing_workflow_id = wf.id
                    break
        
        if existing_workflow_id:
            logger.info(f"Eliminando workflow existente ID: {existing_workflow_id}")
            return self.n8n.delete_workflow(existing_workflow_id)
        
        logger.info("No se encontró workflow existente para eliminar")
        return True
    
    def _load_workflow_template(self) -> Optional[Dict]:
        """Carga la plantilla de workflow apropiada según el proveedor de IA."""
        template_name = "gemini_workflow.json" if base_config.ai_provider == "gemini" else "ollama_workflow.json"
        template_path = Path("src/entrenai/core/templates/n8n_workflows") / template_name
        
        logger.info(f"Cargando plantilla de workflow: {template_path}")
        
        if not template_path.exists():
            logger.error(f"No se encontró la plantilla del workflow: {template_path}")
            return None
        
        try:
            with open(template_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, Exception) as e:
            logger.error(f"Error al cargar la plantilla del workflow: {e}")
            return None
    
    def _update_pgvector_table_name(self, workflow_data: Dict, table_name: str) -> bool:
        """Actualiza el nombre de tabla de Pgvector en el workflow."""
        for node in workflow_data.get("nodes", []):
            if (node.get("type") == "@n8n/n8n-nodes-langchain.vectorStorePGVector" and 
                node.get("parameters", {}).get("mode") == "retrieve-as-tool"):
                
                original_table_name = node["parameters"].get("tableName")
                node["parameters"]["tableName"] = table_name
                logger.info(f"Tabla actualizada de '{original_table_name}' a '{table_name}'")
                return True
        
        logger.warning("No se encontró el nodo PGVector en la plantilla")
        return False
