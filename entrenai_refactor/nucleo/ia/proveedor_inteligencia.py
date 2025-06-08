from typing import Optional, Union, List, cast
from pathlib import Path # Asegurar que Path esté importado

from entrenai_refactor.config.configuracion import configuracion_global, ConfiguracionPrincipal
from entrenai_refactor.config.registrador import obtener_registrador
# Usar los nombres refactorizados cuando estén disponibles, por ahora los originales con alias si es necesario
from entrenai_refactor.nucleo.ia.envoltorio_gemini_refactorizado import EnvoltorioGemini, ErrorEnvoltorioGemini
from entrenai_refactor.nucleo.ia.envoltorio_ollama_refactorizado import EnvoltorioOllama, ErrorEnvoltorioOllama

registrador = obtener_registrador(__name__)

class ErrorProveedorInteligencia(Exception):
    """Excepción personalizada para errores relacionados con el ProveedorInteligencia."""
    def __init__(self, mensaje: str, error_original: Optional[Exception] = None):
        super().__init__(mensaje)
        self.error_original = error_original
        registrador.debug(f"Excepción ErrorProveedorInteligencia creada: {mensaje}, Original: {error_original}")

    def __str__(self):
        if self.error_original:
            return f"{super().__str__()} (Error original: {type(self.error_original).__name__}: {str(self.error_original)})"
        return super().__str__()

