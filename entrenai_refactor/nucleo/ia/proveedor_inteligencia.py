from typing import Optional, Union, List, cast

from entrenai_refactor.config.configuracion import configuracion_global, ConfiguracionPrincipal
from entrenai_refactor.config.registrador import obtener_registrador
from entrenai_refactor.nucleo.ia.envoltorio_gemini import EnvoltorioGemini, ErrorEnvoltorioGemini
from entrenai_refactor.nucleo.ia.envoltorio_ollama import EnvoltorioOllama, ErrorEnvoltorioOllama

registrador = obtener_registrador(__name__)

class ErrorProveedorInteligencia(Exception):
    """Excepción personalizada para errores relacionados con el ProveedorInteligencia."""
    pass

class ProveedorInteligencia:
    """
    Fábrica y punto de acceso para instancias de envoltorios de IA (Ollama, Gemini)
    basándose en la configuración global de la aplicación.
    """

    def __init__(self, config: Optional[ConfiguracionPrincipal] = None):
        # Si no se pasa una config, usa la global. Útil para tests o contextos específicos.
        self.config_app = config or configuracion_global
        self.proveedor_ia_activo_nombre = self.config_app.proveedor_ia

        self._envoltorio_activo: Union[EnvoltorioOllama, EnvoltorioGemini, None] = None
        self._inicializar_envoltorio()

    def _inicializar_envoltorio(self):
        """Inicializa el envoltorio de IA apropiado según la configuración."""
        registrador.info(f"Inicializando envoltorio para el proveedor de IA: '{self.proveedor_ia_activo_nombre}'")
        if self.proveedor_ia_activo_nombre == "ollama":
            try:
                # EnvoltorioOllama ya usa configuracion_global.ollama en su __init__
                self._envoltorio_activo = EnvoltorioOllama()
                registrador.info("EnvoltorioOllama inicializado correctamente.")
            except ErrorEnvoltorioOllama as e:
                registrador.error(f"Error inicializando EnvoltorioOllama: {e}")
                # Decidir si relanzar o permitir que la app continúe sin IA funcional
                # Por ahora, se relanza para que el error sea evidente.
                raise ErrorProveedorInteligencia(f"Error inicializando EnvoltorioOllama: {e}") from e
        elif self.proveedor_ia_activo_nombre == "gemini":
            try:
                # EnvoltorioGemini ya usa configuracion_global.gemini en su __init__
                self._envoltorio_activo = EnvoltorioGemini()
                registrador.info("EnvoltorioGemini inicializado correctamente.")
            except ErrorEnvoltorioGemini as e:
                registrador.error(f"Error inicializando EnvoltorioGemini: {e}")
                raise ErrorProveedorInteligencia(f"Error inicializando EnvoltorioGemini: {e}") from e
        else:
            mensaje_error = (
                f"Proveedor de IA no válido: '{self.proveedor_ia_activo_nombre}'. "
                f"Opciones válidas: 'ollama', 'gemini'."
            )
            registrador.error(mensaje_error)
            raise ErrorProveedorInteligencia(mensaje_error)

    def obtener_envoltorio_activo(self) -> Union[EnvoltorioOllama, EnvoltorioGemini]:
        """Retorna el envoltorio de IA activo. Asegura que esté inicializado."""
        if not self._envoltorio_activo:
            registrador.warning("El envoltorio de IA no estaba inicializado. Intentando inicializar ahora.")
            self._inicializar_envoltorio() # Intenta inicializar si no lo está
            if not self._envoltorio_activo: # Si sigue sin estar inicializado después del intento
                 raise ErrorProveedorInteligencia("No se pudo inicializar un envoltorio de IA activo.")

        # Usamos cast para ayudar al type checker, ya que _inicializar_envoltorio debería haberlo establecido.
        return cast(Union[EnvoltorioOllama, EnvoltorioGemini], self._envoltorio_activo)

    # --- Métodos delegados al envoltorio activo ---

    def generar_embedding(self, texto: str, modelo: Optional[str] = None) -> List[float]:
        """Genera un embedding vectorial para un texto usando el envoltorio activo."""
        envoltorio = self.obtener_envoltorio_activo()
        try:
            return envoltorio.generar_embedding(texto=texto, modelo=modelo)
        except (ErrorEnvoltorioOllama, ErrorEnvoltorioGemini) as e:
            registrador.error(f"Error generando embedding a través del proveedor: {e}")
            raise ErrorProveedorInteligencia(f"Error del proveedor al generar embedding: {e}") from e

    def generar_completacion_chat(
        self, prompt: str, modelo: Optional[str] = None,
        mensaje_sistema: Optional[str] = None,
        fragmentos_contexto: Optional[List[str]] = None,
        stream: bool = False,
    ) -> str:
        """Genera una completación de chat (respuesta) usando el envoltorio activo."""
        envoltorio = self.obtener_envoltorio_activo()
        try:
            return envoltorio.generar_completacion_chat(
                prompt=prompt, modelo=modelo,
                mensaje_sistema=mensaje_sistema,
                fragmentos_contexto=fragmentos_contexto,
                stream=stream
            )
        except (ErrorEnvoltorioOllama, ErrorEnvoltorioGemini) as e:
            mensaje_error = f"Error generando completación de chat a través del proveedor: {e}"
            registrador.error(mensaje_error)
            raise ErrorProveedorInteligencia(mensaje_error) from e

    def formatear_a_markdown(
        self, contenido_texto: str, modelo: Optional[str] = None, ruta_guardado: Optional[str] = None
    ) -> str:
        """Formatea el texto a Markdown usando el envoltorio activo."""
        envoltorio = self.obtener_envoltorio_activo()
        try:
            # Convertir ruta_guardado a Path si se proporciona y el envoltorio lo espera
            ruta_path = Path(ruta_guardado) if ruta_guardado else None
            return envoltorio.formatear_a_markdown(
                contenido_texto=contenido_texto, modelo=modelo, ruta_guardado=ruta_path
            )
        except (ErrorEnvoltorioOllama, ErrorEnvoltorioGemini) as e:
            mensaje_error = f"Error formateando texto a Markdown a través del proveedor: {e}"
            registrador.error(mensaje_error)
            raise ErrorProveedorInteligencia(mensaje_error) from e

[end of entrenai_refactor/nucleo/ia/proveedor_inteligencia.py]
