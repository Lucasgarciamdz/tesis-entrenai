from pathlib import Path
from typing import List, Optional, Dict, Any

from google import genai
from google.generativeai import types as tipos_google_genai # Renombrado para evitar conflicto y por claridad

from entrenai_refactor.config.configuracion import configuracion_global
from entrenai_refactor.config.registrador import obtener_registrador
from entrenai_refactor.nucleo.ia.utilidades_comunes_ia import (
    postprocesar_contenido_markdown,
    preprocesar_contenido_texto,
    guardar_markdown_en_archivo,
)

registrador = obtener_registrador(__name__)

MENSAJE_CLIENTE_NO_INICIALIZADO_GEMINI = "El cliente de Google Gemini no ha sido inicializado correctamente."
MENSAJE_CLAVE_API_NO_CONFIGURADA_GEMINI = "La clave API de Google Gemini no está configurada en el entorno."

class ErrorEnvoltorioGemini(Exception):
    """Excepción personalizada para errores específicos del EnvoltorioGemini."""
    def __init__(self, mensaje: str, error_original: Optional[Exception] = None):
        super().__init__(mensaje)
        self.error_original = error_original
        registrador.debug(f"Excepción ErrorEnvoltorioGemini creada: {mensaje}, Original: {error_original}")

    def __str__(self):
        if self.error_original:
            return f"{super().__str__()} (Error original: {type(self.error_original).__name__}: {str(self.error_original)})"
        return super().__str__()

