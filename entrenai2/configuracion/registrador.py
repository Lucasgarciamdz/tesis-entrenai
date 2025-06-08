import logging
import sys

from entrenai2.configuracion.configuracion import config

def obtener_registrador(nombre: str) -> logging.Logger:
    """
    Configura y devuelve una instancia de logger para un módulo específico.

    Esta función asegura que todos los loggers de la aplicación compartan
    una configuración consistente, basada en las variables de entorno.

    Args:
        nombre: El nombre del logger, típicamente `__name__` del módulo que lo llama.

    Returns:
        Una instancia de `logging.Logger` configurada.
    """
    registrador = logging.getLogger(nombre)
    
    # Evita añadir manejadores duplicados si el logger ya fue configurado.
    if not registrador.handlers:
        registrador.setLevel(config.nivel_log)
        
        manejador_consola = logging.StreamHandler(sys.stdout)
        manejador_consola.setLevel(config.nivel_log)
        
        formateador = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        manejador_consola.setFormatter(formateador)
        
        registrador.addHandler(manejador_consola)

    return registrador
