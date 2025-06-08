from typing import List, Optional, Any
from pathlib import Path
import ollama

from entrenai_refactor.config.configuracion import configuracion_global
from entrenai_refactor.config.registrador import obtener_registrador
from entrenai_refactor.nucleo.ia.utilidades_comunes_ia import (
    postprocesar_contenido_markdown,
    preprocesar_contenido_texto,
    guardar_markdown_en_archivo,
)

registrador = obtener_registrador(__name__)

MENSAJE_CLIENTE_NO_INICIALIZADO = "Cliente Ollama no inicializado."

class ErrorEnvoltorioOllama(Exception):
    """Excepción personalizada para errores del EnvoltorioOllama."""
    pass

class EnvoltorioOllama:
    """Envoltorio para interactuar con la API de Ollama."""

    def __init__(self):
        self.config_ollama = configuracion_global.ollama
        self.cliente: Optional[ollama.Client] = None
        try:
            if self.config_ollama.host:
                self.cliente = ollama.Client(host=self.config_ollama.host)
                self.cliente.list() # Probar conexión listando modelos locales
                registrador.info(f"Cliente Ollama inicializado y conectado al host: {self.config_ollama.host}")
                self._asegurar_modelos_disponibles()
            else:
                registrador.error("Host de Ollama no configurado. EnvoltorioOllama no será funcional.")
                raise ErrorEnvoltorioOllama("Host de Ollama no configurado.")
        except Exception as e:
            registrador.error(f"Falló la conexión o inicialización del cliente Ollama en {self.config_ollama.host}: {e}")
            self.cliente = None
            # Considerar no relanzar para permitir inicio de app si Ollama no está, pero métodos fallarán.
            # raise ErrorEnvoltorioOllama(f"Falló la inicialización del cliente Ollama: {e}") from e

    def _asegurar_modelos_disponibles(self):
        """Verifica si los modelos configurados están disponibles en Ollama."""
        if not self.cliente:
            return

        try:
            respuesta_lista = self.cliente.list()
            modelos_disponibles_ollama = []
            # La respuesta de cliente.list() es un dict con una lista de modelos bajo la clave "models"
            # y cada modelo es un dict con claves como "name", "modified_at", "size".
            if isinstance(respuesta_lista, dict) and "models" in respuesta_lista:
                 for modelo_info in respuesta_lista["models"]:
                    if isinstance(modelo_info, dict) and "name" in modelo_info: # El nombre completo es 'name'
                       modelos_disponibles_ollama.append(modelo_info["name"])
            else:
                registrador.warning(f"Respuesta inesperada de Ollama list: {respuesta_lista}")


            modelos_requeridos = {
                "embedding": self.config_ollama.modelo_embedding,
                "markdown": self.config_ollama.modelo_markdown,
                "qa": self.config_ollama.modelo_qa,
                "contexto": self.config_ollama.modelo_contexto,
            }

            for tipo_modelo, nombre_modelo_config in modelos_requeridos.items():
                if not nombre_modelo_config:
                    registrador.info(f"Modelo Ollama para {tipo_modelo} no está configurado. Omitiendo verificación.")
                    continue

                nombre_base_modelo = nombre_modelo_config.split(":")[0] # Comparar solo el nombre base
                esta_presente = any(nombre_disponible.startswith(nombre_base_modelo) for nombre_disponible in modelos_disponibles_ollama)

                if not esta_presente:
                    registrador.warning(
                        f"Modelo Ollama para {tipo_modelo} ('{nombre_modelo_config}') "
                        f"no encontrado en los modelos disponibles: {modelos_disponibles_ollama}. "
                        f"Asegúrese de que esté descargado usando 'ollama pull {nombre_modelo_config}'."
                    )
                else:
                    registrador.info(f"Modelo Ollama para {tipo_modelo} ('{nombre_modelo_config}') está disponible.")
        except Exception as e:
            registrador.error(f"Error al verificar los modelos Ollama disponibles: {e}")

    def generar_embedding(self, texto: str, modelo: Optional[str] = None) -> List[float]:
        if not self.cliente:
            registrador.error(f"{MENSAJE_CLIENTE_NO_INICIALIZADO} No se puede generar el embedding.")
            raise ErrorEnvoltorioOllama(MENSAJE_CLIENTE_NO_INICIALIZADO)

        modelo_a_usar = modelo or self.config_ollama.modelo_embedding
        if not modelo_a_usar:
            registrador.error("Nombre del modelo de embedding no configurado.")
            raise ErrorEnvoltorioOllama("Nombre del modelo de embedding no configurado.")
        try:
            # Preprocesar texto antes de enviar a embedding
            texto_preprocesado = preprocesar_contenido_texto(texto)
            respuesta = self.cliente.embeddings(model=modelo_a_usar, prompt=texto_preprocesado)
            return respuesta["embedding"]
        except Exception as e:
            registrador.error(f"Error generando embedding con modelo '{modelo_a_usar}': {e}")
            raise ErrorEnvoltorioOllama(f"Falló la generación del embedding: {e}") from e

    def generar_completacion_chat(
        self, prompt: str, modelo: Optional[str] = None,
        mensaje_sistema: Optional[str] = None,
        fragmentos_contexto: Optional[List[str]] = None,
        stream: bool = False
    ) -> str:
        if not self.cliente:
            registrador.error(f"{MENSAJE_CLIENTE_NO_INICIALIZADO} No se puede generar la completación de chat.")
            raise ErrorEnvoltorioOllama(MENSAJE_CLIENTE_NO_INICIALIZADO)

        modelo_a_usar = modelo or self.config_ollama.modelo_qa
        if not modelo_a_usar:
            registrador.error("Nombre del modelo QA no configurado.")
            raise ErrorEnvoltorioOllama("Nombre del modelo QA no configurado.")

        mensajes = []
        if mensaje_sistema:
            mensajes.append({"role": "system", "content": mensaje_sistema})

        if fragmentos_contexto:
            contexto_str = "\n\n".join(fragmentos_contexto)
            prompt_completo = f"Contexto:\n{contexto_str}\n\nPregunta: {prompt}"
            mensajes.append({"role": "user", "content": prompt_completo})
        else:
            mensajes.append({"role": "user", "content": prompt})

        try:
            if stream:
                registrador.warning("El streaming no está implementado en este wrapper. Devolviendo respuesta completa.")

            respuesta = self.cliente.chat(model=modelo_a_usar, messages=mensajes, stream=False)

            contenido_respuesta = ""
            if isinstance(respuesta, dict) and "message" in respuesta and isinstance(respuesta["message"], dict) and "content" in respuesta["message"]:
                contenido_respuesta = str(respuesta["message"]["content"])
            else: # El cliente ollama.py también puede devolver un objeto directamente con atributos
                registrador.warning(f"Formato de respuesta inesperado de Ollama: {respuesta}")
                # Intentar acceder a atributos si no es el dict esperado (manejo defensivo)
                if hasattr(respuesta, "message") and hasattr(respuesta.message, "content"):
                     contenido_respuesta = str(respuesta.message.content)
                else:
                    raise ErrorEnvoltorioOllama(f"Formato de respuesta inesperado de la API de Ollama: {type(respuesta)}")


            if not contenido_respuesta:
                registrador.warning("La completación de chat devolvió contenido vacío.")
            return contenido_respuesta
        except Exception as e:
            registrador.error(f"Error generando completación de chat con modelo '{modelo_a_usar}': {e}")
            raise ErrorEnvoltorioOllama(f"Falló la generación de la completación de chat: {e}") from e

    def formatear_a_markdown(
        self, contenido_texto: str, modelo: Optional[str] = None, ruta_guardado: Optional[Path] = None
    ) -> str:
        if not self.cliente:
            registrador.error(f"{MENSAJE_CLIENTE_NO_INICIALIZADO} No se puede formatear a Markdown.")
            raise ErrorEnvoltorioOllama(MENSAJE_CLIENTE_NO_INICIALIZADO)

        modelo_a_usar = modelo or self.config_ollama.modelo_markdown
        if not modelo_a_usar:
            registrador.error("Nombre del modelo de formateo a Markdown no configurado.")
            raise ErrorEnvoltorioOllama("Nombre del modelo de formateo a Markdown no configurado.")

        texto_limpio = preprocesar_contenido_texto(contenido_texto)

        prompt_sistema = (
            "Eres un experto formateador de texto especializado en convertir texto crudo a Markdown limpio y bien estructurado. "
            "Tu tarea es transformar el contenido proporcionado a un formato Markdown. Sigue estas reglas estrictamente:\n"
            "1. Mantén el significado y la información factual del contenido original.\n"
            "2. Crea encabezados y estructura apropiados basados en la jerarquía del contenido.\n"
            "3. Formatea correctamente listas, tablas, bloques de código y otros elementos Markdown.\n"
            "4. Corrige errores tipográficos y de formato obvios mientras preservas el significado.\n"
            "5. NO añadas ningún contenido nuevo, introducciones, resúmenes o conclusiones.\n"
            "6. NO incluyas ningún meta-comentario o notas sobre el proceso de formateo.\n"
            "7. SOLO devuelve el contenido Markdown formateado correctamente, nada más.\n\n"
            "El objetivo es un Markdown limpio que represente con precisión el contenido original."
        )
        mensajes = [{"role": "system", "content": prompt_sistema}, {"role": "user", "content": texto_limpio}]

        try:
            registrador.info(f"Formateando texto a Markdown usando el modelo '{modelo_a_usar}'...")
            respuesta = self.cliente.chat(model=modelo_a_usar, messages=mensajes, stream=False)

            contenido_markdown = ""
            if isinstance(respuesta, dict) and "message" in respuesta and isinstance(respuesta["message"], dict) and "content" in respuesta["message"]:
                contenido_markdown = str(respuesta["message"]["content"])
            else:
                registrador.warning(f"Formato de respuesta inesperado para formateo a Markdown: {respuesta}")
                if hasattr(respuesta, "message") and hasattr(respuesta.message, "content"):
                     contenido_markdown = str(respuesta.message.content)
                else:
                    raise ErrorEnvoltorioOllama(f"Formato de respuesta inesperado para formateo a Markdown: {type(respuesta)}")


            contenido_markdown_postprocesado = postprocesar_contenido_markdown(contenido_markdown)

            if contenido_markdown_postprocesado:
                registrador.info(f"Texto formateado a Markdown exitosamente (longitud: {len(contenido_markdown_postprocesado)}).")
                if ruta_guardado:
                    guardar_markdown_en_archivo(contenido_markdown_postprocesado, ruta_guardado)
            else:
                registrador.warning("El formateo a Markdown devolvió contenido vacío.")
            return contenido_markdown_postprocesado
        except Exception as e:
            registrador.error(f"Error formateando texto a Markdown con modelo '{modelo_a_usar}': {e}")
            raise ErrorEnvoltorioOllama(f"Falló el formateo de texto a Markdown: {e}") from e

[end of entrenai_refactor/nucleo/ia/envoltorio_ollama.py]
