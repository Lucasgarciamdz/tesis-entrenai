from typing import List, Optional, Any, Dict
from pathlib import Path
import ollama # Cliente oficial de Ollama para Python

from entrenai_refactor.config.configuracion import configuracion_global
from entrenai_refactor.config.registrador import obtener_registrador
from entrenai_refactor.nucleo.ia.utilidades_comunes_ia import (
    postprocesar_contenido_markdown,
    preprocesar_contenido_texto,
    guardar_markdown_en_archivo,
)

registrador = obtener_registrador(__name__)

MENSAJE_CLIENTE_OLLAMA_NO_INICIALIZADO = "El cliente de Ollama no ha sido inicializado correctamente."
MENSAJE_HOST_OLLAMA_NO_CONFIGURADO = "El host (URL) del servidor Ollama no está configurado."

class ErrorEnvoltorioOllama(Exception):
    """Excepción personalizada para errores específicos del EnvoltorioOllama."""
    def __init__(self, mensaje: str, error_original: Optional[Exception] = None):
        super().__init__(mensaje)
        self.error_original = error_original
        registrador.debug(f"Excepción ErrorEnvoltorioOllama creada: {mensaje}, Original: {error_original}")

    def __str__(self):
        if self.error_original:
            return f"{super().__str__()} (Error original: {type(self.error_original).__name__}: {str(self.error_original)})"
        return super().__str__()

