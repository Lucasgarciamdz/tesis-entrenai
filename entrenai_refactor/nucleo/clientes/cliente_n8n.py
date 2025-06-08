import json
from pathlib import Path
from typing import List, Optional, Dict, Any
from urllib.parse import urljoin
import uuid

import requests

from entrenai_refactor.api import modelos as modelos_api
from entrenai_refactor.config.configuracion import configuracion_global
from entrenai_refactor.config.registrador import obtener_registrador

registrador = obtener_registrador(__name__)

class ErrorClienteN8N(Exception):
    """Excepción personalizada para errores del ClienteN8N."""

    def __init__(
        self,
        mensaje: str,
        codigo_estado: Optional[int] = None,
        datos_respuesta: Optional[Any] = None,
    ):
        super().__init__(mensaje)
        self.codigo_estado = codigo_estado
        self.datos_respuesta = datos_respuesta

    def __str__(self):
        return f"{super().__str__()} (Código de Estado: {self.codigo_estado}, Respuesta: {self.datos_respuesta})"

class ClienteN8N:
    def __init__(self, sesion: Optional[requests.Session] = None):
        self.config_n8n = configuracion_global.n8n
        self.url_base = self.config_n8n.url
        self.sesion = sesion or requests.Session()

        if self.config_n8n.clave_api:
            self.sesion.headers.update({"X-N8N-API-KEY": self.config_n8n.clave_api})

        if not self.url_base:
            registrador.error("URL de N8N no configurada. ClienteN8N no será funcional.")
        else:
            if not self.url_base.endswith(("/api/v1", "/api/v1/")):
                self.url_base = urljoin(self.url_base, "api/v1/")
            else:
                if not self.url_base.endswith("/"):
                    self.url_base += "/"
            registrador.info(f"ClienteN8N inicializado para URL: {self.url_base}")

    def _realizar_peticion(
        self,
        metodo: str,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        datos_json: Optional[Dict[str, Any]] = None,
    ) -> Any:
        if not self.url_base:
            raise ErrorClienteN8N("ClienteN8N no configurado con URL base.")

        url_completa = urljoin(self.url_base, endpoint)
        respuesta: Optional[requests.Response] = None
        try:
            if metodo.upper() == "GET":
                respuesta = self.sesion.get(url_completa, params=params, timeout=10)
            elif metodo.upper() == "POST":
                respuesta = self.sesion.post(url_completa, params=params, json=datos_json, timeout=15)
            elif metodo.upper() == "PUT":
                respuesta = self.sesion.put(url_completa, params=params, json=datos_json, timeout=15)
            elif metodo.upper() == "PATCH": # Añadido PATCH para activar/desactivar workflows
                respuesta = self.sesion.patch(url_completa, json=datos_json, timeout=10)
            else:
                raise ErrorClienteN8N(f"Método HTTP no soportado: {metodo}")

            respuesta.raise_for_status()
            if respuesta.status_code == 204: # No Content
                return None
            return respuesta.json()
        except requests.exceptions.HTTPError as error_http:
            texto_resp = respuesta.text if respuesta is not None else "Sin respuesta"
            codigo_stat = respuesta.status_code if respuesta is not None else None
            registrador.error(f"Error HTTP llamando a N8N {endpoint}: {error_http} - Respuesta: {texto_resp}")
            raise ErrorClienteN8N(str(error_http), codigo_estado=codigo_stat, datos_respuesta=texto_resp) from error_http
        except requests.exceptions.RequestException as error_req:
            registrador.error(f"Excepción de petición para N8N {endpoint}: {error_req}")
            raise ErrorClienteN8N(str(error_req)) from error_req
        except ValueError as error_json:  # JSONDecodeError
            texto_resp = respuesta.text if respuesta is not None else "Sin respuesta"
            registrador.error(f"Error decodificación JSON para N8N {endpoint}: {error_json} - Respuesta: {texto_resp}")
            raise ErrorClienteN8N(f"Falló la decodificación de respuesta JSON: {error_json}", datos_respuesta=texto_resp) from error_json

    def obtener_lista_flujos_trabajo(self, limite: Optional[int] = None, etiquetas: Optional[str] = None) -> List[modelos_api.FlujoTrabajoN8N]:
        params_api: Dict[str, Any] = {}
        if limite is not None:
            params_api["limit"] = limite
        if etiquetas is not None:
            params_api["tags"] = etiquetas
        try:
            datos_respuesta = self._realizar_peticion("GET", "workflows", params=params_api)
            flujos_brutos = []
            if isinstance(datos_respuesta, dict) and "data" in datos_respuesta and isinstance(datos_respuesta["data"], list):
                flujos_brutos = datos_respuesta["data"]
            elif isinstance(datos_respuesta, list): # Algunas versiones de N8N pueden devolver una lista directamente
                flujos_brutos = datos_respuesta
            else:
                raise ErrorClienteN8N("Lista de flujos de trabajo no está en el formato esperado.", datos_respuesta=datos_respuesta)
            return [modelos_api.FlujoTrabajoN8N(**datos_flujo) for datos_flujo in flujos_brutos]
        except ErrorClienteN8N as e:
            registrador.error(f"Falló la obtención de lista de flujos de N8N: {e}")
            raise
        except Exception as e_parse:
            registrador.exception(f"Error inesperado parseando lista de flujos N8N: {e_parse}")
            raise ErrorClienteN8N(f"Error inesperado parseando flujos N8N: {e_parse}")

    def obtener_detalles_flujo_trabajo(self, id_flujo: str) -> Optional[modelos_api.FlujoTrabajoN8N]:
        try:
            datos_flujo = self._realizar_peticion("GET", f"workflows/{id_flujo}")
            if isinstance(datos_flujo, dict) and "data" in datos_flujo: # Estructura común {data: {...}}
                return modelos_api.FlujoTrabajoN8N(**datos_flujo["data"])
            elif isinstance(datos_flujo, dict) and "id" in datos_flujo: # A veces devuelve el objeto directamente
                return modelos_api.FlujoTrabajoN8N(**datos_flujo)
            return None
        except ErrorClienteN8N as e:
            if e.codigo_estado == 404:
                return None
            registrador.error(f"Falló la obtención de detalles para flujo '{id_flujo}': {e}")
            raise
        except Exception as e_gen:
            registrador.exception(f"Error inesperado obteniendo detalles de flujo N8N para '{id_flujo}': {e_gen}")
            raise ErrorClienteN8N(f"Error inesperado obteniendo detalles de flujo N8N: {e_gen}")

    def importar_flujo_trabajo(self, contenido_json_flujo: Dict[str, Any]) -> Optional[modelos_api.FlujoTrabajoN8N]:
        try:
            nombre_flujo = contenido_json_flujo.get('name', 'Flujo Importado')
            registrador.info(f"Importando flujo '{nombre_flujo}' a N8N.")

            datos_flujo_para_api = {
                "name": nombre_flujo,
                "nodes": contenido_json_flujo.get("nodes", []),
                "connections": contenido_json_flujo.get("connections", {}),
                "settings": contenido_json_flujo.get("settings", {}),
            }
            if "staticData" in contenido_json_flujo:
                datos_flujo_para_api["staticData"] = contenido_json_flujo["staticData"]

            datos_flujo_importado = self._realizar_peticion("POST", "workflows", datos_json=datos_flujo_para_api)

            if isinstance(datos_flujo_importado, dict) and "id" in datos_flujo_importado:
                registrador.info(f"Flujo importado/actualizado exitosamente. ID: {datos_flujo_importado['id']}")
                return modelos_api.FlujoTrabajoN8N(**datos_flujo_importado)
            else: # Manejar caso donde 'data' podría envolver el resultado
                if isinstance(datos_flujo_importado, dict) and "data" in datos_flujo_importado and isinstance(datos_flujo_importado["data"], dict) and "id" in datos_flujo_importado["data"]:
                    registrador.info(f"Flujo importado/actualizado exitosamente. ID: {datos_flujo_importado['data']['id']}")
                    return modelos_api.FlujoTrabajoN8N(**datos_flujo_importado["data"])
                registrador.error(f"Estructura de respuesta inesperada tras importar flujo: {datos_flujo_importado}")
                return None
        except ErrorClienteN8N as e:
            registrador.error(f"Falló la importación de flujo a N8N: {e}")
            return None
        except Exception as e_gen:
            registrador.exception(f"Error inesperado durante importación de flujo N8N: {e_gen}")
            return None

    def activar_flujo_trabajo(self, id_flujo: str) -> bool:
        try:
            # El endpoint es /workflows/{id}/activate, método POST
            self._realizar_peticion("POST", f"workflows/{id_flujo}/activate")
            registrador.info(f"Flujo de trabajo {id_flujo} activado exitosamente.")
            return True
        except ErrorClienteN8N as e:
            registrador.error(f"Error activando flujo {id_flujo}: {e}")
            return False

    def desactivar_flujo_trabajo(self, id_flujo: str) -> bool:
        try:
            # El endpoint es /workflows/{id}/deactivate, método POST
            self._realizar_peticion("POST", f"workflows/{id_flujo}/deactivate")
            registrador.info(f"Flujo de trabajo {id_flujo} desactivado exitosamente.")
            return True
        except ErrorClienteN8N as e:
            registrador.error(f"Error desactivando flujo {id_flujo}: {e}")
            return False

    def _obtener_url_webhook_desde_json_flujo(self, json_flujo: Dict[str, Any], id_webhook_generado: str) -> Optional[str]:
        """Construye la URL del webhook usando el webhookId del nodo chatTrigger y la URL base de N8N."""
        # El id_webhook_generado es el que se puso en el nodo chatTrigger antes de importar.
        if id_webhook_generado and self.config_n8n.url_webhook: # url_webhook es la base para webhooks (ej: http://localhost:5678)
            return urljoin(self.config_n8n.url_webhook, f"webhook/{id_webhook_generado}/chat")
        elif id_webhook_generado and self.config_n8n.url: # Fallback a la URL base de N8N
             url_base_n8n = self.config_n8n.url
             if "/api/v1" in url_base_n8n: # Quitar /api/v1/ si está
                 url_base_n8n = url_base_n8n.split("/api/v1")[0]
             return urljoin(url_base_n8n, f"webhook/{id_webhook_generado}/chat")
        registrador.warning(f"No se pudo construir URL de webhook. id_webhook_generado: {id_webhook_generado}, config url_webhook: {self.config_n8n.url_webhook}")
        return None

    def configurar_y_desplegar_flujo_chat(
        self,
        id_curso: int,
        nombre_curso: str,
        nombre_coleccion_pgvector: str,
        # params_config_ia: Dict[str, Any], # Unificar esto
        proveedor_ia_seleccionado: str, # 'ollama' o 'gemini'
        config_ollama: Optional[configuracion_global.ollama] = None, # Acceder via configuracion_global
        config_gemini: Optional[configuracion_global.gemini] = None, # Acceder via configuracion_global
        mensajes_iniciales: Optional[str] = None,
        mensaje_sistema_agente: Optional[str] = None, # Para el systemMessage del nodo Agent
        placeholder_entrada: Optional[str] = None,
        titulo_chat: Optional[str] = None,
    ) -> Optional[str]:
        registrador.info(f"Configurando y desplegando flujo de chat N8N para id_curso: {id_curso}")

        # Cargar plantilla de flujo
        ruta_plantilla = Path(configuracion_global.n8n.ruta_json_flujo)
        if not ruta_plantilla.is_file():
            registrador.error(f"Archivo de plantilla de flujo N8N no encontrado en: {ruta_plantilla}")
            return None
        try:
            with open(ruta_plantilla, "r", encoding="utf-8") as f:
                json_flujo = json.load(f)
        except Exception as e:
            registrador.error(f"Falló la lectura o parseo de JSON de flujo N8N desde {ruta_plantilla}: {e}")
            return None

        # Modificar nombre del flujo
        json_flujo["name"] = f"Entrenai - {id_curso} - {nombre_curso}"

        id_webhook_generado = str(uuid.uuid4())
        nodo_chat_trigger_actualizado = False
        nodo_agente_actualizado = False
        nodo_vector_store_actualizado = False
        nodos_ia_actualizados = 0


        for nodo in json_flujo.get("nodes", []):
            # Nodo Chat Trigger
            if nodo.get("type") == "@n8n/n8n-nodes-langchain.chatTrigger":
                nodo["webhookId"] = id_webhook_generado
                if "parameters" not in nodo: nodo["parameters"] = {}
                if "options" not in nodo["parameters"]: nodo["parameters"]["options"] = {}
                if mensajes_iniciales:
                    nodo["parameters"]["initialMessages"] = mensajes_iniciales
                if placeholder_entrada:
                    nodo["parameters"]["options"]["inputPlaceholder"] = placeholder_entrada
                if titulo_chat:
                    nodo["parameters"]["options"]["title"] = titulo_chat
                nodo_chat_trigger_actualizado = True

            # Nodo AI Agent
            elif nodo.get("type") == "@n8n/n8n-nodes-langchain.agent":
                if "parameters" not in nodo: nodo["parameters"] = {}
                if "options" not in nodo["parameters"]: nodo["parameters"]["options"] = {}
                if mensaje_sistema_agente: # Añadir al existente o crear
                    mensaje_base = nodo["parameters"]["options"].get("systemMessage", "")
                    nodo["parameters"]["options"]["systemMessage"] = f"{mensaje_base}\n\n{mensaje_sistema_agente}".strip()
                nodo_agente_actualizado = True

            # Nodo Vector Store (PGVector)
            elif nodo.get("type") == "@n8n/n8n-nodes-langchain.vectorStorePGVector":
                if "parameters" not in nodo: nodo["parameters"] = {}
                nodo["parameters"]["tableName"] = nombre_coleccion_pgvector
                nodo_vector_store_actualizado = True

            # Nodos de IA y Embeddings
            elif "lmChat" in nodo.get("type", "") or "embeddings" in nodo.get("type", ""):
                if proveedor_ia_seleccionado == "gemini" and config_gemini:
                    if "lmChatGoogleGemini" in nodo.get("type", ""):
                        nodo["type"] = "@n8n/n8n-nodes-langchain.lmChatGoogleGemini"
                        if "parameters" not in nodo: nodo["parameters"] = {}
                        nodo["parameters"]["modelName"] = config_gemini.modelo_texto # o modelo_qa
                        # Asegurar que las credenciales son correctas para Gemini
                        nodos_ia_actualizados +=1
                    elif "embeddingsGoogleGemini" in nodo.get("type", ""):
                        nodo["type"] = "@n8n/n8n-nodes-langchain.embeddingsGoogleGemini"
                        if "parameters" not in nodo: nodo["parameters"] = {}
                        nodo["parameters"]["modelName"] = config_gemini.modelo_embedding
                        nodos_ia_actualizados +=1
                elif proveedor_ia_seleccionado == "ollama" and config_ollama:
                    if "lmChat" in nodo.get("type", ""): # Cambiar a Ollama si era Gemini o ya es Ollama
                        nodo["type"] = "@n8n/n8n-nodes-langchain.lmChatOllama"
                        if "parameters" not in nodo: nodo["parameters"] = {}
                        nodo["parameters"]["model"] = config_ollama.modelo_qa # o modelo_contexto, modelo_markdown
                        nodo["parameters"]["baseUrl"] = config_ollama.host
                        # Limpiar credenciales de Gemini si existían
                        if "credentials" in nodo and "googlePalmApi" in nodo["credentials"]:
                            del nodo["credentials"]["googlePalmApi"]
                        elif "credentials" in nodo and "googleVertexAi" in nodo["credentials"]: # Otra posible credencial Gemini
                            del nodo["credentials"]["googleVertexAi"]
                        nodos_ia_actualizados +=1
                    elif "embeddings" in nodo.get("type", ""): # Cambiar a Ollama
                        nodo["type"] = "@n8n/n8n-nodes-langchain.embeddingsOllama"
                        if "parameters" not in nodo: nodo["parameters"] = {}
                        nodo["parameters"]["model"] = config_ollama.modelo_embedding
                        nodo["parameters"]["baseUrl"] = config_ollama.host
                        if "credentials" in nodo and "googlePalmApi" in nodo["credentials"]:
                            del nodo["credentials"]["googlePalmApi"]
                        elif "credentials" in nodo and "googleVertexAi" in nodo["credentials"]:
                             del nodo["credentials"]["googleVertexAi"]
                        nodos_ia_actualizados +=1

        registrador.info(f"Actualizaciones JSON: Trigger={nodo_chat_trigger_actualizado}, Agente={nodo_agente_actualizado}, VectorStore={nodo_vector_store_actualizado}, NodosIA={nodos_ia_actualizados}")

        flujo_importado = self.importar_flujo_trabajo(json_flujo)
        if not flujo_importado or not flujo_importado.id:
            registrador.error("Falló la importación del flujo N8N modificado.")
            return None

        if not flujo_importado.active:
            registrador.info(f"Flujo '{flujo_importado.name}' (ID: {flujo_importado.id}) no está activo. Intentando activar.")
            if not self.activar_flujo_trabajo(flujo_importado.id):
                registrador.error(f"Falló la activación del flujo ID: {flujo_importado.id}")
                # No necesariamente devolver None, podría estar activo pero la API fallar.
                # El webhook podría funcionar igualmente si ya estaba activo o se activa manualmente.
        else:
            registrador.info(f"Flujo '{flujo_importado.name}' (ID: {flujo_importado.id}) ya está activo o fue activado.")

        url_webhook = self._obtener_url_webhook_desde_json_flujo(json_flujo, id_webhook_generado)
        if url_webhook:
            registrador.info(f"Flujo de chat desplegado. URL Webhook: {url_webhook}")
            return url_webhook
        else:
            registrador.error(f"No se pudo determinar la URL del webhook para el flujo '{flujo_importado.name}'. Verifique el nodo chatTrigger en la plantilla JSON y la configuración de N8N_WEBHOOK_URL.")
            return self.config_n8n.url_webhook # Devolver la URL base como último recurso (puede no funcionar)

[end of entrenai_refactor/nucleo/clientes/cliente_n8n.py]
