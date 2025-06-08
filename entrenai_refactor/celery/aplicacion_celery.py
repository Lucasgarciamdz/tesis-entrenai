# Módulo para la configuración e inicialización de la aplicación Celery.

from celery import Celery

# Importar la configuración global y el registrador
from entrenai_refactor.config.configuracion import configuracion_global
from entrenai_refactor.config.registrador import obtener_registrador

# Obtener una instancia del registrador para este módulo
registrador = obtener_registrador(__name__)

# Nombre de la aplicación Celery. Puede ser útil para la organización si hay múltiples apps.
NOMBRE_APLICACION_CELERY = "entrenai_tareas_asincronas"

# Crear la instancia de la aplicación Celery.
# El nombre principal aquí es el del módulo donde se definen las tareas (o un nombre común).
# Se recomienda que las tareas se definan en un módulo separado (ej. tareas.py).
aplicacion_celery = Celery(
    NOMBRE_APLICACION_CELERY,
    broker=configuracion_global.celery.url_broker_celery, # CAMBIADO
    backend=configuracion_global.celery.backend_resultados_celery, # CAMBIADO
    include=[
        'entrenai_refactor.celery.tareas'  # Lista de módulos donde Celery buscará tareas.
    ]
)

# Configuración adicional de Celery (opcional, se puede externalizar)
# Documentación de configuración: https://docs.celeryq.dev/en/stable/userguide/configuration.html
aplicacion_celery.conf.update(
    task_serializer='json', # Serializador para los mensajes de tarea.
    accept_content=['json'],  # Tipos de contenido aceptados.
    result_serializer='json', # Serializador para los resultados de las tareas.
    timezone=getattr(configuracion_global, 'timezone_app', 'Europe/Madrid'), # Zona horaria, con fallback
    enable_utc=True, # Usar UTC para fechas y horas internas.
    # Ajustes de visibilidad y reintentos (ejemplos, ajustar según necesidad)
    # task_acks_late = True, # Reconocimiento tardío de tareas (útil si la tarea es idempotente y larga)
    # task_reject_on_worker_lost = True, # Rechazar tarea si el worker se pierde (requiere acks_late)
    # worker_prefetch_multiplier = 1, # Para asegurar que un worker solo toma una tarea a la vez (si son largas o consumen mucha memoria)
)

registrador.info(f"Aplicación Celery '{NOMBRE_APLICACION_CELERY}' inicializada y configurada.")
registrador.info(f"Broker de Celery configurado en: {configuracion_global.celery.url_broker_celery}") # CAMBIADO
registrador.info(f"Backend de resultados de Celery configurado en: {configuracion_global.celery.backend_resultados_celery}") # CAMBIADO
registrador.info(f"Módulos de tareas para auto-descubrimiento: {aplicacion_celery.conf.include}")

# La tarea de ejemplo ha sido eliminada de este archivo.
# Las tareas reales deben definirse en el módulo 'entrenai_refactor.celery.tareas'.