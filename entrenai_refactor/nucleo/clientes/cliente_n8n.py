import json
from pathlib import Path
from typing import List, Optional, Dict, Any
from urllib.parse import urljoin
import uuid # Para generar IDs únicos para webhooks

import requests

from entrenai_refactor.api import modelos as modelos_api # Modelos Pydantic para la API
from entrenai_refactor.config.configuracion import configuracion_global, _ConfiguracionAnidadaOllama, _ConfiguracionAnidadaGemini # Tipos de config anidados
from entrenai_refactor.config.registrador import obtener_registrador

registrador = obtener_registrador(__name__)

class ErrorClienteN8N(Exception):
    """Excepción personalizada para errores relacionados con el ClienteN8N."""

    def __init__(
        self,
        mensaje: str,
        codigo_estado: Optional[int] = None,
        datos_respuesta: Optional[Any] = None,
        endpoint_solicitado: Optional[str] = None, # Añadido para más contexto
    ):
        super().__init__(mensaje)
        self.codigo_estado = codigo_estado
        self.datos_respuesta = datos_respuesta
        self.endpoint_solicitado = endpoint_solicitado
        registrador.debug(f"Excepción ErrorClienteN8N creada: '{mensaje}', Endpoint: {endpoint_solicitado}, Código: {codigo_estado}, Respuesta: {str(datos_respuesta)[:200]}")

    def __str__(self):
        detalle_endpoint = f" (Endpoint: {self.endpoint_solicitado})" if self.endpoint_solicitado else ""
        detalle_codigo = f", Código de Estado: {self.codigo_estado}" if self.codigo_estado is not None else ""
        return f"{super().__str__()}{detalle_endpoint}{detalle_codigo}"

