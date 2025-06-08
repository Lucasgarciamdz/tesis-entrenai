from typing import Union

from entrenai2.configuracion.configuracion import config
from entrenai2.configuracion.registrador import obtener_registrador
from entrenai2.nucleo.ia.envoltorio_gemini import EnvoltorioGemini, ErrorEnvoltorioGemini
from entrenai2.nucleo.ia.envoltorio_ollama import EnvoltorioOllama, ErrorEnvoltorioOllama

registrador = obtener_registrador(__name__)


class ErrorProveedorIA(Exception):
    """Excepción personalizada para errores relacionados con el proveedor de IA."""
    pass


class ProveedorIA:
    """
    Fábrica estática para obtener una instancia del envoltorio de IA 
    adecuado según la configuración global de la aplicación.
    """

    @staticmethod
    def obtener_envoltorio_ia_por_proveedor() -> Union[EnvoltorioOllama, EnvoltorioGemini]:
        """
        Crea y devuelve una instancia del envoltorio de IA (Ollama o Gemini)
        basándose en el proveedor especificado en la configuración.

        Returns:
            Una instancia de EnvoltorioOllama o EnvoltorioGemini.

        Raises:
            ErrorProveedorIA: Si el proveedor no es válido o falla la inicialización.
        """
        proveedor = config.proveedor_ia
        registrador.info(f"Inicializando proveedor de IA: '{proveedor}'")

        if proveedor == "ollama":
            try:
                return EnvoltorioOllama()
            except ErrorEnvoltorioOllama as e:
                registrador.error(f"Error al inicializar EnvoltorioOllama: {e}")
                raise ErrorProveedorIA("Fallo al inicializar el envoltorio de Ollama.") from e
        
        elif proveedor == "gemini":
            try:
                return EnvoltorioGemini()
            except ErrorEnvoltorioGemini as e:
                registrador.error(f"Error al inicializar EnvoltorioGemini: {e}")
                raise ErrorProveedorIA("Fallo al inicializar el envoltorio de Gemini.") from e
        
        else:
            mensaje = f"Proveedor de IA no válido: '{proveedor}'. Opciones válidas: 'ollama', 'gemini'."
            registrador.error(mensaje)
            raise ErrorProveedorIA(mensaje)
