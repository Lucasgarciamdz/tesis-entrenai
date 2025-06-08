import logging
import sys

# Importa la instancia de configuración global del módulo de configuración refactorizado.
from entrenai_refactor.config.configuracion import configuracion_global

def obtener_registrador(nombre: str) -> logging.Logger:
    """
    Configura y devuelve una instancia de registrador (logger) para un módulo específico.

    Esta función asegura que todos los registradores de la aplicación compartan
    una configuración consistente, basada en las variables de entorno definidas
    en `configuracion_global`.

    Args:
        nombre: El nombre del registrador, típicamente `__name__` del módulo que lo llama.

    Returns:
        Una instancia de `logging.Logger` configurada.
    """
    registrador = logging.getLogger(nombre)

    # Evita añadir manejadores (handlers) duplicados si el registrador ya fue configurado.
    # Esto es importante para no tener múltiples salidas del mismo log.
    if not registrador.handlers:
        # Establece el nivel de log para este registrador desde la configuración global.
        registrador.setLevel(configuracion_global.nivel_log)

        # Crea un manejador para enviar los logs a la consola (salida estándar).
        manejador_consola = logging.StreamHandler(sys.stdout)
        # Establece el nivel de log también para el manejador.
        manejador_consola.setLevel(configuracion_global.nivel_log)

        # Define el formato de los mensajes de log.
        formateador = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s (%(filename)s:%(lineno)d)"
        )
        manejador_consola.setFormatter(formateador)

        # Añade el manejador configurado al registrador.
        registrador.addHandler(manejador_consola)

        # Propagación: Si se establece a False, los logs no se pasarán a los
        # manejadores de los registradores de nivel superior (ej. el registrador raíz).
        # Para la mayoría de los casos de uso de la aplicación, es bueno dejarlo como True (defecto)
        # o gestionarlo explícitamente si hay una jerarquía de loggers compleja.
        # registrador.propagate = False

    return registrador

[end of entrenai_refactor/config/registrador.py]
