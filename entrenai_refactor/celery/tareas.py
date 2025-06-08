# Módulo para definir las tareas asíncronas de Celery.

import requests # Para realizar peticiones HTTP a la API principal
from typing import Optional # Para el argumento opcional id_usuario_solicitante
from celery import shared_task # Para definir tareas sin necesidad de la instancia de app Celery aquí

# Importar la configuración global y el registrador
from entrenai_refactor.config.configuracion import configuracion_global
from entrenai_refactor.config.registrador import obtener_registrador

# Obtener una instancia del registrador para este módulo
registrador = obtener_registrador(__name__)

# Definir constantes para la comunicación con la API
# Estas podrían moverse a un archivo de constantes o ser parte de la configuración si varían mucho.
# Asegurarse que la URL base de la API no termine en '/' para que urljoin funcione bien (aunque aquí se usa f-string).
BASE_URL_API_ENTRENAI = f"http://{configuracion_global.host_api_fastapi}:{configuracion_global.puerto_api_fastapi}" # CAMBIADO
# El endpoint de la API que esta tarea debe llamar.
# Este endpoint fue refactorizado en 'ruta_procesamiento_interno.py'.
ENDPOINT_PROCESAMIENTO_CURSO_API = "/api/v1/procesamiento-interno/curso/procesar-archivos"
TIMEOUT_PETICION_API_SEGUNDOS = 30 # Segundos para timeout de conexión y lectura de la petición HTTP

# Nombre de la tarea refactorizado y más descriptivo.
# Es buena práctica nombrar explícitamente las tareas para evitar problemas si se mueve el archivo.
@shared_task(name="entrenai_refactor.celery.tareas.delegar_procesamiento_curso_a_api")
def delegar_procesamiento_curso_a_api(id_curso: int, id_usuario_solicitante: Optional[int] = None):
    """
    Tarea Celery que delega el procesamiento de archivos de un curso a la API principal de FastAPI.
    La API principal (específicamente el endpoint de procesamiento interno) es la que realmente
    ejecuta la lógica pesada en un hilo de fondo (BackgroundTasks de FastAPI).
    Esta tarea Celery simplemente actúa como un cliente HTTP para invocar dicho endpoint.

    Args:
        id_curso: El ID del curso de Moodle cuyos archivos se van a procesar.
        id_usuario_solicitante: Opcional. El ID del usuario de Moodle que inició la solicitud de procesamiento.
                                Si no se provee, se intentará usar el ID del profesor por defecto de la configuración.
    Returns:
        Un diccionario con el estado de la delegación de la tarea y un mensaje.
    """
    registrador.info(f"Tarea Celery iniciada: Se va a delegar el procesamiento para el curso ID: {id_curso}.")

    if id_usuario_solicitante is None:
        id_usuario_solicitante = configuracion_global.moodle.id_profesor_defecto
        if id_usuario_solicitante is None:
            mensaje_error_usuario = (
                f"No se proporcionó 'id_usuario_solicitante' y no hay un 'id_profesor_defecto' "
                f"configurado en el sistema. No se puede procesar el curso {id_curso}."
            )
            registrador.error(mensaje_error_usuario)
            # Esto marcará la tarea como fallida si se relanza la excepción.
            # Opcionalmente, se puede devolver un estado de error sin relanzar.
            # raise ValueError(mensaje_error_usuario)
            return {"estado": "FALLIDO_CONFIGURACION", "mensaje": mensaje_error_usuario, "id_curso": id_curso}
        registrador.info(f"Usando ID de profesor por defecto ({id_usuario_solicitante}) como solicitante.")

    url_completa_endpoint_api = f"{BASE_URL_API_ENTRENAI}{ENDPOINT_PROCESAMIENTO_CURSO_API}"

    # El cuerpo de la petición (payload) debe coincidir con el modelo Pydantic
    # esperado por el endpoint en 'ruta_procesamiento_interno.py' (SolicitudProcesamientoArchivosCurso).
    cuerpo_peticion_json = {
        "id_curso": id_curso,
        "id_usuario_solicitante": id_usuario_solicitante
    }

    registrador.info(f"Enviando solicitud POST a la API interna: {url_completa_endpoint_api} con cuerpo: {cuerpo_peticion_json}")

    try:
        respuesta_desde_api = requests.post(
            url_completa_endpoint_api,
            json=cuerpo_peticion_json,
            timeout=TIMEOUT_PETICION_API_SEGUNDOS
        )
        # Verificar si la API devolvió un error HTTP (ej. 4xx, 5xx)
        respuesta_desde_api.raise_for_status()

        datos_respuesta_json = respuesta_desde_api.json()
        mensaje_exito_delegacion = (
            f"Solicitud a la API para procesar el curso {id_curso} fue aceptada y delegada correctamente. "
            f"Respuesta de la API: {datos_respuesta_json.get('mensaje', 'Sin mensaje específico de la API.')}"
        )
        registrador.info(mensaje_exito_delegacion)
        return {"estado": "EXITOSO_DELEGACION", "id_curso": id_curso, "respuesta_api": datos_respuesta_json}

    except requests.exceptions.Timeout as e_timeout:
        mensaje_error_timeout = (
            f"Timeout ({TIMEOUT_PETICION_API_SEGUNDOS}s) al intentar comunicar con la API interna "
            f"en '{url_completa_endpoint_api}' para el curso {id_curso}: {e_timeout}"
        )
        registrador.error(mensaje_error_timeout)
        # Considerar reintentar la tarea usando las capacidades de Celery:
        # raise self.retry(exc=e_timeout, countdown=60, max_retries=3) # 'self' solo disponible si bind=True en @shared_task
        return {"estado": "FALLIDO_TIMEOUT_API", "id_curso": id_curso, "error": mensaje_error_timeout}

    except requests.exceptions.ConnectionError as e_conexion:
        mensaje_error_conexion = (
            f"Error de conexión al intentar comunicar con la API interna "
            f"en '{url_completa_endpoint_api}' para el curso {id_curso}: {e_conexion}"
        )
        registrador.error(mensaje_error_conexion)
        return {"estado": "FALLIDO_CONEXION_API", "id_curso": id_curso, "error": mensaje_error_conexion}

    except requests.exceptions.HTTPError as e_http:
        mensaje_error_http = (
            f"Error HTTP {e_http.response.status_code} recibido de la API interna "
            f"en '{url_completa_endpoint_api}' para el curso {id_curso}. "
            f"Respuesta: {e_http.response.text}"
        )
        registrador.error(mensaje_error_http)
        return {"estado": f"FALLIDO_RESPUESTA_API_HTTP_{e_http.response.status_code}", "id_curso": id_curso, "error_detalle": e_http.response.text}

    except Exception as e_inesperado: # Capturar cualquier otra excepción no prevista
        mensaje_error_inesperado = f"Error inesperado al delegar el procesamiento para el curso {id_curso} a la API: {e_inesperado}"
        registrador.exception(mensaje_error_inesperado) # Usar .exception() para incluir el traceback en el log
        return {"estado": "FALLIDO_INESPERADO_TAREA", "id_curso": id_curso, "error": str(e_inesperado)}

# Nota sobre tareas:
# - Si se añaden más tareas a este archivo, Celery las descubrirá automáticamente
#   debido a la configuración 'include' en 'aplicacion_celery.py'.
# - El decorador '@shared_task' es conveniente porque no requiere tener la instancia
#   de la aplicación Celery ('aplicacion_celery') importada directamente en este archivo.
# - Especificar el argumento 'name' en '@shared_task' es una buena práctica para la
#   identificación unívoca de tareas, especialmente si se reestructura el proyecto.