class EnvoltorioOllama:
    """
    Envoltorio para interactuar con la API de Ollama.
    Gestiona la conexión al servidor Ollama, la generación de embeddings,
    completaciones de chat y formateo de texto.
    """

    def __init__(self):
        self.config_ollama = configuracion_global.ollama
        self.cliente_ollama: Optional[ollama.Client] = None # Tipado explícito del cliente Ollama

        registrador.info("Inicializando EnvoltorioOllama...")
        if not self.config_ollama.host_ollama: # CAMBIADO
            registrador.error(MENSAJE_HOST_OLLAMA_NO_CONFIGURADO)
            # Decidir si lanzar excepción o permitir que el envoltorio exista sin cliente.
            # Por ahora, se permite, pero los métodos fallarán.
            # raise ErrorEnvoltorioOllama(MENSAJE_HOST_OLLAMA_NO_CONFIGURADO)
            return

        try:
            registrador.debug(f"Intentando conectar al host de Ollama: {self.config_ollama.host_ollama}") # CAMBIADO
            self.cliente_ollama = ollama.Client(host=self.config_ollama.host_ollama) # CAMBIADO
            # Realizar una llamada de prueba para verificar la conexión y disponibilidad del servidor
            self.cliente_ollama.list()
            registrador.info(f"Cliente Ollama inicializado y conectado exitosamente al host: {self.config_ollama.host_ollama}") # CAMBIADO
            self._asegurar_disponibilidad_modelos_configurados() # Verificar modelos después de conexión exitosa
        except Exception as e_conexion:
            registrador.error(f"Falló la conexión o inicialización del cliente Ollama en {self.config_ollama.host_ollama}: {e_conexion}") # CAMBIADO
            self.cliente_ollama = None # Asegurar que el cliente quede como None si falla
            # Considerar no relanzar para permitir que la aplicación inicie incluso si Ollama no está disponible.
            # Los métodos que usen self.cliente_ollama deberán verificar su existencia.
            # raise ErrorEnvoltorioOllama(f"Falló la inicialización del cliente Ollama: {e_conexion}", e_conexion)

    def _asegurar_disponibilidad_modelos_configurados(self):
        """
        Verifica si los modelos de Ollama especificados en la configuración están
        disponibles en el servidor Ollama conectado. Emite advertencias si no lo están.
        """
        if not self.cliente_ollama:
            registrador.debug("Cliente Ollama no disponible, no se pueden verificar modelos.")
            return

        registrador.debug("Verificando disponibilidad de modelos Ollama configurados...")
        try:
            respuesta_lista_modelos = self.cliente_ollama.list()
            modelos_disponibles_en_servidor = []

            if isinstance(respuesta_lista_modelos, dict) and "models" in respuesta_lista_modelos:
                 for info_modelo in respuesta_lista_modelos.get("models", []): # Usar .get() por seguridad
                    if isinstance(info_modelo, dict) and "name" in info_modelo:
                       modelos_disponibles_en_servidor.append(info_modelo["name"])
            else:
                registrador.warning(f"Respuesta inesperada al listar modelos de Ollama: {respuesta_lista_modelos}")
                # No se puede continuar si no se obtiene la lista de modelos.
                return

            registrador.debug(f"Modelos Ollama disponibles en el servidor: {modelos_disponibles_en_servidor}")

            modelos_configurados_app = {
                "embedding": self.config_ollama.modelo_embedding_ollama, # CAMBIADO
                "formateo_markdown": self.config_ollama.modelo_markdown_ollama, # CAMBIADO
                "pregunta_respuesta": self.config_ollama.modelo_qa_ollama, # CAMBIADO
                "analisis_contexto": self.config_ollama.modelo_contexto_ollama, # CAMBIADO
            }

            for uso_modelo, nombre_modelo_requerido in modelos_configurados_app.items():
                if not nombre_modelo_requerido: # Si un modelo no está configurado, se omite la verificación
                    registrador.info(f"Modelo Ollama para '{uso_modelo}' no está configurado en la aplicación. Omitiendo verificación.")
                    continue

                # Comparar solo el nombre base del modelo (ej. 'llama2' de 'llama2:7b')
                nombre_base_modelo_requerido = nombre_modelo_requerido.split(":")[0]
                esta_disponible = any(
                    nombre_servidor.startswith(nombre_base_modelo_requerido) for nombre_servidor in modelos_disponibles_en_servidor
                )

                if not esta_disponible:
                    registrador.warning(
                        f"El modelo Ollama para '{uso_modelo}' ('{nombre_modelo_requerido}') "
                        f"no se encontró entre los modelos disponibles en el servidor: {modelos_disponibles_en_servidor}. "
                        f"Asegúrese de que el modelo esté descargado en el servidor Ollama (ej: 'ollama pull {nombre_modelo_requerido}')."
                    )
                else:
                    registrador.info(f"Modelo Ollama para '{uso_modelo}' ('{nombre_modelo_requerido}') está disponible en el servidor.")
        except Exception as e_verificacion:
            # Captura errores de conexión que podrían ocurrir aquí también, o errores inesperados.
            registrador.error(f"Error al verificar los modelos Ollama disponibles en el servidor: {e_verificacion}")


    def generar_embedding_de_texto(self, texto_entrada: str, nombre_modelo_embedding: Optional[str] = None) -> List[float]:
        """Genera un vector de embedding para un texto dado utilizando un modelo de Ollama."""
        if not self.cliente_ollama:
            registrador.error(f"{MENSAJE_CLIENTE_OLLAMA_NO_INICIALIZADO} No se puede generar el embedding.")
            raise ErrorEnvoltorioOllama(MENSAJE_CLIENTE_OLLAMA_NO_INICIALIZADO)

        modelo_seleccionado = nombre_modelo_embedding or self.config_ollama.modelo_embedding_ollama # CAMBIADO
        if not modelo_seleccionado:
            registrador.error("Nombre del modelo de embedding de Ollama no configurado.")
            raise ErrorEnvoltorioOllama("Nombre del modelo de embedding de Ollama no configurado.")

        registrador.debug(f"Generando embedding con modelo Ollama '{modelo_seleccionado}' para texto de longitud {len(texto_entrada)}.")
        try:
            texto_preprocesado_para_embedding = preprocesar_contenido_texto(texto_entrada)
            respuesta_embedding = self.cliente_ollama.embeddings(model=modelo_seleccionado, prompt=texto_preprocesado_para_embedding)

            if "embedding" in respuesta_embedding and isinstance(respuesta_embedding["embedding"], list):
                registrador.info(f"Embedding generado exitosamente con modelo '{modelo_seleccionado}'. Dimensión: {len(respuesta_embedding['embedding'])}.")
                return respuesta_embedding["embedding"]
            else:
                registrador.error(f"Respuesta de embedding de Ollama no contiene un vector válido: {respuesta_embedding}")
                raise ErrorEnvoltorioOllama("Respuesta de embedding de Ollama no contiene un vector válido.")
        except Exception as e_embedding:
            registrador.error(f"Error al generar embedding con modelo Ollama '{modelo_seleccionado}': {e_embedding}")
            raise ErrorEnvoltorioOllama(f"Falló la generación del embedding con Ollama: {e_embedding}", e_embedding)

    def generar_respuesta_de_chat(
        self,
        prompt_usuario: str,
        nombre_modelo_chat: Optional[str] = None,
        mensaje_de_sistema: Optional[str] = None,
        historial_chat_previo: Optional[List[Dict[str, str]]] = None, # Formato: [{"role": "user/assistant", "content": "texto"}]
        fragmentos_de_contexto: Optional[List[str]] = None,
        # stream: bool = False # El streaming aún no está implementado en este envoltorio
    ) -> str:
        """
        Genera una respuesta de chat utilizando un modelo de Ollama,
        opcionalmente con un mensaje de sistema, historial de chat y contexto adicional.
        """
        if not self.cliente_ollama:
            registrador.error(f"{MENSAJE_CLIENTE_OLLAMA_NO_INICIALIZADO} No se puede generar la completación de chat.")
            raise ErrorEnvoltorioOllama(MENSAJE_CLIENTE_OLLAMA_NO_INICIALIZADO)

        modelo_seleccionado = nombre_modelo_chat or self.config_ollama.modelo_qa_ollama # CAMBIADO # Usar modelo_qa para chat
        if not modelo_seleccionado:
            registrador.error("Nombre del modelo de QA/chat de Ollama no configurado.")
            raise ErrorEnvoltorioOllama("Nombre del modelo de QA/chat de Ollama no configurado.")

        registrador.debug(f"Generando completación de chat con modelo Ollama '{modelo_seleccionado}'.")

        # Construir la lista de mensajes para la API de Ollama
        mensajes_api = []
        if mensaje_de_sistema:
            mensajes_api.append({"role": "system", "content": mensaje_de_sistema})

        if historial_chat_previo:
            for item_historial in historial_chat_previo:
                 if "role" in item_historial and "content" in item_historial:
                    mensajes_api.append(item_historial)
                 else:
                    registrador.warning(f"Item de historial de chat malformado omitido: {item_historial}")


        # Añadir el contexto y el prompt actual del usuario
        prompt_final_con_contexto = prompt_usuario
        if fragmentos_de_contexto:
            contexto_como_string = "\n\n".join(fragmentos_de_contexto)
            prompt_final_con_contexto = (
                f"Por favor, considera el siguiente contexto para responder la pregunta:\n--- Contexto ---\n"
                f"{contexto_como_string}\n--- Fin del Contexto ---\n\nPregunta del usuario: {prompt_usuario}"
            )

        mensajes_api.append({"role": "user", "content": prompt_final_con_contexto})

        registrador.debug(f"Enviando a Ollama (modelo {modelo_seleccionado}): Mensajes: {json.dumps(mensajes_api, indent=2, ensure_ascii=False)}")

        try:
            # El streaming requeriría un manejo diferente del iterador de respuesta
            # if stream:
            #    registrador.warning("El streaming no está implementado aún para Ollama en este envoltorio. Se devolverá la respuesta completa.")

            respuesta_ollama = self.cliente_ollama.chat(model=modelo_seleccionado, messages=mensajes_api, stream=False)

            contenido_texto_respuesta = ""
            if isinstance(respuesta_ollama, dict) and \
               "message" in respuesta_ollama and \
               isinstance(respuesta_ollama["message"], dict) and \
               "content" in respuesta_ollama["message"]:
                contenido_texto_respuesta = str(respuesta_ollama["message"]["content"])
            else:
                registrador.error(f"Formato de respuesta inesperado de la API de chat de Ollama: {respuesta_ollama}")
                raise ErrorEnvoltorioOllama(f"Formato de respuesta inesperado de la API de chat de Ollama: {type(respuesta_ollama)}")

            if not contenido_texto_respuesta:
                registrador.warning(f"La completación de chat del modelo Ollama '{modelo_seleccionado}' devolvió contenido vacío.")

            registrador.info(f"Respuesta de chat generada exitosamente con modelo Ollama '{modelo_seleccionado}'.")
            return contenido_texto_respuesta

        except Exception as e_chat:
            registrador.error(f"Error al generar completación de chat con modelo Ollama '{modelo_seleccionado}': {e_chat}")
            raise ErrorEnvoltorioOllama(f"Falló la generación de la completación de chat con Ollama: {e_chat}", e_chat)

    def convertir_texto_a_markdown(
        self,
        texto_original: str,
        nombre_modelo_formateo: Optional[str] = None,
        ruta_archivo_guardado: Optional[Path] = None
    ) -> str:
        """Formatea un texto crudo a formato Markdown utilizando un modelo de Ollama."""
        if not self.cliente_ollama:
            registrador.error(f"{MENSAJE_CLIENTE_OLLAMA_NO_INICIALIZADO} No se puede formatear a Markdown.")
            raise ErrorEnvoltorioOllama(MENSAJE_CLIENTE_OLLAMA_NO_INICIALIZADO)

        modelo_seleccionado = nombre_modelo_formateo or self.config_ollama.modelo_markdown_ollama # CAMBIADO
        if not modelo_seleccionado:
            registrador.error("Nombre del modelo de formateo a Markdown de Ollama no configurado.")
            raise ErrorEnvoltorioOllama("Nombre del modelo de formateo a Markdown de Ollama no configurado.")

        texto_limpio_para_formateo = preprocesar_contenido_texto(texto_original)
        registrador.info(f"Formateando texto a Markdown con modelo Ollama '{modelo_seleccionado}'. Longitud original: {len(texto_original)}, preprocesado: {len(texto_limpio_para_formateo)}.")

        prompt_instruccion_sistema = (
            "Eres un experto formateador de texto especializado en convertir texto crudo a Markdown limpio y bien estructurado.\n"
            "Tu tarea es transformar el siguiente contenido proporcionado a un formato Markdown. Sigue estas reglas estrictamente:\n"
            "1. Mantén el significado y la información factual del contenido original.\n"
            "2. Crea encabezados (#, ##, ###) y estructura apropiados basados en la jerarquía implícita del contenido.\n"
            "3. Formatea correctamente listas (numeradas y con viñetas), tablas (si son detectables), bloques de código (si aplica), y otros elementos Markdown (negritas, cursivas, etc.).\n"
            "4. Corrige errores tipográficos y de formato obvios (ej. múltiples espacios) mientras preservas el significado.\n"
            "5. NO añadas ningún contenido nuevo, introducciones, resúmenes, conclusiones o información que no esté en el texto original.\n"
            "6. NO incluyas ningún meta-comentario, notas sobre el proceso de formateo, o disculpas.\n"
            "7. SOLO devuelve el contenido Markdown formateado correctamente. Nada antes, nada después.\n\n"
            "El objetivo es un Markdown limpio que represente con precisión el contenido original, listo para ser usado directamente."
        )
        mensajes_api_formateo = [
            {"role": "system", "content": prompt_instruccion_sistema},
            {"role": "user", "content": texto_limpio_para_formateo}
        ]

        try:
            respuesta_formateo = self.cliente_ollama.chat(model=modelo_seleccionado, messages=mensajes_api_formateo, stream=False)

            contenido_markdown_generado = ""
            if isinstance(respuesta_formateo, dict) and \
               "message" in respuesta_formateo and \
               isinstance(respuesta_formateo["message"], dict) and \
               "content" in respuesta_formateo["message"]:
                contenido_markdown_generado = str(respuesta_formateo["message"]["content"])
            else:
                registrador.error(f"Formato de respuesta inesperado de Ollama para formateo a Markdown: {respuesta_formateo}")
                raise ErrorEnvoltorioOllama(f"Formato de respuesta inesperado para formateo a Markdown con Ollama: {type(respuesta_formateo)}")

            contenido_markdown_final = postprocesar_contenido_markdown(contenido_markdown_generado)

            if contenido_markdown_final:
                registrador.info(f"Texto formateado a Markdown con Ollama exitosamente (longitud: {len(contenido_markdown_final)}).")
                if ruta_archivo_guardado:
                    guardar_markdown_en_archivo(contenido_markdown_final, ruta_archivo_guardado) # Utilidad común
            else:
                registrador.warning(f"El formateo a Markdown con modelo Ollama '{modelo_seleccionado}' devolvió contenido vacío.")

            return contenido_markdown_final

        except Exception as e_formateo:
            registrador.error(f"Error al formatear texto a Markdown con modelo Ollama '{modelo_seleccionado}': {e_formateo}")
            raise ErrorEnvoltorioOllama(f"Falló el formateo de texto a Markdown con Ollama: {e_formateo}", e_formateo)

[end of entrenai_refactor/nucleo/ia/envoltorio_ollama_refactorizado.py]
