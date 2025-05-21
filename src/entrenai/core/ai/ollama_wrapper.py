import ollama
from typing import List, Optional, Any

from src.entrenai.config import OllamaConfig
from src.entrenai.config.logger import get_logger

logger = get_logger(__name__)

# Common error messages as constants
CLIENT_NOT_INITIALIZED = "Cliente Ollama no inicializado."


class OllamaWrapperError(Exception):
    """Custom exception for OllamaWrapper errors."""

    pass


class OllamaWrapper:
    """
    Wrapper for interacting with Ollama API.
    """

    def __init__(self, config: OllamaConfig):
        self.config = config
        self.client: Optional[ollama.Client] = None
        try:
            if config.host:
                self.client = ollama.Client(host=config.host)
                # Test connection by listing local models
                self.client.list()
                logger.info(
                    f"Cliente Ollama inicializado y conectado al host: {config.host}"
                )
                self._ensure_models_available()  # Check for specific models
            else:
                logger.error(
                    "Host de Ollama no configurado. OllamaWrapper no será funcional."
                )
                raise OllamaWrapperError("Host de Ollama no configurado.")
        except Exception as e:
            logger.error(
                f"Falló la conexión o inicialización del cliente Ollama en {config.host}: {e}"
            )
            self.client = None
            # raise OllamaWrapperError(f"Failed to initialize Ollama client: {e}") from e

    def _ensure_models_available(self):
        """
        Verifica si los modelos configurados están disponibles en Ollama y registra una advertencia si no lo están.
        No intenta descargarlos automáticamente para evitar largos tiempos de inicio sin consentimiento del usuario.
        """
        if not self.client:
            return

        try:
            response = self.client.list()  # Get the ListResponse object

            # Get models from the response object
            available_models = []
            if hasattr(response, "models"):
                available_models = response.models

            # Extract model names - models have a 'model' attribute (not 'name')
            available_model_names = []
            for model in available_models:
                if hasattr(model, "model"):
                    available_model_names.append(model.model)

            required_models = {
                "embedding": self.config.embedding_model,
                "markdown": self.config.markdown_model,
                "qa": self.config.qa_model,
                "context": self.config.context_model,
            }

            for model_type, model_name in required_models.items():
                if not model_name:  # Skip if a model name is not configured
                    logger.info(
                        f"Modelo Ollama para {model_type} no está configurado. Omitiendo verificación."
                    )
                    continue

                base_model_name = model_name.split(":")[0]

                # Check if any available model starts with the base name
                is_present = any(
                    model.startswith(base_model_name) for model in available_model_names
                )

                if not is_present:
                    logger.warning(
                        f"Modelo Ollama para {model_type} ('{model_name}') "
                        f"no encontrado en los modelos disponibles: {available_model_names}. "
                        f"Por favor, asegúrese de que esté descargado usando 'ollama pull {model_name}'."
                    )
                else:
                    logger.info(
                        f"Modelo Ollama para {model_type} ('{model_name}') está disponible."
                    )

        except Exception as e:
            logger.error(f"Error al verificar los modelos Ollama disponibles: {e}")

    def generate_embedding(self, text: str, model: Optional[str] = None) -> List[float]:
        """
        Genera un embedding para el texto dado usando el modelo de embedding configurado.
        """
        if not self.client:
            logger.error(f"{CLIENT_NOT_INITIALIZED} No se puede generar el embedding.")
            raise OllamaWrapperError(CLIENT_NOT_INITIALIZED)

        model_to_use = model or self.config.embedding_model
        if not model_to_use:
            logger.error("Nombre del modelo de embedding no configurado.")
            raise OllamaWrapperError("Nombre del modelo de embedding no configurado.")
        try:
            response = self.client.embeddings(model=model_to_use, prompt=text)
            return response["embedding"]
        except Exception as e:
            logger.error(f"Error generando embedding con modelo '{model_to_use}': {e}")
            raise OllamaWrapperError(f"Falló la generación del embedding: {e}") from e

    def generate_chat_completion(
        self,
        prompt: str,
        model: Optional[str] = None,
        system_message: Optional[str] = None,
        context_chunks: Optional[List[str]] = None,  # For RAG
        stream: bool = False,
    ) -> str:
        """
        Genera una completación de chat (respuesta) para un prompt dado.
        Puede incluir un mensaje de sistema y chunks de contexto para RAG.
        """
        if not self.client:
            logger.error(
                f"{CLIENT_NOT_INITIALIZED} No se puede generar la completación de chat."
            )
            raise OllamaWrapperError(CLIENT_NOT_INITIALIZED)

        model_to_use = model or self.config.qa_model
        if not model_to_use:
            logger.error("Nombre del modelo QA no configurado.")
            raise OllamaWrapperError("Nombre del modelo QA no configurado.")

        messages = []
        if system_message:
            messages.append({"role": "system", "content": system_message})

        if context_chunks:
            context_str = "\n\n".join(context_chunks)
            full_prompt = f"Contexto:\n{context_str}\n\nPregunta: {prompt}"  # User-facing, so Spanish
            messages.append({"role": "user", "content": full_prompt})
        else:
            messages.append({"role": "user", "content": prompt})

        try:
            if stream:
                logger.warning(
                    "El streaming no está completamente implementado en este wrapper básico. Devolviendo respuesta completa."
                )
                # Implement streaming in a future version

            response = self.client.chat(
                model=model_to_use, messages=messages, stream=False
            )
            # Handle both dict response and object response with message attribute
            response_content = ""
            if (
                isinstance(response, dict)
                and "message" in response
                and "content" in response["message"]
            ):
                response_content = str(response["message"]["content"])
            elif hasattr(response, "message") and hasattr(response.message, "content"):
                response_content = str(response.message.content)
            else:
                raise OllamaWrapperError(
                    "Formato de respuesta inesperado de la API de Ollama"
                )

            # Ensure we return a non-empty string
            if not response_content:
                logger.warning("La completación de chat devolvió contenido vacío.")
                response_content = ""

            return response_content

        except Exception as e:
            logger.error(
                f"Error generando completación de chat con modelo '{model_to_use}': {e}"
            )
            raise OllamaWrapperError(
                f"Falló la generación de la completación de chat: {e}"
            ) from e

    def _extract_markdown_content(self, response: Any) -> str:
        """
        Extrae contenido markdown de la respuesta de la API de Ollama.
        """
        if (
            isinstance(response, dict)
            and "message" in response
            and "content" in response["message"]
        ):
            return str(response["message"]["content"])
        elif hasattr(response, "message"):
            message = getattr(response, "message")
            if hasattr(message, "content"):
                return str(message.content)

        # If we got here, we couldn't extract the content
        raise OllamaWrapperError("Formato de respuesta inesperado de la API de Ollama")

    def _save_markdown_to_file(self, markdown_content: str, save_path: str) -> None:
        """
        Guarda contenido markdown en un archivo en la ruta especificada.
        """
        try:
            import os
            from datetime import datetime

            # Create directory if it doesn't exist
            os.makedirs(os.path.dirname(save_path), exist_ok=True)

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
            logger.error(f"Falló al guardar contenido Markdown en {save_path}: {e}")

    def format_to_markdown(
        self,
        text_content: str,
        model: Optional[str] = None,
        save_path: Optional[str] = None,
    ) -> str:
        """
        Convierte el contenido de texto dado a un formato Markdown bien estructurado usando un LLM.
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
        if not self.client:
            logger.error(f"{CLIENT_NOT_INITIALIZED} No se puede formatear a Markdown.")
            raise OllamaWrapperError(CLIENT_NOT_INITIALIZED)

        model_to_use = model or self.config.markdown_model
        if not model_to_use:
            logger.error("Nombre del modelo de formateo a Markdown no configurado.")
            raise OllamaWrapperError(
                "Nombre del modelo de formateo a Markdown no configurado."
            )

        cleaned_text = self._preprocess_text_content(text_content)

        system_prompt = (
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

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": cleaned_text},
        ]

        try:
            logger.info(
                f"Formateando texto a Markdown usando el modelo '{model_to_use}'..."
            )
            response = self.client.chat(
                model=model_to_use, messages=messages, stream=False
            )

            markdown_content = self._extract_markdown_content(response)
            markdown_content = self._postprocess_markdown_content(markdown_content)

            if markdown_content:
                logger.info(
                    f"Texto formateado a Markdown exitosamente (longitud: {len(markdown_content)})."
                )
                if save_path:
                    self._save_markdown_to_file(markdown_content, save_path)
            else:
                logger.warning("El formateo a Markdown devolvió contenido vacío.")
                markdown_content = ""

            return markdown_content
        except Exception as e:
            logger.error(
                f"Error formateando texto a Markdown con modelo '{model_to_use}': {e}"
            )
            raise OllamaWrapperError(
                f"Falló el formateo de texto a Markdown: {e}"
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
        import re

        # Remove <think>...</think> blocks
        cleaned_text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)

        # Remove other common metadata patterns that might appear in OCR or extracted text
        cleaned_text = re.sub(
            r"^\s*\[.*?\]\s*$", "", cleaned_text, flags=re.MULTILINE
        )  # Remove [metadata] lines
        cleaned_text = re.sub(
            r"^\s*#\s*metadata:.*$", "", cleaned_text, flags=re.MULTILINE
        )  # Remove #metadata lines

        return cleaned_text.strip()

    def _postprocess_markdown_content(self, markdown: str) -> str:
        """
        Performs final cleanup on the generated markdown.

        Args:
            markdown: The markdown content returned by the LLM

        Returns:
            Markdown limpio y bien formateado.
        """
        import re

        # Remove any lingering <think> tags that might have been generated
        cleaned_markdown = re.sub(r"<think>.*?</think>", "", markdown, flags=re.DOTALL)

        # Remove any "I've converted this to markdown..." explanatory text at the beginning
        cleaned_markdown = re.sub(
            r"^.*?(#|---|```)", r"\1", cleaned_markdown, flags=re.DOTALL, count=1
        )

        # Fix common formatting issues
        # Ensure proper spacing after headings
        cleaned_markdown = re.sub(r"(#{1,6}.*?)(\n(?!\n))", r"\1\n\n", cleaned_markdown)

        # Ensure code blocks are properly formatted with newlines
        cleaned_markdown = re.sub(
            r"```(\w*)\n?([^`]+)```", r"```\1\n\2\n```", cleaned_markdown
        )

        return cleaned_markdown.strip()

    # add_context_to_chunk será manejado por EmbeddingManager por ahora.
