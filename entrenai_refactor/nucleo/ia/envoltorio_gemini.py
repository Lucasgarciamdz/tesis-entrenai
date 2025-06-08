from pathlib import Path
from typing import List, Optional, Dict, Any

from google import genai
from google.generativeai import types as google_types # Renombrado para evitar conflicto con typing.types

from entrenai_refactor.config.configuracion import configuracion_global
from entrenai_refactor.config.registrador import obtener_registrador
from entrenai_refactor.nucleo.ia.utilidades_comunes_ia import (
    postprocesar_contenido_markdown,
    preprocesar_contenido_texto,
    guardar_markdown_en_archivo,
)

registrador = obtener_registrador(__name__)

MENSAJE_CLIENTE_NO_INICIALIZADO = "Cliente Gemini no inicializado."
MENSAJE_CLAVE_API_NO_CONFIGURADA = "Clave API de Gemini no configurada."

class ErrorEnvoltorioGemini(Exception):
    """Excepción personalizada para errores del EnvoltorioGemini."""
    pass

class EnvoltorioGemini:
    """Envoltorio para interactuar con la API de Google Gemini."""

    def __init__(self):
        self.config_gemini = configuracion_global.gemini
        self.cliente_genai = None # El cliente se inicializa con genai.configure
        try:
            if self.config_gemini.clave_api:
                genai.configure(api_key=self.config_gemini.clave_api)
                # No hay un objeto cliente como tal, las llamadas son a través del módulo genai.
                # Se puede listar modelos para verificar la configuración.
                # list(genai.list_models()) # Esto podría ser una prueba de conexión/configuración
                registrador.info("Cliente Gemini inicializado exitosamente con la Clave API.")
            else:
                registrador.error(f"{MENSAJE_CLAVE_API_NO_CONFIGURADA} EnvoltorioGemini no funcional.")
                raise ErrorEnvoltorioGemini(MENSAJE_CLAVE_API_NO_CONFIGURADA)
        except Exception as e:
            registrador.error(f"Falló la inicialización del cliente Gemini: {e}")
            raise ErrorEnvoltorioGemini(f"Falló la inicialización del cliente Gemini: {e}") from e

    def _obtener_config_seguridad(self) -> Optional[List[Dict[str, Any]]]:
        """Obtiene la configuración de seguridad para las llamadas a la API."""
        if not self.config_gemini.seguridad_habilitada:
            # Configuración para desactivar/minimizar filtros de seguridad
            return [
                {"category": google_types.HarmCategory.HARM_CATEGORY_HARASSMENT, "threshold": google_types.HarmBlockThreshold.BLOCK_NONE},
                {"category": google_types.HarmCategory.HARM_CATEGORY_HATE_SPEECH, "threshold": google_types.HarmBlockThreshold.BLOCK_NONE},
                {"category": google_types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT, "threshold": google_types.HarmBlockThreshold.BLOCK_NONE},
                {"category": google_types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT, "threshold": google_types.HarmBlockThreshold.BLOCK_NONE},
            ]
        return None # Usar configuración de seguridad predeterminada de Gemini

    def generar_embedding(self, texto: str, modelo: Optional[str] = None) -> List[float]:
        modelo_a_usar = modelo or self.config_gemini.modelo_embedding
        if not modelo_a_usar:
            raise ErrorEnvoltorioGemini("Modelo de embedding de Gemini no especificado.")

        try:
            # Preprocesar texto antes de enviar a embedding
            texto_preprocesado = preprocesar_contenido_texto(texto)

            # La API de embeddings de Gemini espera 'model' (ej. 'models/embedding-001') y 'content'
            respuesta = genai.embed_content(model=modelo_a_usar, content=texto_preprocesado)

            if "embedding" in respuesta and isinstance(respuesta["embedding"], list):
                return respuesta["embedding"]
            else:
                registrador.error(f"Respuesta de embedding no contiene un vector válido: {respuesta}")
                raise ErrorEnvoltorioGemini("Respuesta de embedding no contiene un vector válido.")
        except Exception as e:
            registrador.error(f"Error generando embedding con modelo Gemini '{modelo_a_usar}': {e}")
            raise ErrorEnvoltorioGemini(f"Falló la generación del embedding con Gemini: {e}") from e

    def generar_completacion_chat(
        self, prompt: str, modelo: Optional[str] = None,
        mensaje_sistema: Optional[str] = None,
        fragmentos_contexto: Optional[List[str]] = None,
        stream: bool = False # El streaming no está implementado aún
    ) -> str:
        modelo_a_usar = modelo or self.config_gemini.modelo_texto # Usar modelo_texto para chat general
        if not modelo_a_usar:
            raise ErrorEnvoltorioGemini("Modelo de texto/chat de Gemini no especificado.")

        try:
            # Construir el historial de chat y el prompt
            # Gemini API v1 (genai) usa un enfoque multimodal para 'contents'
            # y 'system_instruction' para el mensaje de sistema.

            contenido_peticion = []
            if fragmentos_contexto:
                contexto_str = "\n\n".join(fragmentos_contexto)
                prompt_completo = f"Contexto:\n{contexto_str}\n\nPregunta: {prompt}"
                contenido_peticion.append(prompt_completo)
            else:
                contenido_peticion.append(prompt)

            opciones_generacion = google_types.GenerationConfig(candidate_count=1) # Por ahora, solo una respuesta candidata
            config_seguridad = self._obtener_config_seguridad()

            # Crear el modelo generativo
            modelo_generativo = genai.GenerativeModel(
                model_name=modelo_a_usar,
                safety_settings=config_seguridad,
                system_instruction=mensaje_sistema if mensaje_sistema else None
            )

            if stream:
                registrador.warning("Streaming no está implementado para Gemini en este wrapper. Devolviendo respuesta completa.")
                # Aquí iría la lógica de streaming si se implementa

            respuesta = modelo_generativo.generate_content(contents=contenido_peticion, generation_config=opciones_generacion, stream=stream)

            # Extraer contenido de la respuesta
            # La respuesta.text es la forma más directa si no hay errores o bloqueos.
            contenido_respuesta = ""
            if respuesta.parts:
                 contenido_respuesta = "".join(part.text for part in respuesta.parts if hasattr(part, "text"))

            if not contenido_respuesta and respuesta.prompt_feedback and respuesta.prompt_feedback.block_reason:
                registrador.error(f"Contenido bloqueado por Gemini. Razón: {respuesta.prompt_feedback.block_reason_message}")
                raise ErrorEnvoltorioGemini(f"Contenido bloqueado por Gemini: {respuesta.prompt_feedback.block_reason_message}")

            if not contenido_respuesta:
                registrador.warning("La completación de chat de Gemini devolvió contenido vacío.")

            return contenido_respuesta

        except Exception as e:
            registrador.exception(f"Error generando completación de chat con modelo Gemini '{modelo_a_usar}': {e}")
            raise ErrorEnvoltorioGemini(f"Falló la generación de completación de chat con Gemini: {e}") from e

    def formatear_a_markdown(
        self, contenido_texto: str, modelo: Optional[str] = None, ruta_guardado: Optional[Path] = None
    ) -> str:
        modelo_a_usar = modelo or self.config_gemini.modelo_texto # Usar modelo_texto para esta tarea
        if not modelo_a_usar:
            raise ErrorEnvoltorioGemini("Modelo de texto de Gemini no especificado para formateo a Markdown.")

        texto_limpio = preprocesar_contenido_texto(contenido_texto)

        prompt_formateo = (
            "Eres un experto formateador de texto especializado en convertir texto crudo a Markdown limpio y bien estructurado. "
            "Tu tarea es transformar el contenido proporcionado a un formato Markdown. Sigue estas reglas estrictamente:\n"
            "1. Mantén el significado y la información factual del contenido original.\n"
            "2. Crea encabezados y estructura apropiados basados en la jerarquía del contenido.\n"
            "3. Formatea correctamente listas, tablas, bloques de código y otros elementos Markdown.\n"
            "4. Corrige errores tipográficos y de formato obvios mientras preservas el significado.\n"
            "5. NO añadas ningún contenido nuevo, introducciones, resúmenes o conclusiones.\n"
            "6. NO incluyas ningún meta-comentario o notas sobre el proceso de formateo.\n"
            "7. SOLO devuelve el contenido Markdown formateado correctamente, nada más.\n\n"
            "El objetivo es un Markdown limpio que represente con precisión el contenido original.\n\n"
            "Texto a convertir:\n"
            f"{texto_limpio}"
        )

        try:
            registrador.info(f"Formateando texto a Markdown usando el modelo Gemini '{modelo_a_usar}'...")

            modelo_generativo = genai.GenerativeModel(modelo_a_usar, safety_settings=self._obtener_config_seguridad())
            respuesta = modelo_generativo.generate_content(prompt_formateo)

            contenido_markdown = ""
            if respuesta.parts:
                 contenido_markdown = "".join(part.text for part in respuesta.parts if hasattr(part, "text"))

            if not contenido_markdown and respuesta.prompt_feedback and respuesta.prompt_feedback.block_reason:
                registrador.error(f"Formateo a Markdown bloqueado por Gemini. Razón: {respuesta.prompt_feedback.block_reason_message}")
                raise ErrorEnvoltorioGemini(f"Formateo a Markdown bloqueado por Gemini: {respuesta.prompt_feedback.block_reason_message}")

            contenido_markdown_postprocesado = postprocesar_contenido_markdown(contenido_markdown)

            if contenido_markdown_postprocesado:
                registrador.info(f"Texto formateado a Markdown con Gemini exitosamente (longitud: {len(contenido_markdown_postprocesado)}).")
                if ruta_guardado:
                    guardar_markdown_en_archivo(contenido_markdown_postprocesado, ruta_guardado)
            else:
                registrador.warning("El formateo a Markdown con Gemini devolvió contenido vacío.")
            return contenido_markdown_postprocesado
        except Exception as e:
            registrador.exception(f"Error formateando texto a Markdown con modelo Gemini '{modelo_a_usar}': {e}")
            raise ErrorEnvoltorioGemini(f"Falló el formateo de texto a Markdown con Gemini: {e}") from e

[end of entrenai_refactor/nucleo/ia/envoltorio_gemini.py]
