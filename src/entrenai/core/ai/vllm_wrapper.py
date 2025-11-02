from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

from src.entrenai.config import VLLMConfig
from src.entrenai.config.logger import get_logger
from src.entrenai.core.ai.common_utils import (
    postprocess_markdown_content,
    preprocess_text_content,
    save_markdown_to_file,
)

logger = get_logger(__name__)

CLIENT_NOT_INITIALIZED = "Cliente vLLM no inicializado."


class VLLMWrapperError(Exception):
    """Custom exception for vLLM wrapper related errors."""

    pass


class VLLMWrapper:
    """Wrapper for interacting with one or more vLLM OpenAI-compatible servers."""

    def __init__(self, config: VLLMConfig):
        self.config = config

        if not config.base_url:
            raise VLLMWrapperError(
                "VLLM_BASE_URL no está configurado. El wrapper no será funcional."
            )

        self.chat_client = self._build_client(config.base_url, config.api_key)
        embed_base_url = config.embedding_base_url or config.base_url
        if embed_base_url.rstrip("/") == config.base_url.rstrip("/"):
            self.embedding_client = self.chat_client
        else:
            self.embedding_client = self._build_client(embed_base_url, config.api_key)

        self._available_models: Dict[str, set[str]] = {}

        # Verificar modelos esperados al inicializar
        self._ensure_model_available(config.chat_model, self.chat_client)
        if config.embedding_model:
            self._ensure_model_available(config.embedding_model, self.embedding_client)
        if config.markdown_model:
            self._ensure_model_available(config.markdown_model, self.chat_client)

    @staticmethod
    def _build_client(base_url: str, api_key: Optional[str]) -> httpx.Client:
        headers: Dict[str, str] = {}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        return httpx.Client(
            base_url=base_url.rstrip("/"),
            timeout=None,
            headers=headers,
        )

    def _list_models(self, client: httpx.Client) -> set[str]:
        base = client.base_url
        if str(base) in self._available_models:
            return self._available_models[str(base)]

        try:
            response = client.get("/v1/models")
            response.raise_for_status()
            payload = response.json()
            models = {
                item.get("id")
                for item in payload.get("data", [])
                if isinstance(item, dict) and item.get("id")
            }
            self._available_models[str(base)] = models
            return models
        except Exception as exc:  # pragma: no cover - network/infra errors
            logger.error("Error obteniendo modelos disponibles de vLLM: %s", exc)
            raise VLLMWrapperError(
                f"No se pudieron listar los modelos disponibles en {base!s}: {exc}"
            ) from exc

    def _ensure_model_available(
        self, model_alias: str, client: httpx.Client
    ) -> None:
        models = self._list_models(client)
        if model_alias in models:
            return

        resolved_path = self.config.model_alias_map.get(model_alias)
        if resolved_path and resolved_path in models:
            return

        base = client.base_url
        raise VLLMWrapperError(
            f"El modelo '{model_alias}' no está registrado en el servidor vLLM ({base}). "
            "Verifique que el contenedor se haya iniciado con --served-model-name "
            "coincidente o ajuste las variables de entorno VLLM_*."
        )

    def _select_client(
        self, is_embedding: bool = False
    ) -> httpx.Client:
        if is_embedding and self.embedding_client:
            return self.embedding_client
        if not self.chat_client:
            raise VLLMWrapperError(CLIENT_NOT_INITIALIZED)
        return self.chat_client

    def generate_embedding(self, text: str, model: Optional[str] = None) -> List[float]:
        client = self._select_client(is_embedding=True)
        model_alias = model or self.config.embedding_model
        if not model_alias:
            raise VLLMWrapperError("Nombre del modelo de embeddings no configurado.")

        self._ensure_model_available(model_alias, client)

        try:
            response = client.post(
                "/v1/embeddings", json={"model": model_alias, "input": [text]}
            )
            response.raise_for_status()
            payload = response.json()
            return payload["data"][0]["embedding"]
        except Exception as exc:
            logger.error("Error generando embedding con '%s': %s", model_alias, exc)
            raise VLLMWrapperError(
                f"Falló la generación del embedding: {exc}"
            ) from exc

    def generate_chat_completion(
        self,
        prompt: str,
        model: Optional[str] = None,
        system_message: Optional[str] = None,
        context_chunks: Optional[List[str]] = None,
        stream: bool = False,
    ) -> str:
        if stream:
            logger.warning(
                "El streaming aún no está soportado en VLLMWrapper. Se devolverá la respuesta completa."
            )

        client = self._select_client()
        model_alias = model or self.config.chat_model
        self._ensure_model_available(model_alias, client)

        messages: List[Dict[str, str]] = []
        if system_message:
            messages.append({"role": "system", "content": system_message})

        if context_chunks:
            context_text = "\n\n".join(context_chunks)
            user_prompt = f"Contexto:\n{context_text}\n\nPregunta: {prompt}"
        else:
            user_prompt = prompt
        messages.append({"role": "user", "content": user_prompt})

        try:
            response = client.post(
                "/v1/chat/completions",
                json={
                    "model": model_alias,
                    "messages": messages,
                    "stream": False,
                },
            )
            response.raise_for_status()
            payload = response.json()
            choices = payload.get("choices", [])
            if not choices:
                return ""
            return choices[0]["message"].get("content", "") or ""
        except Exception as exc:
            logger.error(
                "Error generando completado de chat con '%s': %s", model_alias, exc
            )
            raise VLLMWrapperError(
                f"Falló la generación de la respuesta del chat: {exc}"
            ) from exc

    def format_to_markdown(
        self,
        text_content: str,
        model: Optional[str] = None,
        save_path: Optional[str] = None,
    ) -> str:
        client = self._select_client()
        model_alias = model or self.config.markdown_model or self.config.chat_model
        self._ensure_model_available(model_alias, client)

        cleaned_text = preprocess_text_content(text_content)

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

        payload = {
            "model": model_alias,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": cleaned_text},
            ],
            "stream": False,
        }

        try:
            response = client.post("/v1/chat/completions", json=payload)
            response.raise_for_status()
            data = response.json()
            choices = data.get("choices", [])
            if not choices:
                return ""
            content = postprocess_markdown_content(
                choices[0]["message"].get("content", "")
            )
            if content and save_path:
                save_markdown_to_file(content, Path(save_path))
            return content
        except Exception as exc:
            logger.error(
                "Error formateando texto a Markdown con '%s': %s", model_alias, exc
            )
            raise VLLMWrapperError(
                f"Falló el formateo de texto a Markdown: {exc}"
            ) from exc

    def close(self) -> None:
        try:
            if self.embedding_client is not self.chat_client:
                self.embedding_client.close()
            self.chat_client.close()
        except Exception:  # pragma: no cover - cleanup best effort
            pass

    def __del__(self):
        self.close()

