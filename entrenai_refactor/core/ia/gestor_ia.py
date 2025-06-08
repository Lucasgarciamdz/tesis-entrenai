import logging
from typing import List, Optional
import ollama

class ErrorIA(Exception):
    pass

class GestorIA:
    def __init__(self, host: str, modelo_embedding: str, modelo_qa: str):
        self.logger = logging.getLogger("gestor_ia")
        try:
            self.cliente = ollama.Client(host=host)
            self.cliente.list()
            self.modelo_embedding = modelo_embedding
            self.modelo_qa = modelo_qa
            self.logger.info(f"GestorIA conectado a Ollama en {host}")
        except Exception as e:
            self.logger.error(f"Error al conectar con Ollama: {e}")
            self.cliente = None
            raise ErrorIA(str(e))

    def generar_embedding(self, texto: str) -> List[float]:
        if not self.cliente:
            raise ErrorIA("Cliente Ollama no inicializado.")
        try:
            respuesta = self.cliente.embeddings(model=self.modelo_embedding, prompt=texto)
            return respuesta["embedding"]
        except Exception as e:
            self.logger.error(f"Error generando embedding: {e}")
            raise ErrorIA(str(e))

    def generar_respuesta_chat(self, prompt: str, mensaje_sistema: Optional[str] = None, contexto: Optional[List[str]] = None) -> str:
        if not self.cliente:
            raise ErrorIA("Cliente Ollama no inicializado.")
        mensajes = []
        if mensaje_sistema:
            mensajes.append({"role": "system", "content": mensaje_sistema})
        if contexto:
            contexto_str = "\n\n".join(contexto)
            prompt_completo = f"Contexto:\n{contexto_str}\n\nPregunta: {prompt}"
            mensajes.append({"role": "user", "content": prompt_completo})
        else:
            mensajes.append({"role": "user", "content": prompt})
        try:
            respuesta = self.cliente.chat(model=self.modelo_qa, messages=mensajes, stream=False)
            if isinstance(respuesta, dict) and "message" in respuesta and "content" in respuesta["message"]:
                return str(respuesta["message"]["content"])
            elif hasattr(respuesta, "message") and hasattr(respuesta.message, "content"):
                return str(respuesta.message.content)
            else:
                raise ErrorIA("Formato de respuesta inesperado de la API de Ollama")
        except Exception as e:
            self.logger.error(f"Error generando respuesta de chat: {e}")
            raise ErrorIA(str(e))

    def configurar_para_curso(self, curso_id: int):
        self.logger.info(f"Configurando IA para el curso {curso_id}")
        return True 