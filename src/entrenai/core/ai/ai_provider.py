from typing import Optional, Union, Dict, Any, List, cast

from src.entrenai.core.ai.ollama_wrapper import OllamaWrapper, OllamaWrapperError
from src.entrenai.core.ai.gemini_wrapper import GeminiWrapper, GeminiWrapperError
from src.entrenai.config import (
    BaseConfig,
    OllamaConfig,
    GeminiConfig,
    ollama_config,
    gemini_config,
)
from src.entrenai.config.logger import get_logger

logger = get_logger(__name__)

class AIProviderError(Exception):
    """Excepción personalizada para errores relacionados con el proveedor de IA."""

    pass


class AIProvider:
    """Fábrica para instancias de wrappers de IA según la configuración."""

    def __init__(self, base_config: BaseConfig):
        self.config = base_config
        self.ai_provider = base_config.ai_provider
        self._wrapper: Union[OllamaWrapper, GeminiWrapper, None] = None
        self._initialize_wrapper()

    def _initialize_wrapper(self):
        """Inicializa el wrapper apropiado según la configuración."""
        if self.ai_provider == "ollama":
            try:
                self._wrapper = OllamaWrapper(config=ollama_config)
            except OllamaWrapperError as e:
                logger.error(f"Error inicializando OllamaWrapper: {e}")
                raise AIProviderError(f"Error inicializando OllamaWrapper: {e}") from e
        elif self.ai_provider == "gemini":
            try:
                self._wrapper = GeminiWrapper(config=gemini_config)
            except GeminiWrapperError as e:
                logger.error(f"Error inicializando GeminiWrapper: {e}")
                raise AIProviderError(f"Error inicializando GeminiWrapper: {e}") from e
        else:
            msg = (
                f"Proveedor de IA no válido: {self.ai_provider}. "
                f"Opciones válidas: 'ollama', 'gemini'"
            )
            logger.error(msg)
            raise AIProviderError(msg)

    def get_ai_wrapper(self) -> Union[OllamaWrapper, GeminiWrapper]:
        """Retorna el wrapper apropiado según la configuración."""
        if not self._wrapper:
            self._initialize_wrapper()

        return cast(Union[OllamaWrapper, GeminiWrapper], self._wrapper)

    def generate_embedding(self, text: str, model: Optional[str] = None) -> List[float]:
        """Genera un embedding vectorial para un texto usando el wrapper actual."""
        wrapper = self.get_ai_wrapper()
        try:
            return wrapper.generate_embedding(text=text, model=model)
        except (OllamaWrapperError, GeminiWrapperError) as e:
            logger.error(f"Error generando embedding: {e}")
            raise AIProviderError(f"Error generando embedding: {e}") from e

    def generate_chat_completion(
        self,
        prompt: str,
        model: Optional[str] = None,
        system_message: Optional[str] = None,
        context_chunks: Optional[List[str]] = None,
        stream: bool = False,
    ) -> str:
        """Genera una completación de chat (respuesta) usando el wrapper actual."""
        wrapper = self.get_ai_wrapper()
        try:
            return wrapper.generate_chat_completion(
                prompt=prompt,
                model=model,
                system_message=system_message,
                context_chunks=context_chunks,
                stream=stream,
            )
        except (OllamaWrapperError, GeminiWrapperError) as e:
            error_msg = f"Error generando completación de chat: {e}"
            logger.error(error_msg)
            raise AIProviderError(error_msg) from e

    def format_to_markdown(
        self,
        text_content: str,
        model: Optional[str] = None,
        save_path: Optional[str] = None,
    ) -> str:
        """Formatea el texto a Markdown usando el wrapper actual."""
        wrapper = self.get_ai_wrapper()
        try:
            return wrapper.format_to_markdown(
                text_content=text_content, model=model, save_path=save_path
            )
        except (OllamaWrapperError, GeminiWrapperError) as e:
            error_msg = f"Error formateando texto a Markdown: {e}"
            logger.error(error_msg)
            raise AIProviderError(error_msg) from e

    def preprocess_text_content(self, text: str) -> str:
        """
        Preprocesa el texto eliminando etiquetas <think> y otros metadatos,
        delegando al método correspondiente del wrapper actual.
        """
        wrapper = self.get_ai_wrapper()
        if hasattr(wrapper, "_preprocess_text_content"):
            return wrapper._preprocess_text_content(text)
        else:
            # Implementación básica por si un wrapper no tiene el método
            import re

            cleaned_text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
            return cleaned_text.strip()


def get_ai_wrapper(
    ai_provider: Optional[str] = None,
    provider_config: Optional[Dict[str, Any]] = None,
) -> Union[OllamaWrapper, GeminiWrapper]:
    """Función auxiliar para obtener un wrapper de IA según el proveedor.

    Args:
        ai_provider: Proveedor ('ollama' o 'gemini').
            Si es None, usa la configuración global.
        provider_config: Configuración personalizada para el proveedor.
            Si es None, usa la configuración global.

    Returns:
        Un wrapper de IA adecuado para el proveedor especificado.
    """
    from src.entrenai.config import base_config

    # Usar proveedor de la configuración si no se especifica uno
    provider = ai_provider or base_config.ai_provider

    # Crear instancia según el proveedor
    if provider == "ollama":
        if provider_config:
            config = OllamaConfig()
            for key, value in provider_config.items():
                if hasattr(config, key):
                    setattr(config, key, value)
            return OllamaWrapper(config=config)
        return OllamaWrapper(config=ollama_config)
    elif provider == "gemini":
        if provider_config:
            config = GeminiConfig()
            for key, value in provider_config.items():
                if hasattr(config, key):
                    setattr(config, key, value)
            return GeminiWrapper(config=config)
        return GeminiWrapper(config=gemini_config)
    else:
        msg = (
            f"Proveedor de IA no válido: {provider}. "
            f"Opciones válidas: 'ollama', 'gemini'"
        )
        logger.error(msg)
        raise AIProviderError(msg)