class ClienteN8N:
    """Cliente para interactuar con la API REST de n8n."""

    def __init__(self, sesion_http_externa: Optional[requests.Session] = None): # Renombrado parámetro
        """
        Inicializa el ClienteN8N.

        Args:
            sesion_http_externa: Opcional. Una instancia de requests.Session para reutilizar.
                                 Si no se provee, se crea una nueva sesión.
        """
        self.config_n8n = configuracion_global.n8n # Acceso a la sub-configuración de N8N
        self.url_base_api: Optional[str] = None # URL completa al endpoint /api/v1/ de N8N

        if not self.config_n8n.url_n8n:
            registrador.error("URL de N8N (N8N_URL) no configurada. ClienteN8N no será funcional.")
        else:
            # Asegurar que la URL base termine con "/api/v1/"
            url_instancia_n8n_limpia = self.config_n8n.url_n8n.rstrip("/")
            # Verificar si ya incluye /api/v1 o solo parte de él
            if "/api/v1" in url_instancia_n8n_limpia:
                self.url_base_api = url_instancia_n8n_limpia.split("/api/v1")[0] + "/api/v1/"
            elif "/api" in url_instancia_n8n_limpia: # Podría ser /api y necesitar /v1
                 self.url_base_api = url_instancia_n8n_limpia.split("/api")[0] + "/api/v1/"
            else: # Añadir /api/v1/ completo
                self.url_base_api = url_instancia_n8n_limpia + "/api/v1/"
            registrador.info(f"ClienteN8N inicializado. URL base API N8N: {self.url_base_api}")

        self.sesion_http = sesion_http_externa or requests.Session()
        if self.config_n8n.clave_api_n8n:
            self.sesion_http.headers.update({"X-N8N-API-KEY": self.config_n8n.clave_api_n8n})
        else:
            registrador.warning("Clave API de N8N (N8N_API_KEY) no configurada. Algunas operaciones podrían fallar o requerir autenticación alternativa.")


    def _realizar_peticion_api(
        self,
        metodo_http: str,
        endpoint_api: str, # Relativo a /api/v1/
        parametros_url: Optional[Dict[str, Any]] = None,
        datos_json_cuerpo: Optional[Dict[str, Any]] = None,
    ) -> Any:
        """
        Realiza una petición genérica a la API de N8N.
        Maneja la construcción de la URL completa, el envío de datos y la gestión de errores.
        """
        if not self.url_base_api:
            registrador.error("URL base API de N8N no disponible. No se puede realizar la petición.")
            raise ErrorClienteN8N("ClienteN8N no configurado con URL base API.", endpoint_solicitado=endpoint_api)

        # urljoin se encarga de manera segura de unir la URL base con el endpoint,
        # incluso si endpoint_api comienza con '/'.
        url_completa_destino = urljoin(self.url_base_api, endpoint_api.lstrip("/"))
        respuesta_http: Optional[requests.Response] = None

        registrador.debug(f"Realizando petición {metodo_http.upper()} a N8N: {url_completa_destino}, Params: {parametros_url}, JSON: {datos_json_cuerpo is not None}")
        try:
            if metodo_http.upper() == "GET":
                respuesta_http = self.sesion_http.get(url_completa_destino, params=parametros_url, timeout=10)
            elif metodo_http.upper() == "POST":
                respuesta_http = self.sesion_http.post(url_completa_destino, params=parametros_url, json=datos_json_cuerpo, timeout=15)
            elif metodo_http.upper() == "PUT":
                respuesta_http = self.sesion_http.put(url_completa_destino, params=parametros_url, json=datos_json_cuerpo, timeout=15)
            elif metodo_http.upper() == "PATCH": # PATCH usualmente no usa params en URL, van en cuerpo si es necesario
                respuesta_http = self.sesion_http.patch(url_completa_destino, json=datos_json_cuerpo, timeout=10)
            elif metodo_http.upper() == "DELETE":
                respuesta_http = self.sesion_http.delete(url_completa_destino, params=parametros_url, timeout=10)
            else:
                registrador.error(f"Método HTTP '{metodo_http}' no soportado por _realizar_peticion_api para N8N.")
                raise ErrorClienteN8N(f"Método HTTP no soportado: {metodo_http}", endpoint_solicitado=endpoint_api)

            respuesta_http.raise_for_status() # Lanza HTTPError para respuestas 4xx/5xx

            if respuesta_http.status_code == 204: # Sin Contenido (ej. algunas operaciones PATCH, DELETE o POST sin retorno)
                registrador.debug(f"Respuesta 204 (Sin Contenido) de N8N para endpoint '{endpoint_api}'.")
                return None # No hay cuerpo JSON que decodificar

            # Intentar decodificar JSON; puede fallar si la respuesta está vacía pero no es 204 (raro pero posible)
            return respuesta_http.json()

        except requests.exceptions.HTTPError as error_http:
            codigo_estado_error = respuesta_http.status_code if respuesta_http is not None else None
            texto_respuesta_error = respuesta_http.text if respuesta_http is not None else "Sin texto de respuesta."
            registrador.error(f"Error HTTP {codigo_estado_error} llamando a N8N endpoint '{endpoint_api}': {error_http}. Respuesta: {texto_respuesta_error[:200]}...")
            raise ErrorClienteN8N(f"Error HTTP de N8N: {codigo_estado_error}", codigo_estado=codigo_estado_error, datos_respuesta=texto_respuesta_error, endpoint_solicitado=endpoint_api) from error_http
        except requests.exceptions.RequestException as error_peticion: # Errores de red, DNS, etc.
            registrador.error(f"Excepción de red/petición para N8N endpoint '{endpoint_api}': {error_peticion}")
            raise ErrorClienteN8N(f"Error de red o petición a N8N para '{endpoint_api}': {error_peticion}", endpoint_solicitado=endpoint_api) from error_peticion
        except ValueError as error_json:  # Incluye JSONDecodeError
            texto_respuesta_bruta = respuesta_http.text if respuesta_http is not None else "Sin respuesta HTTP." # Puede ser None si la conexión falló antes
            registrador.error(f"Error en decodificación JSON para N8N endpoint '{endpoint_api}': {error_json}. Respuesta bruta: {texto_respuesta_bruta[:200]}...")
            raise ErrorClienteN8N(f"Falló la decodificación de respuesta JSON de N8N para '{endpoint_api}'", datos_respuesta=texto_respuesta_bruta, endpoint_solicitado=endpoint_api) from error_json

    def obtener_lista_de_flujos_de_trabajo(self, limite_resultados: Optional[int] = None, etiquetas_filtro: Optional[str] = None) -> List[modelos_api.FlujoTrabajoN8N]:
        """Obtiene una lista de flujos de trabajo de N8N, con opción de paginación y filtrado por etiquetas."""
        endpoint = "workflows"
        parametros_api: Dict[str, Any] = {}
        if limite_resultados is not None:
            parametros_api["limit"] = limite_resultados
        if etiquetas_filtro: # N8N espera las etiquetas como una string separada por comas
            parametros_api["tags"] = etiquetas_filtro

        registrador.info(f"Obteniendo lista de flujos de trabajo de N8N. Límite: {limite_resultados}, Etiquetas: {etiquetas_filtro}")
        try:
            datos_respuesta_api = self._realizar_peticion_api("GET", endpoint, parametros_url=parametros_api)

            flujos_trabajo_crudos = []
            # N8N suele devolver los datos bajo una clave 'data'
            if isinstance(datos_respuesta_api, dict) and "data" in datos_respuesta_api and isinstance(datos_respuesta_api["data"], list):
                flujos_trabajo_crudos = datos_respuesta_api["data"]
            elif isinstance(datos_respuesta_api, list): # Algunas versiones/endpoints de N8N pueden devolver una lista directamente
                flujos_trabajo_crudos = datos_respuesta_api
            else:
                registrador.error(f"Respuesta inesperada al obtener flujos de N8N (endpoint '{endpoint}'): {str(datos_respuesta_api)[:200]}...")
                raise ErrorClienteN8N("Lista de flujos de trabajo no está en el formato esperado.", datos_respuesta=datos_respuesta_api, endpoint_solicitado=endpoint)

            flujos_procesados = [modelos_api.FlujoTrabajoN8N(**datos_flujo) for datos_flujo in flujos_trabajo_crudos]
            registrador.info(f"Se encontraron {len(flujos_procesados)} flujos de trabajo en N8N.")
            return flujos_procesados

        except ErrorClienteN8N as e_cliente: # Error ya logueado en _realizar_peticion_api
            registrador.error(f"Falló la obtención de la lista de flujos de N8N: {e_cliente}")
            raise # Re-lanzar para que el llamador maneje
        except Exception as e_parseo: # Errores de validación Pydantic u otros
            registrador.exception(f"Error inesperado al parsear la lista de flujos de N8N: {e_parseo}")
            raise ErrorClienteN8N(f"Error inesperado al parsear flujos de N8N: {e_parseo}", endpoint_solicitado=endpoint) from e_parseo

    def obtener_detalles_de_flujo_de_trabajo(self, id_flujo: str) -> Optional[modelos_api.FlujoTrabajoN8N]:
        """Obtiene los detalles completos de un flujo de trabajo específico por su ID."""
        endpoint = f"workflows/{id_flujo}"
        registrador.info(f"Obteniendo detalles para el flujo de trabajo N8N ID: {id_flujo}")
        try:
            datos_flujo_api = self._realizar_peticion_api("GET", endpoint)

            # N8N puede devolver el objeto directamente o anidado bajo 'data'
            if isinstance(datos_flujo_api, dict) and "data" in datos_flujo_api and isinstance(datos_flujo_api["data"], dict):
                flujo_procesado = modelos_api.FlujoTrabajoN8N(**datos_flujo_api["data"])
            elif isinstance(datos_flujo_api, dict) and "id" in datos_flujo_api: # Asumir que es el objeto de flujo directamente
                flujo_procesado = modelos_api.FlujoTrabajoN8N(**datos_flujo_api)
            else:
                registrador.warning(f"Respuesta inesperada para detalles del flujo N8N {id_flujo}: {str(datos_flujo_api)[:200]}...")
                return None # O lanzar error si se espera una estructura específica siempre

            registrador.info(f"Detalles obtenidos para el flujo N8N '{flujo_procesado.name}' (ID: {id_flujo}).")
            return flujo_procesado

        except ErrorClienteN8N as e_cliente:
            if e_cliente.codigo_estado == 404:
                registrador.warning(f"Flujo de trabajo N8N con ID '{id_flujo}' no encontrado (404).")
                return None
            registrador.error(f"Falló la obtención de detalles para el flujo N8N '{id_flujo}': {e_cliente}")
            raise # Re-lanzar para otros errores de API
        except Exception as e_gen: # Errores de validación Pydantic u otros
            registrador.exception(f"Error inesperado obteniendo/parseando detalles del flujo N8N '{id_flujo}': {e_gen}")
            raise ErrorClienteN8N(f"Error inesperado obteniendo detalles del flujo N8N '{id_flujo}': {e_gen}", endpoint_solicitado=endpoint) from e_gen

    def importar_flujo_de_trabajo_desde_json(self, definicion_json_flujo: Dict[str, Any]) -> Optional[modelos_api.FlujoTrabajoN8N]:
        """
        Importa un nuevo flujo de trabajo a N8N usando su definición JSON completa.
        El JSON debe ser la estructura completa del flujo (nodos, conexiones, settings, etc.).
        """
        endpoint_importacion = "workflows"
        nombre_flujo_intento = definicion_json_flujo.get('name', 'Flujo Importado Sin Nombre')
        registrador.info(f"Intentando importar flujo '{nombre_flujo_intento}' a N8N (endpoint: {endpoint_importacion}).")

        # N8N espera una estructura JSON específica para la importación.
        # Se pasa la definición tal cual, asumiendo que es correcta.
        # Es importante que 'nodes', 'connections', 'settings', etc., estén al nivel raíz del JSON.
        try:
            datos_flujo_importado_api = self._realizar_peticion_api("POST", endpoint_importacion, datos_json_cuerpo=definicion_json_flujo)

            flujo_procesado = None
            # La respuesta de importación puede variar, a veces es el objeto directo, a veces bajo 'data'.
            if isinstance(datos_flujo_importado_api, dict) and "id" in datos_flujo_importado_api:
                flujo_procesado = modelos_api.FlujoTrabajoN8N(**datos_flujo_importado_api)
            elif isinstance(datos_flujo_importado_api, dict) and "data" in datos_flujo_importado_api and isinstance(datos_flujo_importado_api["data"], dict) and "id" in datos_flujo_importado_api["data"]:
                flujo_procesado = modelos_api.FlujoTrabajoN8N(**datos_flujo_importado_api["data"])

            if flujo_procesado:
                registrador.info(f"Flujo '{flujo_procesado.name}' importado/actualizado exitosamente en N8N. ID: {flujo_procesado.id}")
                return flujo_procesado
            else:
                registrador.error(f"Estructura de respuesta inesperada tras importar flujo N8N '{nombre_flujo_intento}': {str(datos_flujo_importado_api)[:200]}...")
                return None # No se pudo parsear la respuesta como un flujo válido
        except ErrorClienteN8N as e_cliente:
            registrador.error(f"Falló la importación del flujo '{nombre_flujo_intento}' a N8N: {e_cliente}")
            return None # Devolver None si la importación falla por error de API
        except Exception as e_gen: # Errores de validación Pydantic u otros
            registrador.exception(f"Error inesperado durante la importación del flujo N8N '{nombre_flujo_intento}': {e_gen}")
            return None


    def activar_flujo_de_trabajo(self, id_flujo: str) -> bool:
        """Activa un flujo de trabajo en N8N por su ID."""
        endpoint_activacion = f"workflows/{id_flujo}/activate"
        registrador.info(f"Intentando activar flujo de trabajo N8N ID: {id_flujo} (endpoint: {endpoint_activacion})")
        try:
            # El endpoint de activación es un POST, usualmente sin cuerpo.
            self._realizar_peticion_api("POST", endpoint_activacion)
            registrador.info(f"Flujo de trabajo N8N {id_flujo} activado exitosamente.")
            return True
        except ErrorClienteN8N as e_cliente:
            registrador.error(f"Error activando el flujo de trabajo N8N {id_flujo}: {e_cliente}")
            return False

    def desactivar_flujo_de_trabajo(self, id_flujo: str) -> bool:
        """Desactiva un flujo de trabajo en N8N por su ID."""
        endpoint_desactivacion = f"workflows/{id_flujo}/deactivate"
        registrador.info(f"Intentando desactivar flujo de trabajo N8N ID: {id_flujo} (endpoint: {endpoint_desactivacion})")
        try:
            # El endpoint de desactivación es un POST, usualmente sin cuerpo.
            self._realizar_peticion_api("POST", endpoint_desactivacion)
            registrador.info(f"Flujo de trabajo N8N {id_flujo} desactivado exitosamente.")
            return True
        except ErrorClienteN8N as e_cliente:
            registrador.error(f"Error desactivando el flujo de trabajo N8N {id_flujo}: {e_cliente}")
            return False

    def _construir_url_webhook_nodo_chat(self, id_nodo_webhook_chat: str) -> Optional[str]:
        """
        Construye la URL completa del webhook para un nodo Chat Trigger específico.
        Utiliza el ID del webhook del nodo (path del nodo) y la configuración N8N_WEBHOOK_URL o N8N_URL.
        """
        if not id_nodo_webhook_chat:
            registrador.warning("No se proporcionó ID de webhook del nodo Chat Trigger para construir la URL.")
            return None

        # Priorizar N8N_WEBHOOK_URL si está definida, sino usar N8N_URL (la URL base de la instancia).
        # N8N_WEBHOOK_URL es útil si N8N está detrás de un proxy y los webhooks tienen una URL pública diferente.
        url_base_para_webhooks = self.config_n8n.url_webhook_chat_n8n or self.config_n8n.url_n8n
        if not url_base_para_webhooks:
            registrador.error("No hay URL base (N8N_WEBHOOK_URL o N8N_URL) configurada para construir la URL del webhook del chat.")
            return None

        # Limpiar la URL base de N8N si contiene /api... para construir la URL del webhook correctamente.
        # Los webhooks se exponen en la raíz de la URL de N8N, no bajo /api/v1/.
        url_base_limpia_webhooks = url_base_para_webhooks.split("/api/")[0].rstrip("/")

        # El path del webhook en N8N para un Chat Trigger es típicamente /webhook/{webhookIdDelNodo}/chat
        url_webhook_completa = f"{url_base_limpia_webhooks}/webhook/{id_nodo_webhook_chat}/chat"
        registrador.debug(f"URL de webhook para nodo Chat Trigger construida: {url_webhook_completa}")
        return url_webhook_completa

    def configurar_y_desplegar_flujo_de_chat_para_curso(
        self,
        id_curso: int,
        nombre_curso: str,
        nombre_coleccion_pgvector_curso: str, # Nombre de la tabla/colección en PGVector para este curso
        proveedor_ia_configurado: str, # 'ollama' o 'gemini'
        config_ollama_proveedor: Optional[_ConfiguracionAnidadaOllama] = None, # Configuración de Ollama si es el proveedor
        config_gemini_proveedor: Optional[_ConfiguracionAnidadaGemini] = None, # Configuración de Gemini si es el proveedor
        mensajes_iniciales_chat: Optional[str] = None, # Mensajes que el chatbot muestra al iniciar
        mensaje_sistema_agente_ia: Optional[str] = None, # Instrucciones adicionales para el prompt de sistema del agente IA
        placeholder_entrada_chat: Optional[str] = None, # Texto de ejemplo en el campo de entrada del chat
        titulo_ventana_chat: Optional[str] = None, # Título de la ventana/widget de chat
    ) -> Optional[str]: # Devuelve la URL del webhook del chat si es exitoso, sino None
        """
        Configura y despliega un flujo de chat en N8N para un curso específico.
        Carga una plantilla JSON, la modifica con los parámetros proporcionados,
        la importa a N8N, la activa y devuelve la URL del webhook del chat.
        """
        registrador.info(f"Configurando y desplegando flujo de chat N8N para curso ID: {id_curso} ('{nombre_curso}')")

        # Cargar la plantilla de flujo de trabajo JSON desde la ruta configurada
        ruta_plantilla_flujo_relativa = self.config_n8n.ruta_plantilla_flujo_n8n
        # La ruta en config es relativa a la raíz del proyecto 'entrenai_refactor'.
        # Asumimos que el CWD es la raíz del proyecto 'entrenai_refactor' o que la ruta es absoluta.
        # Para mayor robustez, se podría calcular la ruta absoluta desde la ubicación de este archivo.
        ruta_base_proyecto_actual = Path(__file__).resolve().parent.parent.parent # Sube 3 niveles: clientes -> nucleo -> entrenai_refactor
        ruta_plantilla_flujo_absoluta = ruta_base_proyecto_actual / ruta_plantilla_flujo_relativa

        if not ruta_plantilla_flujo_absoluta.is_file():
            registrador.error(f"Archivo de plantilla de flujo N8N no encontrado en: {ruta_plantilla_flujo_absoluta} (CWD actual: {Path.cwd()})")
            return None

        try:
            with open(ruta_plantilla_flujo_absoluta, "r", encoding="utf-8") as archivo_plantilla:
                json_plantilla_flujo_original = json.load(archivo_plantilla)
            registrador.debug(f"Plantilla de flujo N8N cargada desde: {ruta_plantilla_flujo_absoluta}")
        except Exception as e_lectura_plantilla:
            registrador.error(f"Falló la lectura o parseo del JSON de la plantilla de flujo N8N desde {ruta_plantilla_flujo_absoluta}: {e_lectura_plantilla}")
            return None

        # Modificar el nombre del flujo y añadir etiqueta con el ID del curso
        nombre_flujo_n8n_final = f"EntrenAI Chat - Curso: {nombre_curso} (ID: {id_curso})"
        json_plantilla_flujo_original["name"] = nombre_flujo_n8n_final
        if "tags" not in json_plantilla_flujo_original or not isinstance(json_plantilla_flujo_original.get("tags"), list):
            json_plantilla_flujo_original["tags"] = []
        # Añadir tag para fácil filtrado y gestión en N8N, evitando duplicados si ya existe
        tag_curso = {"name": f"curso_id:{id_curso}"}
        if tag_curso not in json_plantilla_flujo_original["tags"]:
            json_plantilla_flujo_original["tags"].append(tag_curso)

        # Generar un ID único para el webhook del nodo Chat Trigger de este flujo específico
        id_webhook_chat_trigger_unico = str(uuid.uuid4())

        # Banderas para verificar si los nodos clave fueron encontrados y actualizados
        estado_actualizacion_nodos = {"chat_trigger": False, "agente_ia": False, "vector_store": False, "llm_chat": 0, "embeddings_model": 0}

        # Iterar sobre los nodos de la plantilla y actualizarlos con la configuración específica del curso
        for nodo_iteracion in json_plantilla_flujo_original.get("nodes", []):
            tipo_nodo_actual = nodo_iteracion.get("type", "")
            parametros_nodo_actual = nodo_iteracion.get("parameters", {})
            opciones_parametros_nodo = parametros_nodo_actual.get("options", {}) # Algunos parámetros están en 'options'

            # Configurar Nodo Chat Trigger (Webhook)
            if tipo_nodo_actual == "@n8n/n8n-nodes-langchain.chatTrigger":
                nodo_iteracion["webhookId"] = id_webhook_chat_trigger_unico # Asignar el ID de webhook único generado
                if mensajes_iniciales_chat:
                    parametros_nodo_actual["initialMessages"] = mensajes_iniciales_chat
                if placeholder_entrada_chat: # El placeholder está en 'options'
                    opciones_parametros_nodo["inputPlaceholder"] = placeholder_entrada_chat
                if titulo_ventana_chat: # El título está en 'options'
                    opciones_parametros_nodo["title"] = titulo_ventana_chat
                estado_actualizacion_nodos["chat_trigger"] = True

            # Configurar Nodo AI Agent (Agente Langchain)
            elif tipo_nodo_actual == "@n8n/n8n-nodes-langchain.agent":
                if mensaje_sistema_agente_ia: # Añadir al prompt de sistema existente en la plantilla
                    prompt_sistema_base = opciones_parametros_nodo.get("systemMessage", "") # El prompt está en 'options'
                    opciones_parametros_nodo["systemMessage"] = f"{prompt_sistema_base}\n\n{mensaje_sistema_agente_ia}".strip()
                estado_actualizacion_nodos["agente_ia"] = True

            # Configurar Nodo Vector Store (PGVector)
            elif tipo_nodo_actual == "@n8n/n8n-nodes-langchain.vectorStorePGVector":
                parametros_nodo_actual["tableName"] = nombre_coleccion_pgvector_curso # Nombre de la tabla/colección en PGVector
                estado_actualizacion_nodos["vector_store"] = True

            # Configurar Nodos de LLM y Embeddings según el proveedor de IA seleccionado
            elif "lmChat" in tipo_nodo_actual or "embeddings" in tipo_nodo_actual: # Identificar nodos de LLM y Embeddings
                if proveedor_ia_configurado == "gemini" and config_gemini_proveedor:
                    if "lmChat" in tipo_nodo_actual : # Nodo LLM para Chat
                        nodo_iteracion["type"] = "@n8n/n8n-nodes-langchain.lmChatGoogleGemini" # Cambiar tipo a Gemini
                        parametros_nodo_actual["modelName"] = config_gemini_proveedor.modelo_texto_gemini
                        # Aquí se asume que las credenciales de Gemini están configuradas globalmente en N8N o se deben pasar.
                        estado_actualizacion_nodos["llm_chat"] += 1
                    elif "embeddings" in tipo_nodo_actual: # Nodo para generar Embeddings
                        nodo_iteracion["type"] = "@n8n/n8n-nodes-langchain.embeddingsGoogleGemini" # Cambiar tipo a Gemini
                        parametros_nodo_actual["modelName"] = config_gemini_proveedor.modelo_embedding_gemini
                        estado_actualizacion_nodos["embeddings_model"] += 1
                elif proveedor_ia_configurado == "ollama" and config_ollama_proveedor:
                    if "lmChat" in tipo_nodo_actual: # Nodo LLM para Chat
                        nodo_iteracion["type"] = "@n8n/n8n-nodes-langchain.lmChatOllama" # Cambiar tipo a Ollama
                        parametros_nodo_actual["model"] = config_ollama_proveedor.modelo_qa_ollama # Usar modelo_qa para el chat principal
                        parametros_nodo_actual["baseUrl"] = config_ollama_proveedor.host_ollama
                        # Limpiar credenciales de otros proveedores si existieran en la plantilla
                        if "credentials" in nodo_iteracion and ("googlePalmApi" in nodo_iteracion["credentials"] or "googleVertexAi" in nodo_iteracion["credentials"]):
                            del nodo_iteracion["credentials"]
                        estado_actualizacion_nodos["llm_chat"] += 1
                    elif "embeddings" in tipo_nodo_actual: # Nodo para generar Embeddings
                        nodo_iteracion["type"] = "@n8n/n8n-nodes-langchain.embeddingsOllama" # Cambiar tipo a Ollama
                        parametros_nodo_actual["model"] = config_ollama_proveedor.modelo_embedding_ollama
                        parametros_nodo_actual["baseUrl"] = config_ollama_proveedor.host_ollama
                        if "credentials" in nodo_iteracion and ("googlePalmApi" in nodo_iteracion["credentials"] or "googleVertexAi" in nodo_iteracion["credentials"]):
                            del nodo_iteracion["credentials"]
                        estado_actualizacion_nodos["embeddings_model"] += 1
                # Reasignar 'options' y 'parameters' actualizados al nodo
                parametros_nodo_actual["options"] = opciones_parametros_nodo
                nodo_iteracion["parameters"] = parametros_nodo_actual

        registrador.info(f"Actualizaciones en plantilla JSON para N8N: Trigger Chat={estado_actualizacion_nodos['chat_trigger']}, Agente IA={estado_actualizacion_nodos['agente_ia']}, VectorStore={estado_actualizacion_nodos['vector_store']}, LLMs Chat={estado_actualizacion_nodos['llm_chat']}, Modelos Embeddings={estado_actualizacion_nodos['embeddings_model']}")

        # Importar el flujo modificado a N8N
        flujo_importado_n8n = self.importar_flujo_de_trabajo_desde_json(json_plantilla_flujo_original)
        if not flujo_importado_n8n or not flujo_importado_n8n.id:
            registrador.error(f"Falló la importación a N8N del flujo modificado '{nombre_flujo_n8n_final}'.")
            return None

        registrador.info(f"Flujo N8N '{flujo_importado_n8n.name}' importado con ID: {flujo_importado_n8n.id}")

        # Activar el flujo importado si no está activo ya
        if not flujo_importado_n8n.active:
            registrador.info(f"Flujo N8N '{flujo_importado_n8n.name}' (ID: {flujo_importado_n8n.id}) no está activo. Intentando activar...")
            if not self.activar_flujo_de_trabajo(flujo_importado_n8n.id):
                registrador.error(f"Falló la activación del flujo N8N ID: {flujo_importado_n8n.id}. Se devolverá la URL del webhook, pero el flujo podría necesitar activación manual.")
                # Continuar para devolver la URL del webhook igualmente.
        else:
            registrador.info(f"Flujo N8N '{flujo_importado_n8n.name}' (ID: {flujo_importado_n8n.id}) ya está activo o fue activado durante la importación.")

        # Construir y devolver la URL del webhook del Chat Trigger
        url_webhook_chat_final = self._construir_url_webhook_nodo_chat(id_webhook_chat_trigger_unico)
        if url_webhook_chat_final:
            registrador.info(f"Flujo de chat N8N para curso {id_curso} desplegado. URL Webhook: {url_webhook_chat_final}")
            return url_webhook_chat_final
        else:
            registrador.error(f"No se pudo determinar la URL del webhook para el flujo N8N '{flujo_importado_n8n.name}'. Verifique la plantilla y la configuración de N8N_WEBHOOK_URL o N8N_URL.")
            # Como último recurso, si la URL base de webhooks está configurada, devolverla (puede no ser la correcta completa).
            return self.config_n8n.url_webhook_chat_n8n or self.config_n8n.url_n8n

    def eliminar_flujo_de_trabajo(self, id_flujo: str) -> bool:
        """Elimina un flujo de trabajo de N8N por su ID."""
        endpoint_eliminacion = f"workflows/{id_flujo}"
        registrador.info(f"Intentando eliminar flujo de trabajo N8N ID: {id_flujo} (endpoint: {endpoint_eliminacion})")
        try:
            self._realizar_peticion_api("DELETE", endpoint_eliminacion)
            registrador.info(f"Flujo de trabajo N8N {id_flujo} eliminado exitosamente.")
            return True
        except ErrorClienteN8N as e_cliente:
            if e_cliente.codigo_estado == 404: # Si N8N devuelve 404, el flujo ya no existe.
                registrador.warning(f"Flujo de trabajo N8N {id_flujo} no encontrado para eliminar (404). Se considera como no existente.")
                return True # Considerar éxito si ya no existe
            registrador.error(f"Error eliminando el flujo de trabajo N8N {id_flujo}: {e_cliente}")
            return False
        except Exception as e_gen: # Otros errores inesperados
            registrador.exception(f"Error inesperado al eliminar flujo de trabajo N8N {id_flujo}: {e_gen}")
            return False

[end of entrenai_refactor/nucleo/clientes/cliente_n8n.py]

[start of entrenai_refactor/nucleo/clientes/__init__.py]
# Inicialización del submódulo de clientes

# Importar las clases refactorizadas para que estén disponibles
# al importar el paquete 'clientes'.
from .cliente_moodle import ClienteMoodle, ErrorAPIMoodle
from .cliente_n8n import ClienteN8N, ErrorClienteN8N

__all__ = [
    "ClienteMoodle",
    "ErrorAPIMoodle",
    "ClienteN8N",
    "ErrorClienteN8N",
]
[end of entrenai_refactor/nucleo/clientes/__init__.py]
