from typing import List, Optional, Any
from pathlib import Path

import ollama

from entrenai2.configuracion.configuracion import config
from entrenai2.configuracion.registrador import obtener_registrador
from entrenai2.nucleo.ia.utilidades_comunes import (
    postprocesar_contenido_markdown,
    preprocesar_contenido_texto,
    guardar_markdown_en_archivo,
)

registrador = obtener_registrador(__name__)

CLIENTE_NO_INICIALIZADO = "El cliente de Ollama no está inicializado."

class ErrorEnvoltorioOllama(Exception):
    """Excepción personalizada para errores del EnvoltorioOllama."""
    pass


class EnvoltorioOllama:
    """Envoltorio para interactuar con la API de Ollama."""

    def __init__(self):
        self.config = config.ollama
        self.cliente: Optional[ollama.Client] = None
        
        if not self.config.host:
            raise ErrorEnvoltorioOllama("El host de Ollama no está configurado.")
            
        try:
            self.cliente = ollama.Client(host=self.config.host)
            self.cliente.list()  # Prueba de conexión
            registrador.info(f"Cliente de Ollama conectado a: {self.config.host}")
            self._asegurar_modelos_disponibles()
        except Exception as e:
            raise ErrorEnvoltorioOllama(f"No se pudo conectar con Ollama en {self.config.host}: {e}") from e

    def _asegurar_modelos_disponibles(self):
        """Verifica que los modelos necesarios estén disponibles en Ollama."""
        if not self.cliente: return

        try:
            modelos_disponibles = [m["name"] for m in self.cliente.list().get("models", [])]
            modelos_requeridos = {
                "embedding": self.config.modelo_embedding,
                "markdown": self.config.modelo_markdown,
                "qa": self.config.modelo_qa,
            }
            for tipo, nombre_modelo in modelos_requeridos.items():
                if nombre_modelo not in modelos_disponibles:
                    registrador.warning(f"El modelo '{nombre_modelo}' para '{tipo}' no se encontró en Ollama.")
        except Exception as e:
            registrador.error(f"Error al verificar los modelos de Ollama: {e}")

    def generar_embedding(self, texto: str, modelo: Optional[str] = None) -> List[float]:
        """Genera un embedding para un texto."""
        if not self.cliente: raise ErrorEnvoltorioOllama(CLIENTE_NO_INICIALIZADO)
        
        modelo_a_usar = modelo or self.config.modelo_embedding
        try:
            respuesta = self.cliente.embeddings(model=modelo_a_usar, prompt=texto)
            return respuesta["embedding"]
        except Exception as e:
            raise ErrorEnvoltorioOllama(f"Fallo en la generación de embedding con '{modelo_a_usar}': {e}") from e

    def generar_completacion_chat(self, prompt: str, **kwargs) -> str:
        """Genera una respuesta de chat."""
        if not self.cliente: raise ErrorEnvoltorioOllama(CLIENTE_NO_INICIALIZADO)

        mensajes = [{"role": "user", "content": prompt}]
        try:
            respuesta = self.cliente.chat(model=self.config.modelo_qa, messages=mensajes)
            return respuesta['message']['content']
        except Exception as e:
            raise ErrorEnvoltorioOllama(f"Fallo en la completación de chat: {e}") from e

    def formatear_a_markdown(self, contenido_texto: str, ruta_guardado: Optional[str] = None) -> str:
        """Convierte texto a un formato Markdown bien estructurado."""
        if not self.cliente: raise ErrorEnvoltorioOllama(CLIENTE_NO_INICIALIZADO)

        texto_limpio = preprocesar_contenido_texto(contenido_texto)
        prompt_sistema = (
            "Eres un experto formateador de texto a Markdown. Transforma el siguiente contenido a un "
            "formato Markdown limpio y bien estructurado, manteniendo el significado original. "
            "No añadas introducciones, resúmenes ni meta-comentarios. Solo devuelve el Markdown."
        )
        mensajes = [
            {"role": "system", "content": prompt_sistema},
            {"role": "user", "content": texto_limpio},
        ]

        try:
            respuesta = self.cliente.chat(model=self.config.modelo_markdown, messages=mensajes)
            contenido_markdown = postprocesar_contenido_markdown(respuesta['message']['content'])
            
            if ruta_guardado:
                guardar_markdown_en_archivo(contenido_markdown, Path(ruta_guardado))
            
            return contenido_markdown
        except Exception as e:
            raise ErrorEnvoltorioOllama(f"Fallo en el formateo a Markdown: {e}") from e
