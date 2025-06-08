# Inicialización del módulo de Celery de EntrenAI.

# Importar la instancia de la aplicación Celery para que sea accesible
# cuando Celery busque la aplicación (ej. `celery -A entrenai_refactor.celery worker`).
from .aplicacion_celery import aplicacion_celery

# Definir __all__ para explicitar qué se exporta desde este paquete.
__all__ = ("aplicacion_celery",)

# Se podría añadir un log aquí también, pero usualmente la configuración de Celery
# ya es bastante verbosa al iniciar.
# from ..config.registrador import obtener_registrador
# registrador = obtener_registrador(__name__)
# registrador.info("Módulo Celery de EntrenAI inicializado y aplicación Celery exportada.")