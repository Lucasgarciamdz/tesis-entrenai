from pathlib import Path
from typing import List, Optional, Dict, Any

import google.generativeai as genai

from entrenai2.configuracion.configuracion import config
from entrenai2.configuracion.registrador import obtener_registrador
from entrenai2.nucleo.ia.utilidades_comunes import (
    postprocesar_contenido_markdown,
    preprocesar_contenido_texto,
    guardar_markdown_en_archivo,
)

registrador = obtener_registrador(__name__)

CLAVE_API_NO_CONFIGURADA = "La clave API de Gemini no está configurada."

class ErrorEnvoltorioGemini(Exception):
    """Excepción personalizada para errores de EnvoltorioGemini."""
    pass


class EnvoltorioGemini:
    """Envoltorio para interactuar con la API de Google Gemini."""

    def __init__(self):
        self.config = config.gemini
        
        if not self.config.clave_api:
            raise ErrorEnvoltorioGemini(CLAVE_API_NO_CONFIGURADA)
            
        try:
            genai.configure(api_key=self.config.clave_api)
            registrador.info("Cliente de Gemini inicializado exitosamente.")
        except Exception as e:
            raise ErrorEnvoltorioGemini(f"Fallo en la inicialización del cliente de Gemini: {e}") from e

    def _obtener_configuracion_seguridad(self) -> Optional[List[Dict[str, Any]]]:
        """Obtiene la configuración de seguridad para las llamadas a la API."""
        if not self.config.seguridad_habilitada:
            return [
                {"category": c, "threshold": "BLOCK_NONE"}
                for c in [
                    "HARM_CATEGORY_HARASSMENT", "HARM_CATEGORY_HATE_SPEECH",
                    "HARM_CATEGORY_SEXUALLY_EXPLICIT", "HARM_CATEGORY_DANGEROUS_CONTENT"
                ]
            ]
        return None

    def generar_embedding(self, texto: str, modelo: Optional[str] = None) -> List[float]:
        """Genera un embedding vectorial para un texto."""
        modelo_a_usar = modelo or self.config.modelo_embedding
        try:
            respuesta = genai.embed_content(
                model=modelo_a_usar,
                content=texto,
                task_type="SEMANTIC_SIMILARITY",
                output_dimensionality=self.config.dimension_embedding,
            )
            return list(respuesta["embedding"])
        except Exception as e:
            raise ErrorEnvoltorioGemini(f"Fallo en la generación de embedding con '{modelo_a_usar}': {e}") from e

    def generar_completacion_chat(self, prompt: str, **kwargs) -> str:
        """Genera una respuesta de chat."""
        modelo_a_usar = kwargs.get("modelo", self.config.modelo_texto)
        try:
            modelo = genai.GenerativeModel(
                model_name=modelo_a_usar,
                safety_settings=self._obtener_configuracion_seguridad()
            )
            respuesta = modelo.generate_content(prompt)
            return respuesta.text
        except Exception as e:
            raise ErrorEnvoltorioGemini(f"Fallo en la completación de chat con '{modelo_a_usar}': {e}") from e

    def formatear_a_markdown(self, contenido_texto: str, ruta_guardado: Optional[str] = None) -> str:
        """Convierte texto a un formato Markdown bien estructurado."""
        texto_limpio = preprocesar_contenido_texto(contenido_texto)
        prompt_sistema = (
            "Eres un experto formateador de texto a Markdown. Transforma el siguiente contenido a un "
            "formato Markdown limpio y bien estructurado, manteniendo el significado original. "
            "No añadas introducciones, resúmenes ni meta-comentarios. Solo devuelve el Markdown."
        )
        prompt_completo = f"{prompt_sistema}\n\nTexto a formatear:\n{texto_limpio}"

        try:
            modelo = genai.GenerativeModel(
                model_name=self.config.modelo_texto,
                safety_settings=self._obtener_configuracion_seguridad()
            )
            respuesta = modelo.generate_content(prompt_completo)
            contenido_markdown = postprocesar_contenido_markdown(respuesta.text)
            
            if ruta_guardado:
                guardar_markdown_en_archivo(contenido_markdown, Path(ruta_guardado))
            
            return contenido_markdown
        except Exception as e:
            raise ErrorEnvoltorioGemini(f"Fallo en el formateo a Markdown: {e}") from e
