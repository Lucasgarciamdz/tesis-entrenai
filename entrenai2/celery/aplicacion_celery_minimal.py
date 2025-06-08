from celery import Celery
from entrenai2.configuracion.configuracion import configuracion_celery

# Obtener URLs del broker y backend desde la configuración centralizada
url_broker = configuracion_celery.url_broker
backend_resultado = configuracion_celery.backend_resultado

# Crear una instancia de la aplicación Celery
aplicacion = Celery(
    "entrenai_minimal",
    broker=url_broker,
    backend=backend_resultado,
    include=["entrenai2.celery.tareas_minimal"] # La ruta de las tareas
)

# Configuración opcional de Celery
aplicacion.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    broker_connection_retry_on_startup=True,
)