class ProveedorInteligencia:
    """
    Actúa como una fábrica y un punto de acceso centralizado para los diferentes
    servicios de Inteligencia Artificial (IA), como Ollama o Gemini.
    Se basa en la configuración global de la aplicación para determinar qué
    proveedor de IA utilizar y cómo configurarlo.
    """

    def __init__(self, configuracion_app: Optional[ConfiguracionPrincipal] = None):
        """
        Inicializa el ProveedorInteligencia.

        Args:
            configuracion_app: Opcional. Una instancia de ConfiguracionPrincipal.
                               Si no se proporciona, se utiliza la configuración global.
                               Esto es útil para pruebas o contextos específicos.
        """
        self.config_aplicacion = configuracion_app or configuracion_global
        self.nombre_proveedor_ia_configurado = self.config_aplicacion.proveedor_ia_seleccionado # CAMBIADO

        self._envoltorio_ia_activo: Union[EnvoltorioOllama, EnvoltorioGemini, None] = None
        self._inicializar_envoltorio_ia_seleccionado()

    def _inicializar_envoltorio_ia_seleccionado(self):
        """
        Inicializa el envoltorio de IA (Ollama o Gemini) que esté configurado
        como activo en la aplicación.
        """
        registrador.info(f"Inicializando envoltorio para el proveedor de IA configurado: '{self.nombre_proveedor_ia_configurado}'")

        if self.nombre_proveedor_ia_configurado == "ollama":
            try:
                # El EnvoltorioOllama utiliza internamente configuracion_global.ollama para sus detalles.
                self._envoltorio_ia_activo = EnvoltorioOllama()
                registrador.info("EnvoltorioOllama (refactorizado) inicializado y configurado como proveedor de IA activo.")
            except ErrorEnvoltorioOllama as e_ollama:
                registrador.error(f"Error al inicializar EnvoltorioOllama: {e_ollama}")
                # Se decide relanzar para que el error de configuración/disponibilidad de IA sea evidente.
                raise ErrorProveedorInteligencia(f"Error al inicializar el proveedor Ollama: {e_ollama}", e_ollama)

        elif self.nombre_proveedor_ia_configurado == "gemini":
            try:
                # El EnvoltorioGemini utiliza internamente configuracion_global.gemini.
                self._envoltorio_ia_activo = EnvoltorioGemini()
                registrador.info("EnvoltorioGemini (refactorizado) inicializado y configurado como proveedor de IA activo.")
            except ErrorEnvoltorioGemini as e_gemini:
                registrador.error(f"Error al inicializar EnvoltorioGemini: {e_gemini}")
                raise ErrorProveedorInteligencia(f"Error al inicializar el proveedor Gemini: {e_gemini}", e_gemini)

        else:
            mensaje_error_proveedor = (
                f"Proveedor de IA no válido o no soportado: '{self.nombre_proveedor_ia_configurado}'. "
                f"Las opciones válidas configuradas son 'ollama' o 'gemini'."
            )
            registrador.error(mensaje_error_proveedor)
            raise ErrorProveedorInteligencia(mensaje_error_proveedor)

    def obtener_envoltorio_ia_activo(self) -> Union[EnvoltorioOllama, EnvoltorioGemini]:
        """
        Devuelve la instancia del envoltorio de IA activo (Ollama o Gemini).
        Asegura que el envoltorio esté inicializado. Si no lo está, intenta inicializarlo.
        Lanza una excepción si no se puede obtener un envoltorio activo.
        """
        if not self._envoltorio_ia_activo:
            registrador.warning("El envoltorio de IA no estaba previamente inicializado. Intentando inicialización forzada ahora.")
            self._inicializar_envoltorio_ia_seleccionado() # Intenta inicializar si por alguna razón no lo estaba.

            if not self._envoltorio_ia_activo: # Si después del reintento sigue sin estar inicializado
                 registrador.critical("Fallo crítico: No se pudo inicializar un envoltorio de IA activo después de reintentos.")
                 raise ErrorProveedorInteligencia("Fallo crítico al obtener un envoltorio de IA activo.")

        # Se usa 'cast' para ayudar al sistema de tipado de Python, ya que la lógica anterior
        # debería garantizar que _envoltorio_ia_activo no sea None en este punto.
        return cast(Union[EnvoltorioOllama, EnvoltorioGemini], self._envoltorio_ia_activo)

    # --- Métodos delegados al envoltorio de IA activo ---
    # Estos métodos proporcionan una interfaz unificada para interactuar con el proveedor de IA,
    # independientemente de si es Ollama o Gemini.

    def generar_embedding(self, texto_entrada: str, nombre_modelo_especifico: Optional[str] = None) -> List[float]:
        """
        Genera un embedding (vector numérico) para un texto dado utilizando el envoltorio de IA activo.
        """
        envoltorio_seleccionado = self.obtener_envoltorio_ia_activo()
        registrador.debug(f"Delegando generación de embedding al proveedor: {type(envoltorio_seleccionado).__name__}")
        try:
            # Los métodos de los envoltorios deben tener la misma firma (o compatible)
            if isinstance(envoltorio_seleccionado, EnvoltorioOllama):
                return envoltorio_seleccionado.generar_embedding_de_texto(texto_entrada, nombre_modelo_especifico)
            elif isinstance(envoltorio_seleccionado, EnvoltorioGemini):
                 return envoltorio_seleccionado.generar_embedding_de_texto(texto_entrada, nombre_modelo_especifico)
            else: # No debería ocurrir si la inicialización es correcta
                raise ErrorProveedorInteligencia(f"Tipo de envoltorio activo no reconocido: {type(envoltorio_seleccionado)}")

        except (ErrorEnvoltorioOllama, ErrorEnvoltorioGemini) as e_envoltorio:
            registrador.error(f"Error específico del envoltorio al generar embedding: {e_envoltorio}")
            raise ErrorProveedorInteligencia(f"Error del proveedor de IA al generar embedding: {e_envoltorio}", e_envoltorio)
        except Exception as e_general:
            registrador.exception(f"Error inesperado al generar embedding a través del proveedor: {e_general}")
            raise ErrorProveedorInteligencia(f"Error inesperado del proveedor al generar embedding: {e_general}", e_general)


    def generar_respuesta_de_chat(
        self,
        prompt_usuario: str,
        nombre_modelo_especifico: Optional[str] = None,
        mensaje_de_sistema: Optional[str] = None,
        historial_chat_previo: Optional[List[Dict[str, str]]] = None,
        fragmentos_de_contexto: Optional[List[str]] = None,
        # stream: bool = False, # El streaming se maneja a nivel de envoltorio si se implementa allí
    ) -> str:
        """
        Genera una respuesta de chat (completación) para un prompt dado,
        utilizando el envoltorio de IA activo.
        """
        envoltorio_seleccionado = self.obtener_envoltorio_ia_activo()
        registrador.debug(f"Delegando generación de respuesta de chat al proveedor: {type(envoltorio_seleccionado).__name__}")
        try:
            # Asumimos que ambos envoltorios tienen un método 'generar_respuesta_de_chat' con firma compatible.
            return envoltorio_seleccionado.generar_respuesta_de_chat(
                prompt_usuario=prompt_usuario,
                nombre_modelo_chat=nombre_modelo_especifico, # Pasar como 'nombre_modelo_chat' al envoltorio
                mensaje_de_sistema=mensaje_de_sistema,
                historial_chat_previo=historial_chat_previo,
                fragmentos_de_contexto=fragmentos_de_contexto,
                # stream=stream # El parámetro stream se pasaría aquí si la firma lo incluye
            )
        except (ErrorEnvoltorioOllama, ErrorEnvoltorioGemini) as e_envoltorio:
            mensaje_error_chat = f"Error específico del envoltorio al generar respuesta de chat: {e_envoltorio}"
            registrador.error(mensaje_error_chat)
            raise ErrorProveedorInteligencia(f"Error del proveedor de IA al generar respuesta de chat: {e_envoltorio}", e_envoltorio)
        except Exception as e_general:
            registrador.exception(f"Error inesperado al generar respuesta de chat a través del proveedor: {e_general}")
            raise ErrorProveedorInteligencia(f"Error inesperado del proveedor al generar respuesta de chat: {e_general}", e_general)


    def formatear_texto_a_markdown(
        self,
        texto_original: str,
        nombre_modelo_especifico: Optional[str] = None,
        ruta_archivo_para_guardar: Optional[Path] = None # Aceptar Path directamente
    ) -> str:
        """
        Formatea un texto crudo a formato Markdown utilizando el envoltorio de IA activo.
        """
        envoltorio_seleccionado = self.obtener_envoltorio_ia_activo()
        registrador.debug(f"Delegando formateo a Markdown al proveedor: {type(envoltorio_seleccionado).__name__}")
        try:
            # Asumimos que ambos envoltorios tienen un método 'convertir_texto_a_markdown' (o similar)
            # con firma compatible.
            if isinstance(envoltorio_seleccionado, EnvoltorioOllama):
                return envoltorio_seleccionado.convertir_texto_a_markdown(
                    texto_original, nombre_modelo_formateo=nombre_modelo_especifico, ruta_archivo_guardado=ruta_archivo_para_guardar
                )
            elif isinstance(envoltorio_seleccionado, EnvoltorioGemini):
                 return envoltorio_seleccionado.convertir_texto_a_markdown(
                    texto_original, nombre_modelo_formateo=nombre_modelo_especifico, ruta_archivo_guardado=ruta_archivo_para_guardar
                )
            else:
                 raise ErrorProveedorInteligencia(f"Tipo de envoltorio activo no reconocido para formateo: {type(envoltorio_seleccionado)}")
        except (ErrorEnvoltorioOllama, ErrorEnvoltorioGemini) as e_envoltorio:
            mensaje_error_markdown = f"Error específico del envoltorio al formatear a Markdown: {e_envoltorio}"
            registrador.error(mensaje_error_markdown)
            raise ErrorProveedorInteligencia(f"Error del proveedor de IA al formatear a Markdown: {e_envoltorio}", e_envoltorio)
        except Exception as e_general:
            registrador.exception(f"Error inesperado al formatear a Markdown a través del proveedor: {e_general}")
            raise ErrorProveedorInteligencia(f"Error inesperado del proveedor al formatear a Markdown: {e_general}", e_general)

[end of entrenai_refactor/nucleo/ia/proveedor_inteligencia_refactorizado.py]
