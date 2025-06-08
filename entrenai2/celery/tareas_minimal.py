import requests
from entrenai2.celery.aplicacion_celery_minimal import aplicacion
from entrenai2.configuracion.configuracion import configuracion_base
from entrenai2.configuracion.registrador import obtener_registrador

registrador = obtener_registrador(__name__)

# Obtener la URL base de la aplicación FastAPI desde la configuración
URL_BASE_FASTAPI = f"http://{configuracion_base.host_fastapi}:{configuracion_base.puerto_fastapi}"

@aplicacion.task(name="procesar_contenido_curso_moodle_minimal")
def procesar_contenido_curso_moodle_minimal(id_curso: int, id_usuario: int):
    """
    Una tarea minimalista de Celery que dispara el endpoint de procesamiento de archivos en la aplicación FastAPI.
    """
    endpoint = f"{URL_BASE_FASTAPI}/api/v1/cursos/procesar-contenido-curso-moodle/"
    carga = {
        "id_curso": id_curso,
        "id_usuario": id_usuario
    }
    registrador.info(f"Tarea Celery: Disparando endpoint de FastAPI para procesar curso {id_curso}...")
    try:
        respuesta = requests.post(endpoint, json=carga)
        respuesta.raise_for_status()
        registrador.info(f"Tarea Celery: Endpoint de FastAPI para curso {id_curso} llamado exitosamente. Respuesta: {respuesta.json()}")
        return respuesta.json()
    except requests.exceptions.RequestException as e:
        registrador.error(f"Tarea Celery: Ocurrió un error al llamar al endpoint de FastAPI para curso {id_curso}: {e}")
        raise
    except Exception as e:
        registrador.exception(f"Tarea Celery: Error inesperado en la tarea de procesamiento para curso {id_curso}: {e}")
        raise