class EnvoltorioGemini:
    """
    Envoltorio para interactuar con la API de Google Gemini.
    Gestiona la configuración, generación de embeddings, completaciones de chat y formateo de texto.
    """

    def __init__(self):
        self.config_gemini = configuracion_global.gemini
        # El "cliente" de Gemini se configura globalmente a través de genai.configure()
        # No se instancia un objeto cliente como en otras librerías.

        registrador.info("Inicializando EnvoltorioGemini...")
        if not self.config_gemini.clave_api_gemini: # CAMBIADO
            registrador.error(MENSAJE_CLAVE_API_NO_CONFIGURADA_GEMINI)
            raise ErrorEnvoltorioGemini(MENSAJE_CLAVE_API_NO_CONFIGURADA_GEMINI)

        try:
            genai.configure(api_key=self.config_gemini.clave_api_gemini) # CAMBIADO
            # Se podría realizar una llamada de prueba, como listar modelos, para verificar la configuración.
            # Ejemplo: list(genai.list_models())
            registrador.info("Google Gemini SDK configurado exitosamente con la clave API.")
        except Exception as e_config:
            registrador.error(f"Falló la configuración del SDK de Google Gemini: {e_config}")
            raise ErrorEnvoltorioGemini(f"Falló la configuración del SDK de Gemini: {e_config}", e_config)

    def _obtener_configuracion_de_seguridad(self) -> Optional[List[Dict[str, Any]]]:
        """
        Construye la configuración de seguridad para las llamadas a la API de Gemini.
        Si la seguridad está deshabilitada en la configuración, devuelve umbrales para bloquear nada.
        """
        if not self.config_gemini.seguridad_gemini_habilitada: # CAMBIADO
            registrador.debug("Configuración de seguridad de Gemini deshabilitada. Se aplicarán umbrales BLOCK_NONE.")
            # Referencia: https://ai.google.dev/docs/safety_setting_gemini
            return [
                {"category": tipos_google_genai.HarmCategory.HARM_CATEGORY_HARASSMENT, "threshold": tipos_google_genai.HarmBlockThreshold.BLOCK_NONE},
                {"category": tipos_google_genai.HarmCategory.HARM_CATEGORY_HATE_SPEECH, "threshold": tipos_google_genai.HarmBlockThreshold.BLOCK_NONE},
                {"category": tipos_google_genai.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT, "threshold": tipos_google_genai.HarmBlockThreshold.BLOCK_NONE},
                {"category": tipos_google_genai.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT, "threshold": tipos_google_genai.HarmBlockThreshold.BLOCK_NONE},
            ]
        registrador.debug("Utilizando configuración de seguridad predeterminada de Gemini.")
        return None # Usar la configuración de seguridad predeterminada de la API

    def generar_embedding_de_texto(self, texto_entrada: str, nombre_modelo_embedding: Optional[str] = None) -> List[float]:
        """Genera un vector de embedding para un texto dado utilizando un modelo de Gemini."""
        modelo_seleccionado = nombre_modelo_embedding or self.config_gemini.modelo_embedding_gemini # CAMBIADO
        if not modelo_seleccionado:
            registrador.error("No se ha especificado un modelo de embedding de Gemini para usar.")
            raise ErrorEnvoltorioGemini("Modelo de embedding de Gemini no especificado.")

        registrador.debug(f"Generando embedding con modelo Gemini '{modelo_seleccionado}' para texto de longitud {len(texto_entrada)}.")
        try:
            texto_preprocesado_para_embedding = preprocesar_contenido_texto(texto_entrada)

            # La API de embeddings de Gemini espera 'model' (ej. 'models/embedding-001') y 'content'.
            respuesta_embedding = genai.embed_content(model=modelo_seleccionado, content=texto_preprocesado_para_embedding)

            if "embedding" in respuesta_embedding and isinstance(respuesta_embedding["embedding"], list):
                registrador.info(f"Embedding generado exitosamente con modelo '{modelo_seleccionado}'. Dimensión: {len(respuesta_embedding['embedding'])}.")
                return respuesta_embedding["embedding"]
            else:
                registrador.error(f"La respuesta de la API de embedding de Gemini no contiene un vector válido. Respuesta: {respuesta_embedding}")
                raise ErrorEnvoltorioGemini("Respuesta de embedding de Gemini no contiene un vector válido.")
        except Exception as e_embedding:
            registrador.error(f"Error al generar embedding con modelo Gemini '{modelo_seleccionado}': {e_embedding}")
            raise ErrorEnvoltorioGemini(f"Falló la generación del embedding con Gemini: {e_embedding}", e_embedding)

    def generar_respuesta_de_chat(
        self,
        prompt_usuario: str,
        nombre_modelo_chat: Optional[str] = None,
        mensaje_de_sistema: Optional[str] = None,
        historial_chat_previo: Optional[List[Dict[str, str]]] = None, # Formato: [{"role": "user/model", "parts": ["texto"]}]
        fragmentos_de_contexto: Optional[List[str]] = None,
        # stream: bool = False # El streaming aún no está implementado en este envoltorio
    ) -> str:
        """
        Genera una respuesta de chat utilizando un modelo de Gemini,
        opcionalmente con un mensaje de sistema, historial de chat y contexto adicional.
        """
        modelo_seleccionado = nombre_modelo_chat or self.config_gemini.modelo_texto_gemini # CAMBIADO
        if not modelo_seleccionado:
            registrador.error("No se ha especificado un modelo de texto/chat de Gemini para usar.")
            raise ErrorEnvoltorioGemini("Modelo de texto/chat de Gemini no especificado.")

        registrador.debug(f"Generando completación de chat con modelo Gemini '{modelo_seleccionado}'.")
        try:
            # Construir el historial de 'contents' para la API de Gemini
            # Referencia: https://ai.google.dev/docs/gemini_api_overview#chat_conversations
            contenido_peticion_api = []
            if historial_chat_previo:
                for item_historial in historial_chat_previo:
                    # Asegurar que el formato sea correcto para la API de Gemini
                    if "role" in item_historial and "parts" in item_historial:
                         contenido_peticion_api.append(item_historial)
                    else:
                        registrador.warning(f"Item de historial de chat malformado omitido: {item_historial}")


            # Añadir el contexto y el prompt actual del usuario
            prompt_final_con_contexto = prompt_usuario
            if fragmentos_de_contexto:
                contexto_como_string = "\n\n".join(fragmentos_de_contexto)
                prompt_final_con_contexto = f"Contexto relevante:\n{contexto_como_string}\n\nPregunta del usuario: {prompt_usuario}"

            contenido_peticion_api.append({"role": "user", "parts": [prompt_final_con_contexto]})

            opciones_config_generacion = tipos_google_genai.GenerationConfig(candidate_count=1) # Solicitar una sola respuesta candidata
            configuracion_seguridad_api = self._obtener_configuracion_de_seguridad()

            # Crear el modelo generativo con la instrucción de sistema si se proporciona
            modelo_generativo_gemini = genai.GenerativeModel(
                model_name=modelo_seleccionado,
                safety_settings=configuracion_seguridad_api,
                system_instruction=mensaje_de_sistema if mensaje_de_sistema else None
            )

            # Iniciar una sesión de chat (si hay historial) o generar contenido directamente
            # Por simplicidad, si hay historial, se pasa todo en 'contents'.
            # Para conversaciones más largas y con estado, se usaría model.start_chat(history=...).

            registrador.debug(f"Enviando a Gemini (modelo {modelo_seleccionado}): Instrucción sistema: '{mensaje_de_sistema if mensaje_de_sistema else 'Ninguna'}', Contenido: {json.dumps(contenido_peticion_api, indent=2, ensure_ascii=False)}")

            respuesta_gemini = modelo_generativo_gemini.generate_content(
                contents=contenido_peticion_api,
                generation_config=opciones_config_generacion,
                # stream=stream # El streaming requeriría un manejo diferente del iterador de respuesta
            )

            # Extraer el contenido de texto de la respuesta
            contenido_texto_respuesta = ""
            if respuesta_gemini.parts:
                 contenido_texto_respuesta = "".join(part.text for part in respuesta_gemini.parts if hasattr(part, "text"))

            # Verificar si el contenido fue bloqueado o la respuesta está vacía
            if not contenido_texto_respuesta and respuesta_gemini.prompt_feedback and respuesta_gemini.prompt_feedback.block_reason:
                mensaje_bloqueo = respuesta_gemini.prompt_feedback.block_reason_message or str(respuesta_gemini.prompt_feedback.block_reason)
                registrador.error(f"La generación de contenido fue bloqueada por Gemini. Razón: {mensaje_bloqueo}")
                raise ErrorEnvoltorioGemini(f"Contenido bloqueado por Gemini: {mensaje_bloqueo}")

            if not contenido_texto_respuesta:
                registrador.warning(f"La completación de chat del modelo Gemini '{modelo_seleccionado}' devolvió contenido vacío.")

            registrador.info(f"Respuesta de chat generada exitosamente con modelo '{modelo_seleccionado}'.")
            return contenido_texto_respuesta

        except Exception as e_chat:
            registrador.exception(f"Error al generar completación de chat con modelo Gemini '{modelo_seleccionado}': {e_chat}")
            raise ErrorEnvoltorioGemini(f"Falló la generación de completación de chat con Gemini: {e_chat}", e_chat)

    def convertir_texto_a_markdown(
        self,
        texto_original: str,
        nombre_modelo_formateo: Optional[str] = None,
        ruta_archivo_guardado: Optional[Path] = None
    ) -> str:
        """Formatea un texto crudo a formato Markdown utilizando un modelo de Gemini."""
        modelo_seleccionado = nombre_modelo_formateo or self.config_gemini.modelo_texto_gemini # CAMBIADO
        if not modelo_seleccionado:
            registrador.error("No se ha especificado un modelo de texto de Gemini para el formateo a Markdown.")
            raise ErrorEnvoltorioGemini("Modelo de texto de Gemini no especificado para formateo a Markdown.")

        texto_limpio_para_formateo = preprocesar_contenido_texto(texto_original)
        registrador.info(f"Formateando texto a Markdown con modelo Gemini '{modelo_seleccionado}'. Longitud original: {len(texto_original)}, preprocesado: {len(texto_limpio_para_formateo)}.")

        prompt_instruccion_formateo = (
            "Eres un experto formateador de texto especializado en convertir texto crudo a Markdown limpio y bien estructurado.\n"
            "Tu tarea es transformar el siguiente contenido proporcionado a un formato Markdown. Sigue estas reglas estrictamente:\n"
            "1. Mantén el significado y la información factual del contenido original.\n"
            "2. Crea encabezados (#, ##, ###) y estructura apropiados basados en la jerarquía implícita del contenido.\n"
            "3. Formatea correctamente listas (numeradas y con viñetas), tablas (si son detectables), bloques de código (si aplica), y otros elementos Markdown (negritas, cursivas, etc.).\n"
            "4. Corrige errores tipográficos y de formato obvios (ej. múltiples espacios) mientras preservas el significado.\n"
            "5. NO añadas ningún contenido nuevo, introducciones, resúmenes, conclusiones o información que no esté en el texto original.\n"
            "6. NO incluyas ningún meta-comentario, notas sobre el proceso de formateo, o disculpas.\n"
            "7. SOLO devuelve el contenido Markdown formateado correctamente. Nada antes, nada después.\n\n"
            "El objetivo es un Markdown limpio que represente con precisión el contenido original, listo para ser usado directamente.\n\n"
            "Texto a convertir:\n"
            f"\"\"\"\n{texto_limpio_para_formateo}\n\"\"\""
        )

        try:
            modelo_generativo_gemini = genai.GenerativeModel(
                modelo_seleccionado,
                safety_settings=self._obtener_configuracion_de_seguridad()
            )
            respuesta_formateo = modelo_generativo_gemini.generate_content(prompt_instruccion_formateo)

            contenido_markdown_generado = ""
            if respuesta_formateo.parts:
                 contenido_markdown_generado = "".join(part.text for part in respuesta_formateo.parts if hasattr(part, "text"))

            if not contenido_markdown_generado and respuesta_formateo.prompt_feedback and respuesta_formateo.prompt_feedback.block_reason:
                mensaje_bloqueo = respuesta_formateo.prompt_feedback.block_reason_message or str(respuesta_formateo.prompt_feedback.block_reason)
                registrador.error(f"La tarea de formateo a Markdown fue bloqueada por Gemini. Razón: {mensaje_bloqueo}")
                raise ErrorEnvoltorioGemini(f"Formateo a Markdown bloqueado por Gemini: {mensaje_bloqueo}")

            contenido_markdown_final = postprocesar_contenido_markdown(contenido_markdown_generado)

            if contenido_markdown_final:
                registrador.info(f"Texto formateado a Markdown con Gemini exitosamente (longitud: {len(contenido_markdown_final)}).")
                if ruta_archivo_guardado:
                    guardar_markdown_en_archivo(contenido_markdown_final, ruta_archivo_guardado) # Utilidad común para guardar
            else:
                registrador.warning(f"El formateo a Markdown con modelo Gemini '{modelo_seleccionado}' devolvió contenido vacío.")

            return contenido_markdown_final

        except Exception as e_formateo:
            registrador.exception(f"Error al formatear texto a Markdown con modelo Gemini '{modelo_seleccionado}': {e_formateo}")
            raise ErrorEnvoltorioGemini(f"Falló el formateo de texto a Markdown con Gemini: {e_formateo}", e_formateo)

[end of entrenai_refactor/nucleo/ia/envoltorio_gemini_refactorizado.py]
