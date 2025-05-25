import os
import re
from datetime import datetime
from typing import List, Optional, Dict

from google import genai
from google.genai import types

from src.entrenai.config import GeminiConfig
from src.entrenai.config.logger import get_logger

logger = get_logger(__name__)

# Common error messages as constants
CLIENT_NOT_INITIALIZED = "Cliente Gemini no inicializado."
API_KEY_NOT_CONFIGURED = "API Key de Gemini no configurada."


class GeminiWrapperError(Exception):
    """Excepción personalizada para errores de GeminiWrapper."""

    pass


class GeminiWrapper:
    """Wrapper para interactuar con la API de Google Gemini."""

    def __init__(self, config: GeminiConfig):
        """Inicializa el wrapper con la configuración proporcionada."""
        self.config = config
        self.client = None
        try:
            if config.api_key:
                self.client = genai.Client(api_key=config.api_key)
                logger.info("Cliente Gemini inicializado exitosamente con la API Key.")
            else:
                logger.error(
                    "API Key de Gemini no configurada. GeminiWrapper no funcional."
                )
                raise GeminiWrapperError(API_KEY_NOT_CONFIGURED)
        except Exception as e:
            logger.error(f"Falló la inicialización del cliente Gemini: {e}")
            raise GeminiWrapperError(
                f"Falló la inicialización del cliente Gemini: {e}"
            ) from e

    def _get_safety_settings(self) -> Optional[List[Dict]]:
        """Obtiene la configuración de seguridad para las llamadas a la API."""
        if not self.config.safety_settings_enabled:
            # Configuración que desactiva los filtros de seguridad
            return [
                {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
                {
                    "category": "HARM_CATEGORY_SEXUALLY_EXPLICIT",
                    "threshold": "BLOCK_NONE",
                },
                {
                    "category": "HARM_CATEGORY_DANGEROUS_CONTENT",
                    "threshold": "BLOCK_NONE",
                },
            ]
        return None  # Usar configuración predeterminada de Gemini

    def generate_embedding(self, text: str, model: Optional[str] = None) -> List[float]:
        """Genera un embedding vectorial para un texto."""
        model_to_use = model or self.config.embedding_model

        try:
            if not self.client:
                raise GeminiWrapperError(CLIENT_NOT_INITIALIZED)

            # Realizar la solicitud de embedding
            response = self.client.models.embed_content(
                model=model_to_use,
                contents=[text],  # La API espera una lista de textos
                config=types.EmbedContentConfig(
                    output_dimensionality=self.config.embedding_dimension
                ),
            )

            # Extraer el vector de embedding
            if response and hasattr(response, "embeddings") and response.embeddings:
                # La nueva API devuelve embeddings en plural
                return response.embeddings[0].values

            # Error si no se encuentran valores válidos
            logger.error(
                f"La respuesta de embedding no contiene un vector válido: {response}"
            )
            raise GeminiWrapperError(
                "La respuesta de embedding no contiene un vector válido"
            )
        except Exception as e:
            logger.error(f"Error generando embedding con modelo '{model_to_use}': {e}")
            raise GeminiWrapperError(f"Falló la generación del embedding: {e}") from e

    def generate_chat_completion(
        self,
        prompt: str,
        model: Optional[str] = None,
        system_message: Optional[str] = None,
        context_chunks: Optional[List[str]] = None,
        stream: bool = False,
    ) -> str:
        """Genera una completación de chat (respuesta) basada en un prompt."""
        model_to_use = model or self.config.text_model

        try:
            if not self.client:
                raise GeminiWrapperError(CLIENT_NOT_INITIALIZED)

            # Construir el prompt completo
            if context_chunks:
                context_str = "\n\n".join(context_chunks)
                full_prompt = f"Contexto:\n{context_str}\n\nPregunta: {prompt}"
            else:
                full_prompt = prompt

            # Preparar mensajes y configuración
            contents = []

            # Si hay un mensaje de sistema, lo añadimos como system_instruction
            system_instruction = system_message

            # Añadir el prompt principal como mensaje del usuario
            contents.append(full_prompt)

            # Configurar opciones de generación
            generation_config = types.GenerateContentConfig(
                safety_settings=self._get_safety_settings(),
                system_instruction=system_instruction,
            )

            # Enviar mensaje y obtener respuesta
            response = self.client.models.generate_content(
                model=model_to_use, contents=contents, config=generation_config
            )

            # Procesar respuesta
            if stream:
                # Implementar manejo de streaming en versiones futuras
                logger.warning(
                    "El streaming no está completamente implementado. "
                    "Devolviendo respuesta completa."
                )

            # Extraer contenido de la respuesta
            response_content = response.text

            if not response_content:
                logger.warning("La completación de chat devolvió contenido vacío.")
                response_content = ""

            return response_content
        except Exception as e:
            logger.error(
                f"Error generando completación de chat con modelo '{model_to_use}': {e}"
            )
            raise GeminiWrapperError(
                f"Falló la generación de completación de chat: {e}"
            ) from e

    def _preprocess_text_content(self, text: str) -> str:
        """
        Preprocesa el texto de entrada antes de enviarlo al LLM.
        Elimina cualquier sección <think> y otros metadatos no deseados.

        Args:
            text: El texto de entrada crudo.

        Returns:
            Texto limpio listo para la conversión a markdown.
        """

        cleaned_text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)

        cleaned_text = re.sub(r"^\s*\[.*?\]\s*$", "", cleaned_text, flags=re.MULTILINE)
        cleaned_text = re.sub(
            r"^\s*#\s*metadata:.*$", "", cleaned_text, flags=re.MULTILINE
        )

        return cleaned_text.strip()

    def _postprocess_markdown_content(self, markdown: str) -> str:
        """
        Performs final cleanup on the generated markdown.

        Args:
            markdown: The markdown content returned by the LLM

        Returns:
            Markdown limpio y bien formateado.
        """
        cleaned_markdown = re.sub(r"<think>.*?</think>", "", markdown, flags=re.DOTALL)

        cleaned_markdown = re.sub(
            r"^.*?(#|---|```)", r"\1", cleaned_markdown, flags=re.DOTALL, count=1
        )

        cleaned_markdown = re.sub(r"(#{1,6}.*?)(\n(?!\n))", r"\1\n\n", cleaned_markdown)

        cleaned_markdown = re.sub(
            r"```(\w*)\n?([^`]+)```", r"```\1\n\2\n```", cleaned_markdown
        )

        return cleaned_markdown.strip()

    def format_to_markdown(
        self,
        text_content: str,
        model: Optional[str] = None,
        save_path: Optional[str] = None,
    ) -> str:
        """
        Convierte el contenido de texto dado a un formato Markdown bien estructurado.
        Maneja varios formatos de entrada (texto plano, salida OCR, etc.) y asegura
        una estructura markdown adecuada preservando el significado del contenido original.

        Args:
            text_content: El texto crudo a convertir a markdown.
            model: Sobrescritura opcional para el modelo de markdown a usar.
            save_path: Ruta opcional para guardar el archivo markdown resultante. Puede ser:
                       - Una ruta de archivo completa (terminando en .md o no).
                       - Una ruta de directorio (generará un nombre de archivo con marca de tiempo).
                       - None (por defecto, no guardará en archivo).

        Returns:
            El texto markdown formateado.
        """
        model_to_use = model or self.config.text_model

        # Preprocesar texto de entrada para limpiarlo
        cleaned_text = self._preprocess_text_content(text_content)

        # Crear un prompt para formatear a Markdown
        format_instruction = (
            "Eres un experto formateador de texto especializado en convertir texto crudo a Markdown limpio. "
            "Tu tarea es transformar el contenido dado a un formato Markdown estructurado adecuadamente. Sigue estas reglas estrictamente:\n\n"
            "1. Mantén el significado y la información factual del contenido original.\n"
            "2. Crea encabezados y estructura apropiados basados en la jerarquía del contenido.\n"
            "3. Formatea correctamente listas, tablas, bloques de código y otros elementos.\n"
            "4. Corrige errores tipográficos y de formato obvios mientras preservas el significado.\n"
            "5. NO añadas ningún contenido nuevo, introducciones, resúmenes o conclusiones.\n"
            "6. NO incluyas ningún meta-comentario o notas sobre el proceso de formateo.\n"
            "7. NO incluyas ningún texto encerrado en etiquetas <think> o metadatos similares.\n"
            "8. SOLO devuelve el contenido Markdown formateado correctamente, nada más.\n\n"
            "El objetivo es un Markdown limpio y bien estructurado que represente con precisión el contenido original."
        )

        try:
            if not self.client:
                raise GeminiWrapperError(CLIENT_NOT_INITIALIZED)

            # Crear mensaje con la instrucción y el texto a formatear
            user_prompt = (
                f"{format_instruction}\n\n"
                "Convierte el siguiente texto a formato Markdown bien estructurado. "
                "Mantén toda la información pero mejora la presentación:\n\n"
                f"{cleaned_text}"
            )

            # Configurar generación de contenido
            generation_config = types.GenerateContentConfig(
                safety_settings=self._get_safety_settings()
            )

            # Enviar mensaje como entrada directa
            response = self.client.models.generate_content(
                model=model_to_use, contents=user_prompt, config=generation_config
            )

            # Extraer y procesar el markdown
            markdown_content = response.text

            # Procesar el resultado con postprocesamiento
            markdown_content = self._postprocess_markdown_content(markdown_content)

            if not markdown_content:
                logger.warning("El formateo a Markdown devolvió contenido vacío.")
                markdown_content = ""

            # Guardar a archivo si se proporciona una ruta
            if save_path and markdown_content:
                self._save_markdown_to_file(markdown_content, save_path)

            return markdown_content
        except Exception as e:
            logger.error(
                f"Error formateando texto a Markdown con modelo '{model_to_use}': {e}"
            )
            raise GeminiWrapperError(
                f"Falló el formateo de texto a Markdown: {e}"
            ) from e

    def _save_markdown_to_file(self, markdown_content: str, save_path: str) -> None:
        """Guarda el contenido Markdown en un archivo."""
        try:
            # Create directory if it doesn't exist
            os.makedirs(os.path.dirname(os.path.abspath(save_path)), exist_ok=True)

            # If save_path is a directory, generate a filename based on timestamp
            if os.path.isdir(save_path):
                filename = f"markdown_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
                full_path = os.path.join(save_path, filename)
            else:
                # Ensure file has .md extension
                if not save_path.endswith(".md"):
                    save_path += ".md"
                full_path = save_path

            # Write content to file usando modo binario para preservar codificación
            with open(full_path, "wb") as f:
                f.write(markdown_content.encode("utf-8"))

            logger.info(f"Contenido Markdown guardado en {full_path}")
        except Exception as e:
            logger.error(f"Error guardando Markdown en {save_path}: {e}")
            # No lanzamos excepción porque el guardado es secundario al formateo
