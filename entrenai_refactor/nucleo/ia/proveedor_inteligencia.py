from typing import Optional, Union, List, Dict, cast # Dict añadido para historial_chat_previo
from pathlib import Path

from entrenai_refactor.config.configuracion import configuracion_global, ConfiguracionPrincipal
from entrenai_refactor.config.registrador import obtener_registrador
# Corregir las rutas de importación para usar rutas relativas a los archivos ya refactorizados.
from .envoltorio_gemini import EnvoltorioGemini, ErrorEnvoltorioGemini
from .envoltorio_ollama import EnvoltorioOllama, ErrorEnvoltorioOllama
# No se necesita importar utilidades_comunes_ia directamente aquí si no se usan sus funciones.

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
        self.nombre_proveedor_ia_configurado: str = self.config_aplicacion.proveedor_ia_seleccionado

        self._envoltorio_ia_activo: Union[EnvoltorioOllama, EnvoltorioGemini, None] = None
        self._inicializar_envoltorio_ia_seleccionado()

    def _inicializar_envoltorio_ia_seleccionado(self):
        """
        Inicializa el envoltorio de IA (Ollama o Gemini) que esté configurado
        como activo en la aplicación. Lanza ErrorProveedorInteligencia si falla.
        """
        registrador.info(f"Inicializando envoltorio para el proveedor de IA configurado: '{self.nombre_proveedor_ia_configurado}'")

        if self.nombre_proveedor_ia_configurado == "ollama":
            try:
                # EnvoltorioOllama usa internamente configuracion_global.ollama.
                self._envoltorio_ia_activo = EnvoltorioOllama() # Ya refactorizado
                registrador.info("EnvoltorioOllama inicializado y configurado como proveedor de IA activo.")
            except ErrorEnvoltorioOllama as e_ollama: # Captura el error específico del envoltorio
                registrador.error(f"Error al inicializar EnvoltorioOllama: {e_ollama}")
                # Relanzar para que el error de configuración/disponibilidad de IA sea evidente y manejado externamente.
                raise ErrorProveedorInteligencia(f"Error al inicializar el proveedor Ollama: {e_ollama}", e_ollama)
            except Exception as e_general_ollama: # Captura cualquier otro error inesperado durante la inicialización
                registrador.error(f"Error general inesperado al inicializar EnvoltorioOllama: {e_general_ollama}")
                raise ErrorProveedorInteligencia(f"Error general al inicializar el proveedor Ollama: {e_general_ollama}", e_general_ollama)


        elif self.nombre_proveedor_ia_configurado == "gemini":
            try:
                # EnvoltorioGemini usa internamente configuracion_global.gemini.
                self._envoltorio_ia_activo = EnvoltorioGemini() # Ya refactorizado
                registrador.info("EnvoltorioGemini inicializado y configurado como proveedor de IA activo.")
            except ErrorEnvoltorioGemini as e_gemini:
                registrador.error(f"Error al inicializar EnvoltorioGemini: {e_gemini}")
                raise ErrorProveedorInteligencia(f"Error al inicializar el proveedor Gemini: {e_gemini}", e_gemini)
            except Exception as e_general_gemini:
                registrador.error(f"Error general inesperado al inicializar EnvoltorioGemini: {e_general_gemini}")
                raise ErrorProveedorInteligencia(f"Error general al inicializar el proveedor Gemini: {e_general_gemini}", e_general_gemini)

        else:
            mensaje_error_proveedor = (
                f"Proveedor de IA no válido o no soportado: '{self.nombre_proveedor_ia_configurado}'. "
                f"Las opciones válidas configuradas en el sistema son 'ollama' o 'gemini'."
            )
            registrador.error(mensaje_error_proveedor)
            raise ErrorProveedorInteligencia(mensaje_error_proveedor)

    def obtener_envoltorio_ia_activo(self) -> Union[EnvoltorioOllama, EnvoltorioGemini]:
        """
        Devuelve la instancia del envoltorio de IA activo (Ollama o Gemini).
        Asegura que el envoltorio esté inicializado. Si no lo está (ej. si la inicialización falló
        y se decidió no relanzar la excepción en __init__), intenta inicializarlo de nuevo.
        Lanza una excepción `ErrorProveedorInteligencia` si no se puede obtener un envoltorio activo.
        """
        if not self._envoltorio_ia_activo:
            registrador.warning("El envoltorio de IA no estaba previamente inicializado o falló su inicialización. Intentando de nuevo.")
            self._inicializar_envoltorio_ia_seleccionado() # Esto puede lanzar ErrorProveedorInteligencia

            if not self._envoltorio_ia_activo: # Si después del reintento sigue sin estar inicializado (improbable si _inicializar... lanza error)
                 mensaje_critico = "Fallo crítico: No se pudo inicializar un envoltorio de IA activo después de reintentos."
                 registrador.critical(mensaje_critico)
                 raise ErrorProveedorInteligencia(mensaje_critico)

        # Se usa 'cast' para ayudar al sistema de tipado de Python, ya que la lógica anterior
        # (incluyendo las excepciones lanzadas) debería garantizar que _envoltorio_ia_activo no sea None.
        return cast(Union[EnvoltorioOllama, EnvoltorioGemini], self._envoltorio_ia_activo)


    def generar_embedding(self, texto_entrada: str, nombre_modelo_especifico: Optional[str] = None) -> List[float]:
        """
        Genera un embedding (vector numérico) para un texto dado utilizando el envoltorio de IA activo.

        Args:
            texto_entrada: El texto para el cual generar el embedding.
            nombre_modelo_especifico: Opcional. Nombre del modelo de embedding a usar, si se
                                      desea anular el predeterminado del proveedor.

        Returns:
            Una lista de floats representando el embedding.

        Raises:
            ErrorProveedorInteligencia: Si ocurre un error durante la generación del embedding.
        """
        envoltorio_activo = self.obtener_envoltorio_ia_activo() # Puede lanzar ErrorProveedorInteligencia si falla la obtención
        registrador.debug(f"Delegando generación de embedding al proveedor: {type(envoltorio_activo).__name__}")
        try:
            # Los métodos de los envoltorios deben tener la misma firma (o compatible)
            # El nombre del parámetro para el modelo es 'nombre_modelo_embedding' en los envoltorios.
            return envoltorio_activo.generar_embedding_de_texto(texto_entrada, nombre_modelo_embedding=nombre_modelo_especifico)
        except (ErrorEnvoltorioOllama, ErrorEnvoltorioGemini) as e_envoltorio: # Errores específicos de los envoltorios
            registrador.error(f"Error específico del envoltorio '{type(envoltorio_activo).__name__}' al generar embedding: {e_envoltorio}")
            raise ErrorProveedorInteligencia(f"Error del proveedor de IA al generar embedding: {e_envoltorio}", e_envoltorio)
        except Exception as e_general: # Otros errores inesperados
            registrador.exception(f"Error inesperado al generar embedding a través del proveedor '{type(envoltorio_activo).__name__}': {e_general}")
            raise ErrorProveedorInteligencia(f"Error inesperado del proveedor al generar embedding: {e_general}", e_general)


    def generar_respuesta_de_chat(
        self,
        prompt_usuario: str,
        nombre_modelo_especifico: Optional[str] = None,
        mensaje_de_sistema: Optional[str] = None,
        historial_chat_previo: Optional[List[Dict[str, str]]] = None,
        fragmentos_de_contexto: Optional[List[str]] = None,
        # transmitir: bool = False, # El streaming (transmitir) se maneja a nivel de envoltorio si se implementa allí
    ) -> str:
        """
        Genera una respuesta de chat (completación) para un prompt dado,
        utilizando el envoltorio de IA activo.

        Args:
            prompt_usuario: El prompt o pregunta del usuario.
            nombre_modelo_especifico: Opcional. Nombre del modelo de chat a usar.
            mensaje_de_sistema: Opcional. Instrucción a nivel de sistema para el modelo.
            historial_chat_previo: Opcional. Historial de la conversación.
            fragmentos_de_contexto: Opcional. Fragmentos de texto para proveer contexto adicional.
            # transmitir: Opcional. Si se debe usar streaming para la respuesta (aún no implementado globalmente).

        Returns:
            La respuesta generada por el modelo de IA.

        Raises:
            ErrorProveedorInteligencia: Si ocurre un error durante la generación de la respuesta.
        """
        envoltorio_activo = self.obtener_envoltorio_ia_activo()
        registrador.debug(f"Delegando generación de respuesta de chat al proveedor: {type(envoltorio_activo).__name__}")
        try:
            # El nombre del parámetro para el modelo es 'nombre_modelo_chat' en los envoltorios.
            return envoltorio_activo.generar_respuesta_de_chat(
                prompt_usuario=prompt_usuario,
                nombre_modelo_chat=nombre_modelo_especifico,
                mensaje_de_sistema=mensaje_de_sistema,
                historial_chat_previo=historial_chat_previo,
                fragmentos_de_contexto=fragmentos_de_contexto,
                # stream=transmitir # El parámetro stream se pasaría aquí si la firma lo incluye
            )
        except (ErrorEnvoltorioOllama, ErrorEnvoltorioGemini) as e_envoltorio:
            mensaje_error_chat = f"Error específico del envoltorio '{type(envoltorio_activo).__name__}' al generar respuesta de chat: {e_envoltorio}"
            registrador.error(mensaje_error_chat)
            raise ErrorProveedorInteligencia(f"Error del proveedor de IA al generar respuesta de chat: {e_envoltorio}", e_envoltorio)
        except Exception as e_general:
            registrador.exception(f"Error inesperado al generar respuesta de chat a través del proveedor '{type(envoltorio_activo).__name__}': {e_general}")
            raise ErrorProveedorInteligencia(f"Error inesperado del proveedor al generar respuesta de chat: {e_general}", e_general)


    def formatear_texto_a_markdown(
        self,
        texto_original: str,
        nombre_modelo_especifico: Optional[str] = None,
        ruta_archivo_para_guardar: Optional[Path] = None
    ) -> str:
        """
        Formatea un texto crudo a formato Markdown utilizando el envoltorio de IA activo.

        Args:
            texto_original: El texto a formatear.
            nombre_modelo_especifico: Opcional. Nombre del modelo a usar para el formateo.
            ruta_archivo_para_guardar: Opcional. Si se provee, guarda el Markdown resultante en esta ruta.

        Returns:
            El texto formateado en Markdown.

        Raises:
            ErrorProveedorInteligencia: Si ocurre un error durante el formateo.
        """
        envoltorio_activo = self.obtener_envoltorio_ia_activo()
        registrador.debug(f"Delegando formateo a Markdown al proveedor: {type(envoltorio_activo).__name__}")
        try:
            # El nombre del parámetro para el modelo es 'nombre_modelo_formateo' en los envoltorios.
            return envoltorio_activo.convertir_texto_a_markdown(
                texto_original,
                nombre_modelo_formateo=nombre_modelo_especifico,
                ruta_archivo_guardado=ruta_archivo_para_guardar
            )
        except (ErrorEnvoltorioOllama, ErrorEnvoltorioGemini) as e_envoltorio:
            mensaje_error_markdown = f"Error específico del envoltorio '{type(envoltorio_activo).__name__}' al formatear a Markdown: {e_envoltorio}"
            registrador.error(mensaje_error_markdown)
            raise ErrorProveedorInteligencia(f"Error del proveedor de IA al formatear a Markdown: {e_envoltorio}", e_envoltorio)
        except Exception as e_general:
            registrador.exception(f"Error inesperado al formatear a Markdown a través del proveedor '{type(envoltorio_activo).__name__}': {e_general}")
            raise ErrorProveedorInteligencia(f"Error inesperado del proveedor al formatear a Markdown: {e_general}", e_general)
