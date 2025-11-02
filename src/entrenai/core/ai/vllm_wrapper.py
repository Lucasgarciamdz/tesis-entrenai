import threading
import time
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
    """Custom exception for VLLM wrapper related errors."""

    pass


class VLLMWrapper:
    """Wrapper around a vLLM OpenAI-compatible server."""

    def __init__(self, config: VLLMConfig):
        self.config = config
        if not config.base_url:
            logger.error(
                "VLLM_BASE_URL no está configurado. VLLMWrapper no será funcional."
            )
            raise VLLMWrapperError("VLLM_BASE_URL no configurado.")

        self._last_used_at: Dict[str, float] = {}
        self._unload_timers: Dict[str, threading.Timer] = {}
        self._loaded_models: Dict[str, bool] = {}
        self._load_lock = threading.Lock()

        headers = {}
        if config.api_key:
            headers["Authorization"] = f"Bearer {config.api_key}"

        self.client = httpx.Client(
            base_url=config.base_url.rstrip("/"),
            timeout=config.request_timeout_seconds,
            headers=headers,
        )

        try:
            self._ensure_connection()
        except Exception as exc:
            logger.error(
                "Falló la conexión inicial con el servidor vLLM en %s: %s",
                config.base_url,
                exc,
            )
            self.client.close()
            raise VLLMWrapperError(
                f"Falló la conexión inicial con el servidor vLLM: {exc}"
            ) from exc

    # ------------------------------------------------------------------ #
    # Private helpers
    # ------------------------------------------------------------------ #
    def _ensure_connection(self) -> None:
        """Confirms the server is reachable and caches any already loaded models."""
        response = self.client.get("/v1/models")
        response.raise_for_status()

        data = response.json()
        models = data.get("data", []) if isinstance(data, dict) else []
        for model_obj in models:
            model_id = model_obj.get("id")
            if model_id:
                self._loaded_models[model_id] = True
                logger.info("Modelo vLLM '%s' detectado como cargado.", model_id)

    def _ensure_model_loaded(self, model_name: str) -> None:
        """Loads the model if it is not currently available."""
        if not model_name:
            raise VLLMWrapperError("Nombre de modelo vacío provisto para vLLM.")

        with self._load_lock:
            if self._loaded_models.get(model_name):
                return

            logger.info("Cargando modelo vLLM '%s' bajo demanda.", model_name)
            payload: Dict[str, Any] = {"model": model_name}
            response = self.client.post("/v1/models", json=payload)
            if response.status_code not in (200, 201):
                raise VLLMWrapperError(
                    f"No se pudo cargar el modelo '{model_name}': {response.text}"
                )
            self._loaded_models[model_name] = True
            logger.info("Modelo vLLM '%s' cargado exitosamente.", model_name)

    def _schedule_unload(self, model_name: str) -> None:
        """Schedules unloading a model after the configured idle timeout."""
        if not self.config.idle_timeout_seconds:
            return

        if model_name in self._unload_timers:
            self._unload_timers[model_name].cancel()

        timer = threading.Timer(
            self.config.idle_timeout_seconds, self._attempt_unload, args=(model_name,)
        )
        timer.daemon = True
        self._unload_timers[model_name] = timer
        timer.start()

    def _attempt_unload(self, model_name: str) -> None:
        """Attempts to unload the model if it has been idle long enough."""
        last_used = self._last_used_at.get(model_name)
        if last_used is None:
            return

        elapsed = time.monotonic() - last_used
        if elapsed < (self.config.idle_timeout_seconds or 0):
            # A newer request refreshed the timer.
            logger.debug(
                "Modelo vLLM '%s' uso reciente detectado (%.2fs), no se descarga.",
                model_name,
                elapsed,
            )
            return

        logger.info(
            "Descargando modelo vLLM '%s' por inactividad (%.2f s).",
            model_name,
            elapsed,
        )
        try:
            response = self.client.delete(f"/v1/models/{model_name}")
            if response.status_code not in (200, 202, 204):
                logger.warning(
                    "El servidor vLLM devolvió estado %s al descargar '%s': %s",
                    response.status_code,
                    model_name,
                    response.text,
                )
            else:
                logger.info("Modelo vLLM '%s' descargado exitosamente.", model_name)
                with self._load_lock:
                    self._loaded_models.pop(model_name, None)
        except Exception as exc:
            logger.warning(
                "No se pudo descargar el modelo vLLM '%s': %s", model_name, exc
            )

    def _update_last_used(self, model_name: str) -> None:
        self._last_used_at[model_name] = time.monotonic()
        self._schedule_unload(model_name)

    def _chat_request(
        self,
        model_name: str,
        messages: List[Dict[str, str]],
        temperature: float = 0.2,
        stream: bool = False,
    ) -> Dict[str, Any]:
        payload = {
            "model": model_name,
            "messages": messages,
            "temperature": temperature,
            "stream": stream,
        }
        response = self.client.post("/v1/chat/completions", json=payload)
        response.raise_for_status()
        return response.json()

    # ------------------------------------------------------------------ #
    # Public interface
    # ------------------------------------------------------------------ #
    def generate_embedding(self, text: str, model: Optional[str] = None) -> List[float]:
        if not self.client:
            raise VLLMWrapperError(CLIENT_NOT_INITIALIZED)

        model_to_use = model or self.config.embedding_model
        self._ensure_model_loaded(model_to_use)

        payload = {"model": model_to_use, "input": [text]}
        response = self.client.post("/v1/embeddings", json=payload)
        response.raise_for_status()
        data = response.json()

        try:
            embedding = data["data"][0]["embedding"]
        except (KeyError, IndexError, TypeError) as exc:
            raise VLLMWrapperError(
                f"Respuesta inesperada al solicitar embeddings: {data}"
            ) from exc

        self._update_last_used(model_to_use)
        return embedding

    def generate_chat_completion(
        self,
        prompt: str,
        model: Optional[str] = None,
        system_message: Optional[str] = None,
        context_chunks: Optional[List[str]] = None,
        stream: bool = False,
    ) -> str:
        if not self.client:
            raise VLLMWrapperError(CLIENT_NOT_INITIALIZED)

        model_to_use = model or self.config.chat_model
        self._ensure_model_loaded(model_to_use)

        messages: List[Dict[str, str]] = []
        if system_message:
            messages.append({"role": "system", "content": system_message})

        if context_chunks:
            context = "\n\n".join(context_chunks)
            messages.append(
                {
                    "role": "user",
                    "content": f"Contexto:\n{context}\n\nPregunta: {prompt}",
                }
            )
        else:
            messages.append({"role": "user", "content": prompt})

        try:
            response_data = self._chat_request(
                model_name=model_to_use, messages=messages, stream=stream
            )
        except httpx.HTTPError as exc:
            raise VLLMWrapperError(
                f"Error en la solicitud de chat a vLLM: {exc}"
            ) from exc

        try:
            choices = response_data["choices"]
            if not choices:
                raise ValueError("La lista 'choices' está vacía.")
            message = choices[0]["message"]
            content = message.get("content", "")
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise VLLMWrapperError(
                f"Respuesta inesperada al generar completación: {response_data}"
            ) from exc

        self._update_last_used(model_to_use)
        return content or ""

    def format_to_markdown(
        self,
        text_content: str,
        model: Optional[str] = None,
        save_path: Optional[str] = None,
    ) -> str:
        if not self.client:
            raise VLLMWrapperError(CLIENT_NOT_INITIALIZED)

        model_to_use = model or self.config.markdown_model or self.config.chat_model
        self._ensure_model_loaded(model_to_use)

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

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": cleaned_text},
        ]

        try:
            response_data = self._chat_request(
                model_name=model_to_use, messages=messages, temperature=0.0
            )
        except httpx.HTTPError as exc:
            raise VLLMWrapperError(
                f"Error formateando texto a Markdown con vLLM: {exc}"
            ) from exc

        try:
            choices = response_data["choices"]
            if not choices:
                raise ValueError("La lista 'choices' está vacía.")
            message = choices[0]["message"]
            content = postprocess_markdown_content(message.get("content", ""))
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise VLLMWrapperError(
                f"Respuesta inesperada al formatear Markdown: {response_data}"
            ) from exc

        if save_path and content:
            save_markdown_to_file(content, Path(save_path))

        self._update_last_used(model_to_use)
        return content

    def close(self) -> None:
        """Release HTTP resources."""
        if self.client:
            self.client.close()

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass

