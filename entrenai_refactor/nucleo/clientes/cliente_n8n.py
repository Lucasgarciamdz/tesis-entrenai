import json
from pathlib import Path
from typing import List, Optional, Dict, Any
from urllib.parse import urljoin
import uuid

import requests

from entrenai_refactor.api import modelos as modelos_api
from entrenai_refactor.config.configuracion import configuracion_global, _ConfiguracionOllamaAnidada, _ConfiguracionGeminiAnidada # Importar tipos de config anidados
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
        registrador.debug(f"Excepción ErrorClienteN8N creada: {mensaje}, Código: {codigo_estado}, Respuesta: {datos_respuesta}")

    def __str__(self):
        return f"{super().__str__()} (Código de Estado: {self.codigo_estado}, Respuesta: {self.datos_respuesta})"

class ClienteN8N:
    """Cliente para interactuar con la API REST de n8n."""

    def __init__(self, sesion_http: Optional[requests.Session] = None):
        self.config_n8n = configuracion_global.n8n
        self.url_base_api = None # Inicializar como None

        if not self.config_n8n.url_n8n: # CAMBIADO: url -> url_n8n
            registrador.error("URL de N8N no configurada. ClienteN8N no será funcional.")
        else:
            # Asegurar que la URL base termine con "/api/v1/"
            url_temp = self.config_n8n.url_n8n.rstrip("/") # CAMBIADO: url -> url_n8n
            if not url_temp.endswith("/api/v1"):
                self.url_base_api = url_temp + "/api/v1/"
            else:
                self.url_base_api = url_temp + "/"
            registrador.info(f"ClienteN8N inicializado para URL base API: {self.url_base_api}")

        self.sesion_http = sesion_http or requests.Session()
        if self.config_n8n.clave_api_n8n: # CAMBIADO: clave_api -> clave_api_n8n
            self.sesion_http.headers.update({"X-N8N-API-KEY": self.config_n8n.clave_api_n8n}) # CAMBIADO: clave_api -> clave_api_n8n
        else:
            registrador.warning("Clave API de N8N no configurada. Algunas operaciones podrían fallar.")


    def _realizar_peticion_api(
        self,
        metodo_http: str,
        endpoint_api: str,
        parametros_url: Optional[Dict[str, Any]] = None,
        datos_json_cuerpo: Optional[Dict[str, Any]] = None,
    ) -> Any:
        """Realiza una petición genérica a la API de N8N."""
        if not self.url_base_api:
            registrador.error("URL base API de N8N no disponible. No se puede realizar la petición.")
            raise ErrorClienteN8N("ClienteN8N no configurado con URL base API.")

        url_completa_destino = urljoin(self.url_base_api, endpoint_api)
        respuesta_http: Optional[requests.Response] = None # Para asegurar definición

        registrador.debug(f"Realizando petición {metodo_http.upper()} a N8N: {url_completa_destino}")
        try:
            if metodo_http.upper() == "GET":
                respuesta_http = self.sesion_http.get(url_completa_destino, params=parametros_url, timeout=10)
            elif metodo_http.upper() == "POST":
                respuesta_http = self.sesion_http.post(url_completa_destino, params=parametros_url, json=datos_json_cuerpo, timeout=15)
            elif metodo_http.upper() == "PUT":
                respuesta_http = self.sesion_http.put(url_completa_destino, params=parametros_url, json=datos_json_cuerpo, timeout=15)
            elif metodo_http.upper() == "PATCH":
                respuesta_http = self.sesion_http.patch(url_completa_destino, json=datos_json_cuerpo, timeout=10) # Params suelen ir en cuerpo para PATCH
            else:
                registrador.error(f"Método HTTP '{metodo_http}' no soportado por _realizar_peticion_api.")
                raise ErrorClienteN8N(f"Método HTTP no soportado: {metodo_http}")

            respuesta_http.raise_for_status() # Lanza HTTPError para respuestas 4xx/5xx

            if respuesta_http.status_code == 204: # Sin Contenido (ej. algunas operaciones PATCH o DELETE)
                registrador.debug(f"Respuesta 204 (Sin Contenido) de N8N para {endpoint_api}.")
                return None

            # Intentar decodificar JSON, podría fallar si la respuesta está vacía pero no es 204
            return respuesta_http.json()

        except requests.exceptions.HTTPError as error_http:
            texto_respuesta_error = respuesta_http.text if respuesta_http is not None else "Sin texto de respuesta."
            codigo_estado_error = respuesta_http.status_code if respuesta_http is not None else None
            registrador.error(f"Error HTTP llamando a N8N endpoint '{endpoint_api}': {error_http}. Código: {codigo_estado_error}. Respuesta: {texto_respuesta_error}")
            raise ErrorClienteN8N(f"Error HTTP de N8N: {codigo_estado_error}", codigo_estado=codigo_estado_error, datos_respuesta=texto_respuesta_error) from error_http
        except requests.exceptions.RequestException as error_peticion:
            registrador.error(f"Excepción de red/petición para N8N endpoint '{endpoint_api}': {error_peticion}")
            raise ErrorClienteN8N(f"Error de red o petición a N8N para '{endpoint_api}': {error_peticion}") from error_peticion
        except ValueError as error_json:  # JSONDecodeError
            texto_respuesta_bruta = respuesta_http.text if respuesta_http is not None else "Sin respuesta HTTP."
            registrador.error(f"Error en decodificación JSON para N8N endpoint '{endpoint_api}': {error_json}. Respuesta bruta: {texto_respuesta_bruta}")
            raise ErrorClienteN8N(f"Falló la decodificación de respuesta JSON de N8N para '{endpoint_api}'", datos_respuesta=texto_respuesta_bruta) from error_json

    def obtener_lista_de_flujos_de_trabajo(self, limite_resultados: Optional[int] = None, etiquetas_filtro: Optional[str] = None) -> List[modelos_api.FlujoTrabajoN8N]:
        """Obtiene una lista de flujos de trabajo de N8N, con opción de paginación y filtrado por etiquetas."""
        parametros_api: Dict[str, Any] = {}
        if limite_resultados is not None:
            parametros_api["limit"] = limite_resultados
        if etiquetas_filtro is not None:
            parametros_api["tags"] = etiquetas_filtro # Formato: "tag1,tag2"

        registrador.info(f"Obteniendo lista de flujos de trabajo de N8N. Límite: {limite_resultados}, Etiquetas: {etiquetas_filtro}")
        try:
            datos_respuesta_api = self._realizar_peticion_api("GET", "workflows", parametros_url=parametros_api)

            flujos_trabajo_brutos = []
            if isinstance(datos_respuesta_api, dict) and "data" in datos_respuesta_api and isinstance(datos_respuesta_api["data"], list):
                flujos_trabajo_brutos = datos_respuesta_api["data"]
            elif isinstance(datos_respuesta_api, list): # Algunas versiones/endpoints de N8N pueden devolver una lista directamente
                flujos_trabajo_brutos = datos_respuesta_api
            else:
                registrador.error(f"Respuesta inesperada al obtener flujos de N8N: {datos_respuesta_api}")
                raise ErrorClienteN8N("Lista de flujos de trabajo no está en el formato esperado.", datos_respuesta=datos_respuesta_api)

            flujos_procesados = [modelos_api.FlujoTrabajoN8N(**datos_flujo) for datos_flujo in flujos_trabajo_brutos]
            registrador.info(f"Se encontraron {len(flujos_procesados)} flujos de trabajo.")
            return flujos_procesados

        except ErrorClienteN8N as e:
            registrador.error(f"Falló la obtención de la lista de flujos de N8N: {e}")
            raise # Re-lanzar para que el llamador maneje
        except Exception as e_parse: # Errores de validación Pydantic u otros
            registrador.exception(f"Error inesperado al parsear la lista de flujos de N8N: {e_parse}")
            raise ErrorClienteN8N(f"Error inesperado al parsear flujos de N8N: {e_parse}")

    def obtener_detalles_de_flujo_de_trabajo(self, id_flujo: str) -> Optional[modelos_api.FlujoTrabajoN8N]:
        """Obtiene los detalles completos de un flujo de trabajo específico por su ID."""
        registrador.info(f"Obteniendo detalles para el flujo de trabajo ID: {id_flujo}")
        try:
            datos_flujo_api = self._realizar_peticion_api("GET", f"workflows/{id_flujo}")

            if isinstance(datos_flujo_api, dict) and "data" in datos_flujo_api and isinstance(datos_flujo_api["data"], dict): # Estructura común {data: {...}}
                flujo_procesado = modelos_api.FlujoTrabajoN8N(**datos_flujo_api["data"])
            elif isinstance(datos_flujo_api, dict) and "id" in datos_flujo_api: # A veces N8N devuelve el objeto directamente
                flujo_procesado = modelos_api.FlujoTrabajoN8N(**datos_flujo_api)
            else:
                registrador.warning(f"Respuesta inesperada para detalles del flujo {id_flujo}: {datos_flujo_api}")
                return None

            registrador.info(f"Detalles obtenidos para el flujo '{flujo_procesado.name}' (ID: {id_flujo}).")
            return flujo_procesado

        except ErrorClienteN8N as e:
            if e.codigo_estado == 404:
                registrador.warning(f"Flujo de trabajo con ID '{id_flujo}' no encontrado en N8N (404).")
                return None
            registrador.error(f"Falló la obtención de detalles para el flujo '{id_flujo}': {e}")
            raise
        except Exception as e_gen: # Errores de validación Pydantic u otros
            registrador.exception(f"Error inesperado obteniendo detalles del flujo N8N '{id_flujo}': {e_gen}")
            raise ErrorClienteN8N(f"Error inesperado obteniendo detalles del flujo N8N '{id_flujo}': {e_gen}")

    def importar_flujo_de_trabajo_desde_json(self, definicion_json_flujo: Dict[str, Any]) -> Optional[modelos_api.FlujoTrabajoN8N]:
        """Importa un nuevo flujo de trabajo a N8N usando su definición JSON."""
        nombre_flujo_intento = definicion_json_flujo.get('name', 'Flujo Importado Sin Nombre')
        registrador.info(f"Intentando importar flujo '{nombre_flujo_intento}' a N8N.")

        # N8N espera una estructura específica para la importación.
        # Aseguramos que los campos principales estén presentes.
        datos_flujo_para_api = {
            "name": nombre_flujo_intento,
            "nodes": definicion_json_flujo.get("nodes", []),
            "connections": definicion_json_flujo.get("connections", {}), # En N8N más reciente es 'connections', antes 'edges'
            "settings": definicion_json_flujo.get("settings", {}),
            "active": definicion_json_flujo.get("active", False), # Por defecto no activo
            "tags": definicion_json_flujo.get("tags", []) # Asegurar que tags sea una lista
        }
        # Campo opcional 'staticData'
        if "staticData" in definicion_json_flujo:
            datos_flujo_para_api["staticData"] = definicion_json_flujo["staticData"]

        try:
            datos_flujo_importado_api = self._realizar_peticion_api("POST", "workflows", datos_json_cuerpo=datos_flujo_para_api)

            flujo_procesado = None
            if isinstance(datos_flujo_importado_api, dict) and "id" in datos_flujo_importado_api:
                flujo_procesado = modelos_api.FlujoTrabajoN8N(**datos_flujo_importado_api)
            elif isinstance(datos_flujo_importado_api, dict) and "data" in datos_flujo_importado_api and isinstance(datos_flujo_importado_api["data"], dict) and "id" in datos_flujo_importado_api["data"]:
                flujo_procesado = modelos_api.FlujoTrabajoN8N(**datos_flujo_importado_api["data"])

            if flujo_procesado:
                registrador.info(f"Flujo '{flujo_procesado.name}' importado/actualizado exitosamente. ID: {flujo_procesado.id}")
                return flujo_procesado
            else:
                registrador.error(f"Estructura de respuesta inesperada tras importar flujo: {datos_flujo_importado_api}")
                return None
        except ErrorClienteN8N as e:
            registrador.error(f"Falló la importación del flujo '{nombre_flujo_intento}' a N8N: {e}")
            return None # Devolver None si la importación falla por error de API
        except Exception as e_gen: # Errores de validación Pydantic u otros
            registrador.exception(f"Error inesperado durante la importación del flujo N8N '{nombre_flujo_intento}': {e_gen}")
            return None


    def activar_flujo_de_trabajo(self, id_flujo: str) -> bool:
        """Activa un flujo de trabajo en N8N por su ID."""
        registrador.info(f"Intentando activar flujo de trabajo ID: {id_flujo}")
        try:
            # El endpoint es /workflows/{id}/activate, método POST, sin cuerpo.
            self._realizar_peticion_api("POST", f"workflows/{id_flujo}/activate")
            registrador.info(f"Flujo de trabajo {id_flujo} activado exitosamente.")
            return True
        except ErrorClienteN8N as e:
            registrador.error(f"Error activando el flujo de trabajo {id_flujo}: {e}")
            return False

    def desactivar_flujo_de_trabajo(self, id_flujo: str) -> bool:
        """Desactiva un flujo de trabajo en N8N por su ID."""
        registrador.info(f"Intentando desactivar flujo de trabajo ID: {id_flujo}")
        try:
            # El endpoint es /workflows/{id}/deactivate, método POST, sin cuerpo.
            self._realizar_peticion_api("POST", f"workflows/{id_flujo}/deactivate")
            registrador.info(f"Flujo de trabajo {id_flujo} desactivado exitosamente.")
            return True
        except ErrorClienteN8N as e:
            registrador.error(f"Error desactivando el flujo de trabajo {id_flujo}: {e}")
            return False

    def _construir_url_webhook(self, id_webhook_nodo: str) -> Optional[str]:
        """
        Construye la URL completa del webhook a partir del ID del webhook (path del nodo)
        y la configuración de N8N_WEBHOOK_URL o N8N_URL.
        """
        if not id_webhook_nodo:
            registrador.warning("No se proporcionó ID de webhook del nodo para construir la URL.")
            return None

        # Priorizar N8N_WEBHOOK_URL si está definida, sino usar N8N_URL (la URL base de la instancia)
        url_base_para_webhook = self.config_n8n.url_webhook_chat_n8n or self.config_n8n.url_n8n # CAMBIADO: url_webhook -> url_webhook_chat_n8n, url -> url_n8n
        if not url_base_para_webhook:
            registrador.error("No hay URL base (N8N_WEBHOOK_URL o N8N_URL) configurada para construir la URL del webhook.")
            return None

        # Limpiar la URL base de N8N si contiene /api/v1 para construir la URL del webhook correctamente
        url_base_limpia = url_base_para_webhook.split("/api/v1")[0].rstrip("/")

        # El path del webhook en N8N es típicamente /webhook/{webhookId} o /webhook-test/{webhookId}
        # Para el nodo Chatbot, el path completo suele ser /webhook/{webhookId}/chat
        url_webhook_completa = f"{url_base_limpia}/webhook/{id_webhook_nodo}/chat"
        registrador.debug(f"URL de webhook construida: {url_webhook_completa}")
        return url_webhook_completa

    def configurar_y_desplegar_flujo_de_chat_para_curso(
        self,
        id_curso: int, # Usado para nombrar el flujo y potencialmente en tags
        nombre_curso: str, # Usado para nombrar el flujo
        nombre_coleccion_pgvector: str, # Para el nodo Vector Store
        proveedor_ia_seleccionado: str, # 'ollama' o 'gemini'
        config_ollama: Optional[_ConfiguracionOllamaAnidada] = None,
        config_gemini: Optional[_ConfiguracionGeminiAnidada] = None,
        mensajes_iniciales_chat: Optional[str] = None,
        mensaje_sistema_agente_ia: Optional[str] = None,
        placeholder_entrada_chat: Optional[str] = None,
        titulo_ventana_chat: Optional[str] = None,
    ) -> Optional[str]: # Devuelve la URL del webhook si es exitoso
        """
        Configura y despliega un flujo de chat en N8N para un curso específico.
        Carga una plantilla JSON, la modifica con los parámetros proporcionados,
        la importa a N8N, la activa y devuelve la URL del webhook.
        """
        registrador.info(f"Configurando y desplegando flujo de chat N8N para curso ID: {id_curso} ({nombre_curso})")

        # Cargar la plantilla de flujo de trabajo JSON
        ruta_plantilla_flujo = Path(configuracion_global.n8n.ruta_plantilla_flujo_n8n) # CAMBIADO: ruta_json_flujo -> ruta_plantilla_flujo_n8n
        if not Path.cwd().name == "entrenai_refactor": # Si no estamos en el dir de entrenai_refactor
            # Esto es una heurística, idealmente la ruta debería ser absoluta o basada en un punto de anclaje del proyecto
            ruta_base_proyecto = Path(__file__).resolve().parent.parent.parent # Sube 3 niveles: clientes -> nucleo -> entrenai_refactor
            ruta_plantilla_flujo_abs = ruta_base_proyecto / ruta_plantilla_flujo
        else: # Si CWD es entrenai_refactor, la ruta relativa funciona
             ruta_plantilla_flujo_abs = ruta_plantilla_flujo

        if not ruta_plantilla_flujo_abs.is_file():
            registrador.error(f"Archivo de plantilla de flujo N8N no encontrado en: {ruta_plantilla_flujo_abs} (CWD: {Path.cwd()})")
            return None

        try:
            with open(ruta_plantilla_flujo_abs, "r", encoding="utf-8") as archivo_plantilla:
                json_plantilla_flujo = json.load(archivo_plantilla)
            registrador.debug(f"Plantilla de flujo N8N cargada desde: {ruta_plantilla_flujo_abs}")
        except Exception as e:
            registrador.error(f"Falló la lectura o parseo del JSON de la plantilla de flujo N8N desde {ruta_plantilla_flujo_abs}: {e}")
            return None

        # Modificar el nombre del flujo y añadir etiqueta con el ID del curso
        nombre_flujo_modificado = f"EntrenAI Chat - Curso: {nombre_curso} (ID: {id_curso})"
        json_plantilla_flujo["name"] = nombre_flujo_modificado
        if "tags" not in json_plantilla_flujo or not isinstance(json_plantilla_flujo["tags"], list):
            json_plantilla_flujo["tags"] = []
        json_plantilla_flujo["tags"].append({"name": f"curso_id:{id_curso}"}) # Añadir tag para fácil filtrado

        # Generar un ID único para el webhook de este flujo específico
        id_webhook_para_chat_trigger = str(uuid.uuid4())

        # Banderas para verificar si los nodos clave fueron actualizados
        actualizaciones_nodos = {"chat_trigger": False, "agente_ia": False, "vector_store": False, "ia_llm": 0, "ia_embeddings": 0}

        # Iterar sobre los nodos de la plantilla y actualizarlos
        for nodo_actual in json_plantilla_flujo.get("nodes", []):
            tipo_nodo = nodo_actual.get("type", "")
            parametros_nodo = nodo_actual.get("parameters", {})
            opciones_nodo = parametros_nodo.get("options", {})

            # Configurar Nodo Chat Trigger
            if tipo_nodo == "@n8n/n8n-nodes-langchain.chatTrigger":
                nodo_actual["webhookId"] = id_webhook_para_chat_trigger # Asignar el ID único
                if mensajes_iniciales_chat:
                    parametros_nodo["initialMessages"] = mensajes_iniciales_chat
                if placeholder_entrada_chat:
                    opciones_nodo["inputPlaceholder"] = placeholder_entrada_chat
                if titulo_ventana_chat:
                    opciones_nodo["title"] = titulo_ventana_chat
                actualizaciones_nodos["chat_trigger"] = True

            # Configurar Nodo AI Agent
            elif tipo_nodo == "@n8n/n8n-nodes-langchain.agent":
                if mensaje_sistema_agente_ia:
                    mensaje_base_sistema = opciones_nodo.get("systemMessage", "")
                    opciones_nodo["systemMessage"] = f"{mensaje_base_sistema}\n\n{mensaje_sistema_agente_ia}".strip()
                actualizaciones_nodos["agente_ia"] = True

            # Configurar Nodo Vector Store (PGVector)
            elif tipo_nodo == "@n8n/n8n-nodes-langchain.vectorStorePGVector":
                parametros_nodo["tableName"] = nombre_coleccion_pgvector # Nombre de la tabla/colección en PGVector
                actualizaciones_nodos["vector_store"] = True

            # Configurar Nodos de LLM y Embeddings según el proveedor de IA
            elif "lmChat" in tipo_nodo or "embeddings" in tipo_nodo:
                if proveedor_ia_seleccionado == "gemini" and config_gemini:
                    if "lmChat" in tipo_nodo : # Nodo LLM
                        nodo_actual["type"] = "@n8n/n8n-nodes-langchain.lmChatGoogleGemini"
                        parametros_nodo["modelName"] = config_gemini.modelo_texto
                        # Aquí se asumiría que las credenciales de Gemini están configuradas globalmente en N8N o se deben pasar.
                        actualizaciones_nodos["ia_llm"] += 1
                    elif "embeddings" in tipo_nodo: # Nodo Embeddings
                        nodo_actual["type"] = "@n8n/n8n-nodes-langchain.embeddingsGoogleGemini"
                        parametros_nodo["modelName"] = config_gemini.modelo_embedding
                        actualizaciones_nodos["ia_embeddings"] += 1
                elif proveedor_ia_seleccionado == "ollama" and config_ollama:
                    if "lmChat" in tipo_nodo: # Nodo LLM
                        nodo_actual["type"] = "@n8n/n8n-nodes-langchain.lmChatOllama"
                        parametros_nodo["model"] = config_ollama.modelo_qa # Usar modelo_qa para el chat principal
                        parametros_nodo["baseUrl"] = config_ollama.host
                        # Limpiar credenciales de otros proveedores si existieran
                        if "credentials" in nodo_actual and ("googlePalmApi" in nodo_actual["credentials"] or "googleVertexAi" in nodo_actual["credentials"]):
                            del nodo_actual["credentials"]
                        actualizaciones_nodos["ia_llm"] += 1
                    elif "embeddings" in tipo_nodo: # Nodo Embeddings
                        nodo_actual["type"] = "@n8n/n8n-nodes-langchain.embeddingsOllama"
                        parametros_nodo["model"] = config_ollama.modelo_embedding
                        parametros_nodo["baseUrl"] = config_ollama.host
                        if "credentials" in nodo_actual and ("googlePalmApi" in nodo_actual["credentials"] or "googleVertexAi" in nodo_actual["credentials"]):
                            del nodo_actual["credentials"]
                        actualizaciones_nodos["ia_embeddings"] += 1
                # Reasignar parámetros y opciones actualizados al nodo
                parametros_nodo["options"] = opciones_nodo
                nodo_actual["parameters"] = parametros_nodo

        registrador.info(f"Actualizaciones en plantilla JSON: Trigger={actualizaciones_nodos['chat_trigger']}, Agente={actualizaciones_nodos['agente_ia']}, VectorStore={actualizaciones_nodos['vector_store']}, LLMs={actualizaciones_nodos['ia_llm']}, Embeddings={actualizaciones_nodos['ia_embeddings']}")

        # Importar el flujo modificado a N8N
        flujo_importado = self.importar_flujo_de_trabajo_desde_json(json_plantilla_flujo)
        if not flujo_importado or not flujo_importado.id:
            registrador.error(f"Falló la importación del flujo N8N modificado '{nombre_flujo_modificado}'.")
            return None

        registrador.info(f"Flujo '{flujo_importado.name}' importado con ID: {flujo_importado.id}")

        # Activar el flujo importado si no está activo
        if not flujo_importado.active:
            registrador.info(f"Flujo '{flujo_importado.name}' (ID: {flujo_importado.id}) no está activo. Intentando activar...")
            if not self.activar_flujo_de_trabajo(flujo_importado.id):
                registrador.error(f"Falló la activación del flujo ID: {flujo_importado.id}. Aún así, se intentará devolver la URL del webhook.")
                # Continuar para devolver la URL del webhook, ya que podría activarse manualmente.
        else:
            registrador.info(f"Flujo '{flujo_importado.name}' (ID: {flujo_importado.id}) ya está activo o fue activado durante la importación.")

        # Construir y devolver la URL del webhook
        url_webhook_generada = self._construir_url_webhook(id_webhook_para_chat_trigger)
        if url_webhook_generada:
            registrador.info(f"Flujo de chat para curso {id_curso} desplegado. URL Webhook: {url_webhook_generada}")
            return url_webhook_generada
        else:
            registrador.error(f"No se pudo determinar la URL del webhook para el flujo '{flujo_importado.name}'. Verifique la plantilla y la configuración N8N_WEBHOOK_URL.")
            # Como último recurso, devolver la URL base de webhook configurada (puede no ser la correcta)
            return self.config_n8n.url_webhook_chat_n8n # CAMBIADO: url_webhook -> url_webhook_chat_n8n

    def eliminar_flujo_de_trabajo(self, id_flujo: str) -> bool:
        """Elimina un flujo de trabajo de N8N por su ID."""
        registrador.info(f"Intentando eliminar flujo de trabajo ID: {id_flujo}")
        try:
            self._realizar_peticion_api("DELETE", f"workflows/{id_flujo}")
            registrador.info(f"Flujo de trabajo {id_flujo} eliminado exitosamente.")
            return True
        except ErrorClienteN8N as e:
            if e.codigo_estado == 404:
                registrador.warning(f"Flujo de trabajo {id_flujo} no encontrado para eliminar (404).")
                return False # O True si se considera "ya no existe" como éxito
            registrador.error(f"Error eliminando el flujo de trabajo {id_flujo}: {e}")
            return False
        except Exception as e_gen:
            registrador.exception(f"Error inesperado al eliminar flujo de trabajo {id_flujo}: {e_gen}")
            return False
